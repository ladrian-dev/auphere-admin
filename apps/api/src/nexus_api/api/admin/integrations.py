"""Admin endpoints para integraciones externas (Bloque E: AgendaPro).

POST /admin/tenants/:id/integrations/agendapro/bootstrap
    Body: { login, password, business_url? }
    Acción: invoca agendapro._bootstrap_session via dispatch_internal,
    persiste payload encriptado + context_id en tenant_credentials,
    escribe row en audit_log.

POST /admin/tenants/:id/integrations/agendapro/health-check
    Sin body. Lee credenciales, invoca agendapro._health_check pasando
    login/password para que el server intente re-login auto si el
    context expiró. Persiste new_context_id si vino, flippea
    needs_reauth si re-login también falló (y dispara
    escalate.escalate_to_human).

Ambos endpoints exigen Bearer admin token. El service_caller_token para
dispatch_internal sale de ``get_internal_caller_token()``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from nexus_channels.whatsapp_ycloud.ycloud_client import YCloudAPIError, YCloudClient
from pydantic import BaseModel, ConfigDict, Field
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
)
from nexus_api.services.agendapro_credentials import (
    upsert_agendapro_credentials,
)
from nexus_api.services.agendapro_health import (
    AgendaProNotConfigured,
    run_agendapro_health_check,
)

router = APIRouter()
log = structlog.get_logger()


# ── request bodies ──────────────────────────────────────────────────────────


class AgendaProBootstrapIn(BaseModel):
    login: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=200)
    business_url: str | None = Field(default=None, max_length=500)


class AgendaProBootstrapOut(BaseModel):
    integration: str
    context_id: str
    bootstrap_at: datetime
    screenshot_url: str | None
    audit_log_id: uuid.UUID


class AgendaProHealthCheckOut(BaseModel):
    healthy: bool
    relogin_attempted: bool
    relogin_succeeded: bool
    needs_reauth: bool
    checked_at: datetime
    notes: str | None
    new_context_id_persisted: bool


# ── shared helpers ──────────────────────────────────────────────────────────


async def _dispatch_internal_for_admin(
    *,
    name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Wrapper que importa lazy y resuelve registry + caller_token.

    Las imports lazy evitan que el módulo de admin importe en cascada el
    registry MCP (que carga 21 tools y wirea Redis al import-time vía
    el factory de transport).
    """
    from nexus_mcp import build_default_registry, get_internal_caller_token

    registry = build_default_registry()
    envelope: dict[str, Any] = await registry.dispatch_internal(
        name,
        args,
        caller_token=get_internal_caller_token(),
    )
    return envelope


# ── endpoints ───────────────────────────────────────────────────────────────


@router.post(
    "/tenants/{tenant_id}/integrations/agendapro/bootstrap",
    response_model=AgendaProBootstrapOut,
    status_code=status.HTTP_201_CREATED,
)
async def bootstrap_agendapro(
    tenant_id: uuid.UUID,
    body: AgendaProBootstrapIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> AgendaProBootstrapOut:
    """Login a AgendaPro, captura context_id, persiste credenciales
    encriptadas + context_id en tenant_credentials.
    """
    try:
        envelope = await _dispatch_internal_for_admin(
            name="agendapro._bootstrap_session",
            args={
                "login": body.login,
                "password": body.password,
                "business_url": body.business_url,
            },
        )
    except Exception as exc:
        log.exception(
            "agendapro.bootstrap_failed",
            tenant_id=str(tenant_id),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"agendapro bootstrap failed: {exc}",
        ) from exc

    result = envelope["result"]
    context_id = result["context_id"]
    screenshot = result.get("screenshot") or {}
    bootstrap_at = datetime.fromisoformat(result["bootstrap_at"])

    await upsert_agendapro_credentials(
        session,
        login=body.login,
        password=body.password,
        context_id=context_id,
        business_url=body.business_url,
    )
    audit = AuditLog(
        tenant_id=tenant_id,
        actor=f"admin:{actor[:8]}",
        action="integration.agendapro.bootstrap",
        target=f"tenant:{tenant_id}",
        before_json=None,
        after_json={
            "integration": "agendapro",
            "context_id": context_id,
            "screenshot_url": screenshot.get("screenshot_url"),
            "screenshot_failed": screenshot.get("screenshot_failed", False),
        },
    )
    session.add(audit)
    await session.flush()
    return AgendaProBootstrapOut(
        integration="agendapro",
        context_id=context_id,
        bootstrap_at=bootstrap_at,
        screenshot_url=screenshot.get("screenshot_url"),
        audit_log_id=audit.id,
    )


@router.post(
    "/tenants/{tenant_id}/integrations/agendapro/health-check",
    response_model=AgendaProHealthCheckOut,
)
async def health_check_agendapro(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> AgendaProHealthCheckOut:
    """Verifica el context AgendaPro. Auto-relogin si expiró. Si
    re-login falla → flippea ``needs_reauth=True`` + escribe audit_log
    que el operator alerter convierte en notification al operador."""
    try:
        result = await run_agendapro_health_check(session, tenant_id, actor=f"admin:{actor[:8]}")
    except AgendaProNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="tenant has no agendapro integration; bootstrap first",
        ) from exc
    return AgendaProHealthCheckOut(
        healthy=result.healthy,
        relogin_attempted=result.relogin_attempted,
        relogin_succeeded=result.relogin_succeeded,
        needs_reauth=result.needs_reauth,
        checked_at=result.checked_at,
        notes=result.notes,
        new_context_id_persisted=result.new_context_id_persisted,
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
    phone_number_id: str
    waba_id: str
    display_name: str | None
    verified_name: str | None
    quality_rating: str | None


class WhatsAppConnectManualIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    waba_id: str = Field(min_length=1, max_length=64)
    phone_number_id: str = Field(min_length=1, max_length=64)


class WhatsAppConnectOut(BaseModel):
    status: str
    channel_id: uuid.UUID
    phone_number: str
    phone_number_id: str
    waba_id: str
    display_name: str | None
    verified_name: str | None
    quality_rating: str | None
    audit_log_id: uuid.UUID


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
    display_name, verified_name, quality_rating.
    """
    phone_number = (
        payload.get("phoneNumber")
        or payload.get("phone_number")
        or payload.get("display_phone_number")
    )
    return {
        "phone_number": phone_number,
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
    phone_number_id: str = Query(..., min_length=1, max_length=64),
) -> WhatsAppVerifyOut:
    """Dry-run probe of (waba_id, phone_number_id) against YCloud.

    The wizard calls this BEFORE the connect step so Lee sees a preview
    (E.164 + display_name + quality_rating) and can confirm. No DB writes.
    """
    client = _build_ycloud_client()
    try:
        try:
            payload = await client.get_phone_number(
                waba_id=waba_id, phone_number_id=phone_number_id
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
    return WhatsAppVerifyOut(
        phone_number=summary["phone_number"],
        phone_number_id=phone_number_id,
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
    client = _build_ycloud_client()
    try:
        try:
            payload = await client.get_phone_number(
                waba_id=body.waba_id, phone_number_id=body.phone_number_id
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

    # Look for an existing whatsapp Channel under THIS tenant. If present,
    # update in place (idempotent re-connect of the same number). If a
    # different tenant already owns this E.164, the UNIQUE constraint trips.
    stmt = select(Channel).where(
        Channel.tenant_id == tenant_id, Channel.type == ChannelType.WHATSAPP
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()

    config_payload = {
        "waba_id": body.waba_id,
        "phone_number_id": body.phone_number_id,
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
        phone_number_id=body.phone_number_id,
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
