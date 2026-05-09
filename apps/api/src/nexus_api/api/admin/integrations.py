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
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import scoped_session_from_path
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import AuditLog
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


# Compatibility export — admin/__init__.py importa "router".
__all__ = ["router"]


# Ensure proper UTC import is used in default factories above (no-op alias).
_ = UTC
