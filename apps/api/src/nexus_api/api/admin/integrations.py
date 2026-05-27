"""Admin endpoints for external integrations.

AgendaPro (ADR-017): public-link only. The agent uses the tenant's
public AgendaPro URL (e.g. ``cultorbarber.site.agendapro.com``) to
check availability and create appointments via the new public browser
MCP. Modify / cancel / get_appointments are escalated to the owner via
the backchannel (ADR-018) — the public flow doesn't support them.

The legacy admin/credential-based flow (browser automation of the
AgendaPro admin panel) was deprecated and removed in migration 0021.
No production tenant was using it.

WhatsApp (Block J): manual wizard against YCloud — operator pastes
waba_id + phone_number_id, backend verifies + upserts the Channel.

Both flows require Bearer admin token.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from nexus_channels.whatsapp_ycloud.ycloud_client import YCloudAPIError, YCloudClient
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import scoped_session_from_path
from nexus_api.config import get_settings
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    Tenant,
)

router = APIRouter()
log = structlog.get_logger()


# ── AgendaPro public-link setup ────────────────────────────────────────────


class AgendaProPublicUrlIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Empty string clears the field; ``null`` does the same. Pydantic
    # coerces both via the validator below.
    public_url: str | None = Field(default=None, max_length=500)


class AgendaProPublicUrlOut(BaseModel):
    integration: str
    public_url: str | None
    updated_at: datetime
    audit_log_id: uuid.UUID


@router.patch(
    "/tenants/{tenant_id}/integrations/agendapro/public-url",
    response_model=AgendaProPublicUrlOut,
)
async def set_agendapro_public_url(
    tenant_id: uuid.UUID,
    body: AgendaProPublicUrlIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> AgendaProPublicUrlOut:
    """Set (or clear) the tenant's public AgendaPro URL.

    The new public browser MCP reads this column when invoking
    ``booking.check_availability`` and ``booking.create_appointment``.
    Cancel / modify / get_appointments are out of scope for the public
    flow and the agent escalates them to the owner via the backchannel.
    """
    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"tenant {tenant_id} not found",
        )

    raw = (body.public_url or "").strip() or None
    # Minimal sanity check — the public browser MCP will probe the URL
    # itself before scraping. Reject anything that doesn't look like an
    # http(s) URL up front so the operator sees the typo here.
    if raw is not None and not raw.startswith(("https://", "http://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL pública debe arrancar con https:// o http://",
        )

    before = tenant.agendapro_public_url
    tenant.agendapro_public_url = raw
    audit = AuditLog(
        tenant_id=tenant_id,
        actor=f"admin:{actor[:8]}",
        action="integration.agendapro.public_url",
        target=f"tenant:{tenant_id}",
        before_json={"public_url": before},
        after_json={"public_url": raw},
    )
    session.add(audit)
    await session.flush()
    return AgendaProPublicUrlOut(
        integration="agendapro",
        public_url=raw,
        updated_at=datetime.now(UTC),
        audit_log_id=audit.id,
    )


# ── WhatsApp manual setup (Block J) ────────────────────────────────────────
#
# Phase 1 onboarding: Lee/owner crea la WABA en el YCloud dashboard, copia
# waba_id + phone_number_id, y los pega en el wizard del panel. El backend
# confirma los IDs contra YCloud (GET /v2/whatsapp/phoneNumbers/...) y crea
# la fila ``Channel`` con provider_identifier=<E.164> + config={waba_id,
# phone_number_id, display_name, verified_name, quality_rating}. Sin
# Embedded Signup (decisión locked al cierre del Bloque H — patrón derivado
# de restaurant-ai/api/src/routes/admin/whatsapp-setup.ts).
#
# El UNIQUE(type, provider_identifier) en `channels` es global: dos tenants
# no pueden compartir el mismo E.164. Ese es el invariante correcto para
# Phase 1 — el webhook YCloud rutea por business phone.


class WhatsAppVerifyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone_number: str
    # ``phone_number_id`` may be empty when the operator paired only the
    # WABA (YCloud's SMB onboarding doesn't always surface the phone_number_id
    # in its UI; the platform falls back to the WABA-level listing endpoint
    # and persists whatever id YCloud returns — empty if none). The webhook
    # and outbound paths never use phone_number_id; tenant resolution is by
    # ``provider_identifier`` (E.164). Keeping the field so the UI can show
    # it when present and skip the field when not, without breaking older
    # clients.
    phone_number_id: str = ""
    waba_id: str
    display_name: str | None
    verified_name: str | None
    quality_rating: str | None


class WhatsAppConnectManualIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    waba_id: str = Field(min_length=1, max_length=64)
    # Optional. Leave empty (or omit) when YCloud's UI doesn't expose the
    # Meta phone_number_id under the SMB tier; the backend resolves the
    # single phone registered under the WABA via the listing endpoint and
    # persists whatever ``id`` YCloud returns (often empty). Outbound sends
    # route by E.164 (the ``from`` field of ``sendDirectly`` is the business
    # phone), so an empty phone_number_id is functional.
    #
    # When provided, must be the Meta-side numeric identifier — NOT the
    # phone number itself. The validator below rejects E.164-looking
    # values up front so the operator sees the typo before YCloud does.
    phone_number_id: str = Field(default="", max_length=64)

    @field_validator("phone_number_id")
    @classmethod
    def _validate_phone_number_id(cls, value: str) -> str:
        return _normalize_phone_number_id(value)


class WhatsAppConnectOut(BaseModel):
    status: str
    channel_id: uuid.UUID
    phone_number: str
    # Same rationale as WhatsAppVerifyOut.phone_number_id — may be empty.
    phone_number_id: str = ""
    waba_id: str
    display_name: str | None
    verified_name: str | None
    quality_rating: str | None
    audit_log_id: uuid.UUID


# Meta phone_number_id is a numeric identifier (15–16 digits in practice,
# but YCloud has surfaced shorter/longer forms historically). Anything
# that doesn't look numeric — most commonly an E.164 the operator pasted
# into the wrong field — is rejected with a clear message before we
# round-trip to YCloud.
_PHONE_NUMBER_ID_RE = re.compile(r"^\d{1,32}$")


def _normalize_phone_number_id(value: str | None) -> str:
    """Trim and validate the optional ``phone_number_id`` input.

    Empty / None → ``""`` (backend resolves via WABA listing fallback).
    Non-empty → must match ``^\\d+$``. Common operator mistake:
    pasting the E.164 phone (``+34632719028``) into the phone_number_id
    field. YCloud sometimes 200s on that path (soft-match) but the ``id``
    it returns is not round-trippable, breaking the subsequent connect
    call. Catch it here so the operator gets an actionable error.
    """
    raw = (value or "").strip()
    if not raw:
        return ""
    if not _PHONE_NUMBER_ID_RE.fullmatch(raw):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "phone_number_id no es un número de teléfono — es un "
                "identificador numérico de Meta. Si tu dashboard de YCloud "
                "no lo muestra, dejá el campo vacío y el backend resuelve "
                "el número registrado en la WABA."
            ),
        )
    return raw


def _reconcile_phone_number_id(
    *,
    operator_input: str,
    ycloud_id: str,
    waba_id: str,
) -> str:
    """Resolve the canonical ``phone_number_id`` to persist.

    Trust order: whatever YCloud returned in the payload (it's the
    canonical id, even when the operator pasted the phone number itself
    and YCloud soft-matched it) > what the operator typed > ``""``.

    Logs a warning when the inputs diverge so we have a paper trail of
    operator typos.
    """
    canonical = (ycloud_id or "").strip()
    if canonical and operator_input and operator_input != canonical:
        log.warning(
            "whatsapp.phone_number_id.mismatch",
            waba_id=waba_id,
            operator_input=operator_input,
            canonical=canonical,
        )
    return canonical or operator_input or ""


def _build_ycloud_client() -> YCloudClient:
    """Override target for tests via ``app.dependency_overrides``.

    Phase 1 reuses the BSP-level API key (Auphere is the YCloud customer);
    per-tenant keys are a Phase 4+ white-label concern.
    """
    settings = get_settings()
    return YCloudClient(api_key=settings.ycloud_api_key, base_url=settings.ycloud_api_base_url)


def _phone_info_to_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalise the YCloud ``phoneNumbers/{id}`` response.

    YCloud's response shape mirrors Meta's GraphAPI; field names alternate
    between camelCase and snake_case across YCloud versions, so we accept
    both. The keys we surface to the wizard are: phone_number (E.164),
    display_name, verified_name, quality_rating, and phone_number_id (when
    YCloud chose to surface it — empty otherwise).
    """
    phone_number = (
        payload.get("phoneNumber")
        or payload.get("phone_number")
        or payload.get("display_phone_number")
    )
    phone_number_id = (
        payload.get("phoneNumberId") or payload.get("phone_number_id") or payload.get("id") or ""
    )
    return {
        "phone_number": phone_number,
        "phone_number_id": str(phone_number_id) if phone_number_id else "",
        "display_name": payload.get("displayName") or payload.get("display_name"),
        "verified_name": payload.get("verifiedName") or payload.get("verified_name"),
        "quality_rating": payload.get("qualityRating") or payload.get("quality_rating"),
    }


