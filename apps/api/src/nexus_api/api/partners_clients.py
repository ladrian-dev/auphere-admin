"""Partner self-serve for a client's WhatsApp line + admin whitelist.

``/v1/partners/clients/{external_client_ref}/…`` — server-to-server,
authenticated with the partner's secret API key (``provision`` scope).
This is what lets Amigable Cobro connect the WhatsApp where a business's
agent lives and register that business's admins **from their own app**,
instead of an Auphere operator doing it in the panel.

Tenancy invariant (same as ``/v1/widget-sessions``): the tenant is ALWAYS
resolved from ``partner_tenants`` under the authenticated partner — never
from the request body — so a partner can only ever touch its own clients.
An unknown ref is an opaque 404.
"""

from __future__ import annotations

from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from nexus_channels.whatsapp_meta import SignupIngressPayload
from nexus_channels.whatsapp_meta.phone import to_e164
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.config import get_settings
from nexus_api.core.partner_auth import PartnerContext, require_partner_key
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.repositories.partner import PartnerTenantRepository
from nexus_api.services.agent_config_service import AgentConfigService
from nexus_api.services.meta_signup_service import complete_meta_signup

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/partners", tags=["partners"])


# ── schemas ─────────────────────────────────────────────────────────────────


class SignupConfigOut(BaseModel):
    """Public Meta App identifiers the partner's frontend needs to open
    Facebook Login for Business (Embedded Signup). No secrets here — the
    App Secret / tokens never leave the backend."""

    app_id: str
    cloud_api_config_id: str
    coexistence_config_id: str
    graph_api_version: str


class WhatsAppSignupIn(BaseModel):
    """What the partner POSTs after the client finishes Embedded Signup.

    Mirrors the operator flow: ``code`` is the single-use OAuth code,
    ``waba_id`` is always present, ``phone_number_id`` / ``business_id`` are
    absent for Coexistence (the orchestrator derives the phone from the
    WABA). ``mode`` defaults to ``coexistence`` — the flow Amigable Cobro
    uses so the business keeps its WhatsApp Business mobile app.
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=512)
    waba_id: str = Field(min_length=1, max_length=64)
    phone_number_id: str | None = Field(default=None, max_length=64)
    business_id: str | None = Field(default=None, max_length=64)
    mode: str = Field(default="coexistence", pattern="^(cloud_api|coexistence)$")


class WhatsAppSignupOut(BaseModel):
    status: str
    waba_id: str
    phone_number_id: str
    display_phone_number: str
    mode: str
    bisuat_expires_at: str | None = None


class AdminIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=4, max_length=32, description="Teléfono del admin (E.164).")
    name: str | None = Field(default=None, max_length=120)
    role: Literal["full", "readonly"] = Field(
        default="full",
        description=(
            "'full' = acceso total (consultas + cambios de deudores). "
            "'readonly' = solo consultar información (deudas, cuentas, "
            "listados); no puede registrar pagos, crear cuentas ni ningún "
            "cambio."
        ),
    )


class AdminsUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    admins: list[AdminIn] = Field(
        min_length=0,
        max_length=50,
        description="Whitelist completa de admins de la empresa (reemplaza la anterior).",
    )


class AdminOut(BaseModel):
    phone: str
    name: str | None = None
    role: Literal["full", "readonly"] = "full"


class AdminsOut(BaseModel):
    admin_only: bool
    admins: list[AdminOut]


# ── helpers ─────────────────────────────────────────────────────────────────


async def _resolve_tenant_id(session: AsyncSession, ctx: PartnerContext, ref: str):
    """Tenant behind ``ref`` for the authenticated partner, or opaque 404."""
    async with session.begin():
        mapping = await PartnerTenantRepository(session).get_mapping(ctx.partner.id, ref)
    if mapping is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown client reference",
        )
    return mapping.tenant_id


def _partner_actor(ctx: PartnerContext) -> str:
    return f"partner:{ctx.partner.slug[:32]}"


# ── endpoints ───────────────────────────────────────────────────────────────


@router.get("/whatsapp/signup-config", response_model=SignupConfigOut)
async def whatsapp_signup_config(
    ctx: PartnerContext = Depends(require_partner_key("provision")),
) -> SignupConfigOut:
    """Identifiers the partner app embeds to drive Embedded Signup with
    Auphere's Meta App. Coexistence is the id Amigable Cobro should use."""
    settings = get_settings()
    return SignupConfigOut(
        app_id=settings.meta_app_id,
        cloud_api_config_id=settings.meta_config_id_wa_cloud_api,
        coexistence_config_id=settings.meta_config_id_wa_coexistence,
        graph_api_version=settings.meta_graph_api_version,
    )


