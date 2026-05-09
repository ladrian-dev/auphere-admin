"""Service: run an AgendaPro health-check inside an open tenant session.

Block E shipped the admin endpoint
``POST /admin/.../integrations/agendapro/health-check``. Block H needs
to invoke the same logic from the worker's hourly cron — outside an
HTTP request — so we extract the meaty work here. The endpoint becomes
a thin wrapper; the cron calls this directly with
``actor='system:health_check_cron'``.

Caller responsibilities:
- Open a ``tenant_scoped_session`` (RLS applied).
- Provide an ``actor`` string for the audit log.

The service does NOT commit — the caller controls the transaction
boundary so an admin endpoint can include the audit_log row in the
same transaction as the credentials update.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import AuditLog
from nexus_api.services.agendapro_credentials import (
    get_agendapro_credentials,
    mark_agendapro_health_check,
    update_agendapro_context_id,
)

log = structlog.get_logger()


class AgendaProNotConfigured(Exception):
    """Tenant has no agendapro credentials. Caller decides 404 vs skip."""


@dataclass
class HealthCheckResult:
    healthy: bool
    relogin_attempted: bool
    relogin_succeeded: bool
    needs_reauth: bool
    checked_at: datetime
    notes: str | None
    new_context_id_persisted: bool
    audit_log_id: uuid.UUID | None  # set when needs_reauth flipped


async def _dispatch_internal(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Lazy import to avoid pulling MCP graph at module import time."""
    from nexus_mcp import build_default_registry, get_internal_caller_token

    registry = build_default_registry()
    envelope: dict[str, Any] = await registry.dispatch_internal(
        name,
        args,
        caller_token=get_internal_caller_token(),
    )
    return envelope


async def run_agendapro_health_check(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    actor: str,
) -> HealthCheckResult:
    """Verify the AgendaPro context. Auto-relogin if expired. Flip
    ``needs_reauth`` when re-login also fails and emit the audit row
    that the operator alerter consumes.

    Raises ``AgendaProNotConfigured`` when the tenant has no creds.
    """
    creds = await get_agendapro_credentials(session)
    if creds is None:
        raise AgendaProNotConfigured

    envelope = await _dispatch_internal(
        "agendapro._health_check",
        {
            "context_id": creds.context_id,
            "login_for_relogin": creds.login,
            "password_for_relogin": creds.password,
            "business_url": creds.business_url,
        },
    )
    result = envelope["result"]
    healthy = bool(result["healthy"])
    needs_reauth = bool(result["needs_reauth"])
    new_context_id: str | None = result.get("new_context_id")
    checked_at = datetime.fromisoformat(result["checked_at"])

    new_persisted = False
    if new_context_id and new_context_id != creds.context_id:
        await update_agendapro_context_id(session, new_context_id=new_context_id)
        new_persisted = True

    await mark_agendapro_health_check(session, needs_reauth=needs_reauth, checked_at=checked_at)

    audit_id: uuid.UUID | None = None
    if needs_reauth:
        audit = AuditLog(
            tenant_id=tenant_id,
            actor=actor[:255],
            action="integration.agendapro.needs_reauth",
            target=f"tenant:{tenant_id}",
            before_json=None,
            after_json={
                "checked_at": checked_at.isoformat(),
                "notes": result.get("notes"),
                "relogin_attempted": result.get("relogin_attempted"),
            },
        )
        session.add(audit)
        await session.flush()
        audit_id = audit.id
        log.warning(
            "agendapro.needs_reauth",
            tenant_id=str(tenant_id),
            notes=result.get("notes"),
            actor=actor,
        )

    return HealthCheckResult(
        healthy=healthy,
        relogin_attempted=bool(result.get("relogin_attempted")),
        relogin_succeeded=bool(result.get("relogin_succeeded")),
        needs_reauth=needs_reauth,
        checked_at=checked_at,
        notes=result.get("notes"),
        new_context_id_persisted=new_persisted,
        audit_log_id=audit_id,
    )