def _ycloud_error_to_http(exc: YCloudAPIError, *, context: str) -> HTTPException:
    """Map a YCloud transport/HTTP error to a useful operator message.

    The three common cases:
      - 401: BSP API key rotated/wrong → admin must check Doppler.
      - 403: BSP key has no permission on this WABA → owner shared the
        wrong account, or coexistence not bound yet.
      - 404: waba_id or phone_number_id is wrong → typo in the wizard.
    """
    if exc.status_code == 401:
        detail = (
            "YCloud rechazó la llamada como no autenticada (401). "
            "Verificar NEXUS_YCLOUD_API_KEY en Doppler."
        )
    elif exc.status_code == 403:
        detail = (
            "YCloud devolvió 403: la API key no tiene permisos sobre esta "
            "WABA. Confirmar que el owner agregó a Auphere como Tech "
            "Provider en su Facebook Business y que YCloud bindeó la WABA."
        )
    elif exc.status_code == 404:
        detail = (
            "YCloud no encontró el par (waba_id, phone_number_id). "
            "Revisar que los IDs estén copiados sin espacios y que el "
            "número esté registrado en la WABA."
        )
    elif exc.status_code == 0:
        detail = f"YCloud transport error ({context}): {exc.message}"
    else:
        detail = f"YCloud {exc.status_code} ({context}): {exc.message}"
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


