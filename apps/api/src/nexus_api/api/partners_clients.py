"""Partner self-serve for a client's WhatsApp line + admin whitelist.

``/v1/partners/clients/{external_client_ref}/…`` — server-to-server,
authenticated with the partner's secret API key. This is the whole
partner surface for one client: connect the WhatsApp line where its
agent lives, manage who administers it, read its onboarding state, and
send approved templates to its contacts — all from the partner's own
app, with no Auphere operator in the loop.

Two scopes, deliberately split: ``provision`` for the integration-time
capabilities (signup, admins, status) and ``broadcasts`` for messaging
the client's end customers.

Tenancy invariant: the tenant is ALWAYS resolved from ``partner_tenants`` under the authenticated partner — never
from the request body — so a partner can only ever touch its own clients.
An unknown ref is an opaque 404.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from nexus_channels.whatsapp_meta import SignupIngressPayload
from nexus_channels.whatsapp_meta.phone import to_e164
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.config import get_settings
from nexus_api.core import rate_limit
from nexus_api.core.partner_auth import PartnerContext, require_partner_key
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    ApiKeyScope,
    Channel,
    ChannelStatus,
    ChannelType,
    PartnerTenant,
    Tenant,
    TenantStatus,
)
from nexus_api.repositories.partner import EmbedAuditRepository, PartnerTenantRepository
from nexus_api.schemas.broadcasts import (
    BroadcastAcceptedOut,
    BroadcastCreateIn,
    BroadcastStatusOut,
    ClientTemplatesOut,
)
from nexus_api.services.agent_config_service import AgentConfigService
from nexus_api.services.broadcasts import create_broadcast, get_broadcast_status
from nexus_api.services.meta_signup_service import complete_meta_signup
from nexus_api.services.partner_provisioning import activate_tenant_if_ready
from nexus_api.services.whatsapp_templates import fetch_templates

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
    tenant_status: str = Field(
        description=(
            "Estado del cliente tras conectar. 'active' = el agente ya "
            "responde en esa línea; 'provisioning' = falta algo (ver "
            "activation_blocked_reason)."
        ),
    )
    tenant_activated: bool = Field(
        description="True si esta llamada fue la que activó al cliente.",
    )
    activation_blocked_reason: str | None = Field(
        default=None,
        description=(
            "Por qué el cliente sigue sin activarse: 'no_agent' (no tiene "
            "agente aún — reprovisionar), 'operator_review' (el partner no "
            "tiene auto_activate; lo activa un operador de Auphere)."
        ),
    )


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


class ClientStatusOut(BaseModel):
    """Everything the partner's UI needs to render a client's onboarding
    state without re-provisioning (which would rotate credentials)."""

    external_client_ref: str
    name: str
    timezone: str
    status: str = Field(
        description="Estado del cliente: provisioning | active | paused | archived."
    )
    whatsapp_connected: bool
    display_phone_number: str | None = None
    agent_configured: bool = Field(
        description="True si el cliente ya tiene un agente activo respondiendo.",
    )
    agent_version: int | None = None
    agent_seed_template: str | None = None
    admins_count: int
    ready: bool = Field(
        description="True cuando el agente ya puede atender: activo, con WhatsApp y con admins.",
    )
    missing: list[str] = Field(
        default_factory=list,
        description=(
            "Qué falta para que ``ready`` sea true: 'agent', 'whatsapp', 'admins', 'activation'."
        ),
    )


# ── helpers ─────────────────────────────────────────────────────────────────


async def _resolve_mapping(session: AsyncSession, ctx: PartnerContext, ref: str) -> PartnerTenant:
    """Mapping row behind ``ref`` for the authenticated partner, or opaque 404."""
    async with session.begin():
        mapping = await PartnerTenantRepository(session).get_mapping(ctx.partner.id, ref)
    if mapping is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown client reference",
        )
    return mapping


async def _resolve_tenant_id(session: AsyncSession, ctx: PartnerContext, ref: str) -> uuid.UUID:
    """Tenant behind ``ref`` for the authenticated partner, or opaque 404."""
    mapping = await _resolve_mapping(session, ctx, ref)
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

    Then, in the same transaction, runs ``activate_tenant_if_ready`` — the
    same handoff the iframe signup does. Without it a client provisioned
    and connected entirely from the partner's app would stay
    ``provisioning``, which the worker dispatcher treats as inactive: the
    number would be live and the agent silent, with nothing in the logs
    looking broken.
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
        activated = await activate_tenant_if_ready(
            session,
            partner=ctx.partner,
            tenant_id=tenant_id,
            api_key_id=ctx.api_key.id,
        )
        tenant = await session.get(Tenant, tenant_id)
        tenant_status = (
            tenant.status.value if tenant is not None else TenantStatus.PROVISIONING.value
        )
        blocked = None
        if tenant_status == TenantStatus.PROVISIONING.value:
            blocked = "operator_review" if not ctx.partner.auto_activate else "no_agent"

    result = bundle.result
    log.info(
        "partner.client_whatsapp_connected",
        partner=ctx.partner.slug,
        tenant_id=str(tenant_id),
        phone_number_id=result.phone_number_id,
        tenant_status=tenant_status,
        tenant_activated=activated,
    )
    return WhatsAppSignupOut(
        status="connected",
        waba_id=result.waba_id,
        phone_number_id=result.phone_number_id,
        display_phone_number=result.display_phone_number,
        mode=result.mode,
        bisuat_expires_at=(
            result.bisuat_expires_at.isoformat() if result.bisuat_expires_at is not None else None
        ),
        tenant_status=tenant_status,
        tenant_activated=activated,
        activation_blocked_reason=blocked,
    )


@router.get("/clients/{external_client_ref}", response_model=ClientStatusOut)
async def get_client_status(
    external_client_ref: str,
    ctx: PartnerContext = Depends(require_partner_key("provision")),
    session: AsyncSession = Depends(get_db_session),
) -> ClientStatusOut:
    """Read-only onboarding state of one client.

    The partner's UI needs this to decide what to show ("Conectar
    WhatsApp" vs. "Listo"). Re-POSTing ``/v1/partners/clients`` would
    answer part of it but also rotates the connector credentials, so
    polling that endpoint is the wrong tool.
    """
    mapping = await _resolve_mapping(session, ctx, external_client_ref)
    tenant_id = mapping.tenant_id

    async with tenant_scoped_session(session, tenant_id):
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:  # pragma: no cover - FK guarantees the row
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Unknown client reference",
            )
        active = await AgentConfigService(session).get_active()
        phone = await session.scalar(
            sa.select(Channel.provider_identifier)
            .where(
                Channel.type == ChannelType.WHATSAPP,
                Channel.status == ChannelStatus.ACTIVE,
            )
            .limit(1)
        )
        tenant_status = tenant.status.value
        tenant_name = tenant.name
        tenant_tz = tenant.timezone

    admins = _admins_out(active.policies if active else None)
    missing: list[str] = []
    if active is None:
        missing.append("agent")
    if phone is None:
        missing.append("whatsapp")
    if admins.admin_only and not admins.admins:
        missing.append("admins")
    if not missing and tenant_status != TenantStatus.ACTIVE.value:
        # Everything is in place but the tenant never flipped — an
        # operator has to review it (partner without ``auto_activate``)
        # or it was paused/archived on purpose.
        missing.append("activation")

    return ClientStatusOut(
        external_client_ref=external_client_ref,
        name=tenant_name,
        timezone=tenant_tz,
        status=tenant_status,
        whatsapp_connected=phone is not None,
        display_phone_number=phone,
        agent_configured=active is not None,
        agent_version=active.version if active else None,
        agent_seed_template=active.seed_template_ref if active else None,
        admins_count=len(admins.admins),
        ready=not missing,
        missing=missing,
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


@router.get("/clients/{external_client_ref}/templates", response_model=ClientTemplatesOut)
async def list_client_templates(
    external_client_ref: str,
    ctx: PartnerContext = Depends(require_partner_key(ApiKeyScope.BROADCASTS.value)),
    session: AsyncSession = Depends(get_db_session),
) -> ClientTemplatesOut:
    """APPROVED templates in THIS client's own WABA.

    Live read from Meta (the source of truth), filtered to APPROVED so the
    partner never offers a template that would be rejected at send time.
    Templates are per-WABA, so this is always the client's own catalogue.
    """
    tenant_id = await _resolve_tenant_id(session, ctx, external_client_ref)
    async with tenant_scoped_session(session, tenant_id):
        templates, _waba_id = await fetch_templates(session)
    approved = [t for t in templates if (t.status or "").upper() == "APPROVED"]
    return ClientTemplatesOut(templates=approved)


@router.post(
    "/clients/{external_client_ref}/broadcasts",
    response_model=BroadcastAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_client_broadcast(
    external_client_ref: str,
    body: BroadcastCreateIn,
    request: Request,
    response: Response,
    ctx: PartnerContext = Depends(require_partner_key(ApiKeyScope.BROADCASTS.value)),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> BroadcastAcceptedOut:
    """Send one approved template to 1..N of the client's contacts.

    ``202`` means queued and durable — the outbound dispatcher delivers,
    retries and tracks status; poll ``GET .../broadcasts/{id}``. A replay
    of the same ``idempotency_key`` returns ``200`` with the original
    result instead of sending twice.

    Guards, all inherited from the shared service so both surfaces behave
    identically: template must be APPROVED and LIVE in the client's WABA,
    named parameters only, opted-out recipients dropped, and the
    partner's ``broadcast_recipient_cap`` enforced per call.
    """
    if not await rate_limit.allow(
        redis,
        key=rate_limit.broadcast_bucket_key(str(ctx.partner.id)),
        per_minute=ctx.partner.rate_limit_embed_per_min,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for broadcasts",
        )

    tenant_id = await _resolve_tenant_id(session, ctx, external_client_ref)
    async with tenant_scoped_session(session, tenant_id):
        result, created = await create_broadcast(
            session,
            tenant_id=tenant_id,
            partner_id=ctx.partner.id,
            recipient_cap=ctx.partner.broadcast_recipient_cap,
            # No session JWT on this path — the API key is the actor, and
            # it is what the audit row records.
            jti=None,
            payload=body,
        )
        if created:
            await EmbedAuditRepository(session).record(
                event="broadcast.created",
                partner_id=ctx.partner.id,
                api_key_id=ctx.api_key.id,
                tenant_id=tenant_id,
                payload={
                    "broadcast_id": str(result.broadcast_id),
                    "template_name": body.template_name,
                    "accepted": result.accepted,
                    "rejected": len(result.rejected),
                },
                ip=request.client.host if request.client else None,
            )

    if not created:
        response.status_code = status.HTTP_200_OK
    log.info(
        "partner.broadcast_created",
        partner=ctx.partner.slug,
        tenant_id=str(tenant_id),
        broadcast_id=str(result.broadcast_id),
        accepted=result.accepted,
        rejected=len(result.rejected),
        replay=not created,
    )
    return result


@router.get(
    "/clients/{external_client_ref}/broadcasts/{broadcast_id}",
    response_model=BroadcastStatusOut,
)
async def get_client_broadcast(
    external_client_ref: str,
    broadcast_id: uuid.UUID,
    ctx: PartnerContext = Depends(require_partner_key(ApiKeyScope.BROADCASTS.value)),
    session: AsyncSession = Depends(get_db_session),
) -> BroadcastStatusOut:
    """Counters + per-recipient delivery state.

    A broadcast belonging to another client is a 404, not a 403: the read
    happens under this client's RLS scope, so other tenants' rows are not
    visible in the first place.
    """
    tenant_id = await _resolve_tenant_id(session, ctx, external_client_ref)
    async with tenant_scoped_session(session, tenant_id):
        return await get_broadcast_status(session, broadcast_id=broadcast_id)


def _admins_out(policies: dict[str, Any] | None) -> AdminsOut:
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