@router.post(
    "/clients/{external_client_ref}/whatsapp/signup",
    response_model=WhatsAppSignupOut,
    status_code=status.HTTP_201_CREATED,
)
async def connect_client_whatsapp(
    external_client_ref: str,
    body: WhatsAppSignupIn,
    ctx: PartnerContext = Depends(require_partner_key("provision")),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> WhatsAppSignupOut:
    """Complete Embedded Signup (coexistence) for the client's WhatsApp line.

    Runs the SAME orchestration as the operator panel
    (``complete_meta_signup``): exchange code → register phone → subscribe
    webhook → persist credentials → upsert the ``channels`` row. On success
    that number is the line where the business's agent lives.
    """
    tenant_id = await _resolve_tenant_id(session, ctx, external_client_ref)
    payload = SignupIngressPayload(
        code=body.code,
        waba_id=body.waba_id,
        phone_number_id=body.phone_number_id,
        business_id=body.business_id,
        mode=body.mode,
    )
    async with tenant_scoped_session(session, tenant_id):
        bundle = await complete_meta_signup(
            session=session,
            redis=redis,
            payload=payload,
            tenant_id=tenant_id,
            actor=_partner_actor(ctx),
            audit_action="channel.whatsapp.partner_signup",
        )
    result = bundle.result
    return WhatsAppSignupOut(
        status="connected",
        waba_id=result.waba_id,
        phone_number_id=result.phone_number_id,
        display_phone_number=result.display_phone_number,
        mode=result.mode,
        bisuat_expires_at=(
            result.bisuat_expires_at.isoformat() if result.bisuat_expires_at is not None else None
        ),
    )


@router.get("/clients/{external_client_ref}/admins", response_model=AdminsOut)
async def get_client_admins(
    external_client_ref: str,
    ctx: PartnerContext = Depends(require_partner_key("provision")),
    session: AsyncSession = Depends(get_db_session),
) -> AdminsOut:
    """Current admin whitelist for the client (from the active agent config)."""
    tenant_id = await _resolve_tenant_id(session, ctx, external_client_ref)
    async with tenant_scoped_session(session, tenant_id):
        active = await AgentConfigService(session).get_active()
    return _admins_out(active.policies if active else None)


@router.put("/clients/{external_client_ref}/admins", response_model=AdminsOut)
async def set_client_admins(
    external_client_ref: str,
    body: AdminsUpdateIn,
    ctx: PartnerContext = Depends(require_partner_key("provision")),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> AdminsOut:
    """Replace the client's admin whitelist (with per-admin roles).

    Each admin is a phone allowed to talk to the agent. ``role`` sets what it
    can do: ``full`` = query + all debtor changes; ``readonly`` = only query
    information (no writes — the worker strips write tools for that sender).
    The phones become ``policies.admin_access.admin_phones`` and the
    ``{phone, name, role}`` entries become ``admin_access.admins`` on a
    freshly promoted agent config.
    """
    tenant_id = await _resolve_tenant_id(session, ctx, external_client_ref)

    phones: list[str] = []
    admins_meta: list[dict[str, str | None]] = []
    for admin in body.admins:
        e164 = to_e164(admin.phone)
        if not e164:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Teléfono inválido (no E.164): {admin.phone}",
            )
        if e164 not in phones:
            phones.append(e164)
            admins_meta.append({"phone": e164, "name": admin.name, "role": admin.role})

    async with tenant_scoped_session(session, tenant_id):
        try:
            config = await AgentConfigService(session).set_admin_access(
                actor=_partner_actor(ctx),
                admin_phones=phones,
                admins=admins_meta,
            )
        except Exception as exc:  # AgentConfigConflict → 409
            from nexus_api.core.errors import AgentConfigConflict

            if isinstance(exc, AgentConfigConflict):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
            raise
        policies = config.policies

    # Refresh any warm worker AgentLoader cache so the new whitelist applies
    # on the next turn. Best-effort — the cache also expires on its own.
    try:
        from nexus_api.api.admin.agent_configs import PROMOTE_CHANNEL

        await redis.publish(PROMOTE_CHANNEL, str(tenant_id))
    except Exception as exc:  # pragma: no cover - stale-cache risk only
        log.warning(
            "partner.admins.promote_publish_failed", tenant_id=str(tenant_id), error=str(exc)
        )

    return _admins_out(policies)


def _admins_out(policies: dict | None) -> AdminsOut:
    access = (policies or {}).get("admin_access") or {}
    phones = [str(p) for p in (access.get("admin_phones") or [])]
    meta = {str(a.get("phone")): a for a in (access.get("admins") or []) if isinstance(a, dict)}
    out: list[AdminOut] = []
    for p in phones:
        entry = meta.get(p) or {}
        role = str(entry.get("role") or "full").lower()
        out.append(
            AdminOut(
                phone=p,
                name=entry.get("name"),
                role="readonly" if role == "readonly" else "full",
            )
        )
    return AdminsOut(admin_only=bool(access.get("admin_only")), admins=out)


__all__ = ["router"]