@router.get(
    "/integrations/whatsapp/verify",
    response_model=WhatsAppVerifyOut,
    dependencies=[Depends(require_admin_token)],
)
async def verify_whatsapp(
    waba_id: str = Query(..., min_length=1, max_length=64),
    phone_number_id: str = Query(default="", max_length=64),
) -> WhatsAppVerifyOut:
    """Dry-run probe of the WABA against YCloud.

    The wizard calls this BEFORE the connect step so Lee sees a preview
    (E.164 + display_name + quality_rating) and can confirm. No DB writes.

    When ``phone_number_id`` is omitted (empty string) the client falls
    back to the WABA-level listing endpoint and resolves the single
    registered phone — necessary because YCloud's SMB UI doesn't always
    expose the Meta phone_number_id. When provided, it must look like a
    Meta-side numeric id (see :func:`_normalize_phone_number_id`).
    """
    normalized_input = _normalize_phone_number_id(phone_number_id)
    client = _build_ycloud_client()
    try:
        try:
            payload = await client.get_phone_number(
                waba_id=waba_id,
                phone_number_id=normalized_input or None,
            )
        except YCloudAPIError as exc:
            raise _ycloud_error_to_http(exc, context="get_phone_number") from exc
    finally:
        await client.close()
    summary = _phone_info_to_summary(payload)
    if not summary["phone_number"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="YCloud devolvió una respuesta sin phoneNumber — verificar IDs",
        )
    resolved_phone_id = _reconcile_phone_number_id(
        operator_input=normalized_input,
        ycloud_id=summary["phone_number_id"],
        waba_id=waba_id,
    )
    return WhatsAppVerifyOut(
        phone_number=summary["phone_number"],
        phone_number_id=resolved_phone_id,
        waba_id=waba_id,
        display_name=summary["display_name"],
        verified_name=summary["verified_name"],
        quality_rating=summary["quality_rating"],
    )


@router.post(
    "/tenants/{tenant_id}/integrations/whatsapp/connect-manual",
    response_model=WhatsAppConnectOut,
    status_code=status.HTTP_201_CREATED,
)
async def connect_whatsapp_manual(
    tenant_id: uuid.UUID,
    body: WhatsAppConnectManualIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> WhatsAppConnectOut:
    """Verify (waba_id, phone_number_id) against YCloud + upsert Channel.

    The DB invariant ``UNIQUE(type, provider_identifier)`` is global, so
    if the same E.164 already maps to a different tenant we return 409.
    """
    # The Pydantic model already ran ``_normalize_phone_number_id`` on
    # ``body.phone_number_id`` via the field validator, so anything that
    # looks like an E.164 has already been rejected with 400.
    client = _build_ycloud_client()
    try:
        try:
            payload = await client.get_phone_number(
                waba_id=body.waba_id,
                phone_number_id=body.phone_number_id or None,
            )
        except YCloudAPIError as exc:
            raise _ycloud_error_to_http(exc, context="get_phone_number") from exc
    finally:
        await client.close()

    summary = _phone_info_to_summary(payload)
    phone_number = summary["phone_number"]
    if not phone_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="YCloud devolvió una respuesta sin phoneNumber — verificar IDs",
        )
    resolved_phone_id = _reconcile_phone_number_id(
        operator_input=body.phone_number_id,
        ycloud_id=summary["phone_number_id"],
        waba_id=body.waba_id,
    )

    # Look for an existing whatsapp Channel under THIS tenant. If present,
    # update in place (idempotent re-connect of the same number). If a
    # different tenant already owns this E.164, the UNIQUE constraint trips.
    stmt = select(Channel).where(
        Channel.tenant_id == tenant_id, Channel.type == ChannelType.WHATSAPP
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()

    config_payload = {
        "waba_id": body.waba_id,
        "phone_number_id": resolved_phone_id,
        "display_name": summary["display_name"],
        "verified_name": summary["verified_name"],
        "quality_rating": summary["quality_rating"],
    }

    if existing is not None:
        before = {
            "provider_identifier": existing.provider_identifier,
            "config": dict(existing.config),
            "status": existing.status.value,
        }
        existing.provider_identifier = phone_number
        existing.config = config_payload
        existing.status = ChannelStatus.ACTIVE
        channel = existing
        before_json: dict[str, Any] | None = before
    else:
        channel = Channel(
            tenant_id=tenant_id,
            type=ChannelType.WHATSAPP,
            provider="ycloud",
            provider_identifier=phone_number,
            config=config_payload,
            status=ChannelStatus.ACTIVE,
        )
        session.add(channel)
        before_json = None

    try:
        await session.flush()
    except IntegrityError as exc:
        # The global UNIQUE(type, provider_identifier) tripped. Another
        # tenant already owns this E.164. The migration path is operator-
        # documented in RUNBOOK ("Cómo migrar un número entre tenants").
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"el número {phone_number} ya está conectado a otro tenant; "
                f"si es una migración, primero desconectarlo del tenant anterior"
            ),
        ) from exc

    audit = AuditLog(
        tenant_id=tenant_id,
        actor=f"admin:{actor[:8]}",
        action="channel.whatsapp.connect_manual",
        target=f"channel:{channel.id}",
        before_json=before_json,
        after_json={
            "phone_number": phone_number,
            "config": config_payload,
            "channel_id": str(channel.id),
        },
    )
    session.add(audit)
    await session.flush()

    return WhatsAppConnectOut(
        status="connected",
        channel_id=channel.id,
        phone_number=phone_number,
        phone_number_id=resolved_phone_id,
        waba_id=body.waba_id,
        display_name=summary["display_name"],
        verified_name=summary["verified_name"],
        quality_rating=summary["quality_rating"],
        audit_log_id=audit.id,
    )


# Compatibility export — admin/__init__.py importa "router".
__all__ = ["router"]


# Ensure proper UTC import is used in default factories above (no-op alias).
_ = UTC
