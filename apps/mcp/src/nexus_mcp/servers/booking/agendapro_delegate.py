"""Helper que centraliza la delegación booking-server → agendapro.*.

Cuando un tenant tiene integration AgendaPro activa (fila en
``tenant_credentials`` con ``integration='agendapro'`` y
``needs_reauth=False``), las tools mutativas del booking-server
(``create_appointment``, ``modify_appointment``, ``cancel_appointment``)
delegan a ``agendapro.*`` ANTES de persistir local. La fila local en
``appointments`` queda como shadow cache con ``external_ref`` apuntando
al id de AgendaPro.

Si AgendaPro retorna ``needs_reauth=True`` (sesión expirada), el helper
flippea el flag en ``tenant_credentials`` y propaga ``ToolError``. La
transacción local rollbackea — no se crea fila huérfana sin external_ref.

Idempotency: el server Node compone su key internamente
(``auphere_<tenant_id>_<intent_hash>``); acá derivamos ``intent_hash``
del ``idempotency_key`` que el caller proporcionó (sha256 hex truncado a
40 chars).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any

import structlog
from nexus_api.db.models import AuditLog
from nexus_api.services.agendapro_credentials import (
    AgendaProCredentials,
    get_agendapro_credentials,
    mark_agendapro_health_check,
)
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_mcp.base import ToolError

log = structlog.get_logger(__name__)


def derive_intent_hash(idempotency_key: str) -> str:
    """40 caracteres hex (sha256 truncado) — alfanumérico, matchea el
    regex que ``composeIdempotencyKey`` valida del lado Node."""
    return hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:40]


async def get_active_credentials(
    session: AsyncSession,
) -> AgendaProCredentials | None:
    """Retorna las credenciales solo si la integration está usable.
    None si no existe o si ``needs_reauth=True``."""
    creds = await get_agendapro_credentials(session)
    if creds is None or creds.needs_reauth:
        return None
    return creds


async def _dispatch_agendapro(
    *,
    name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    from nexus_mcp.registry import (
        build_default_registry,
        get_internal_caller_token,
    )

    registry = build_default_registry()
    envelope = await registry.dispatch_internal(
        name,
        args,
        caller_token=get_internal_caller_token(),
    )
    return envelope


async def _handle_session_status(
    session: AsyncSession,  # noqa: ARG001 — kept for API symmetry; flag is persisted in a separate session
    *,
    result: dict[str, Any],
    tenant_id: uuid.UUID,
) -> None:
    """Si el server reportó ``needs_reauth=True``, flippea el flag en
    una transacción SEPARADA (commit) antes de raise ToolError, para que
    el flag sobreviva al rollback de la transacción local actual.
    """
    session_status = result.get("session") or {}
    if not session_status.get("needs_reauth"):
        return

    # Open an independent session + tenant scope so the flag commit is
    # NOT affected by the outer rollback when ToolError propagates.
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker

    sm = get_sessionmaker()
    async with sm() as flag_session, tenant_scoped_session(flag_session, tenant_id):
        await mark_agendapro_health_check(
            flag_session,
            needs_reauth=True,
            checked_at=_now(),
        )
    log.warning(
        "agendapro.session_expired_during_call",
        tenant_id=str(tenant_id),
    )
    raise ToolError(
        "agendapro session expired and needs reauth — operator must "
        "re-bootstrap the integration"
    )


def _now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)


async def write_audit_with_screenshot(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    action: str,
    target: str,
    screenshot: dict[str, Any] | None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Persiste un audit_log row con la screenshot_url devuelta por el
    server Node. ``screenshot`` es el dict ``ScreenshotMeta`` del
    output."""
    after: dict[str, Any] = {}
    if screenshot:
        after["screenshot_url"] = screenshot.get("screenshot_url")
        after["screenshot_failed"] = screenshot.get("screenshot_failed", False)
        if screenshot.get("screenshot_error"):
            after["screenshot_error"] = screenshot["screenshot_error"]
    if extra:
        after.update(extra)
    audit = AuditLog(
        tenant_id=tenant_id,
        actor="system:booking-server",
        action=action,
        target=target,
        before_json=None,
        after_json=after,
    )
    session.add(audit)
    await session.flush()


async def delegate_create(
    session: AsyncSession,
    *,
    creds: AgendaProCredentials,
    tenant_id: uuid.UUID,
    starts_at: datetime,
    duration_min: int,
    service_name: str,
    barber_external_id: str | None,
    customer_name: str,
    customer_phone: str,
    customer_email: str | None,
    notes: str | None,
    idempotency_key: str,
) -> dict[str, Any]:
    """Invoca agendapro.create_appointment. Retorna el ``result`` dict
    del envelope. Lanza ``ToolError`` si needs_reauth o falla."""
    args = {
        "context_id": creds.context_id,
        "intent_hash": derive_intent_hash(idempotency_key),
        "starts_at": starts_at.isoformat(),
        "duration_min": duration_min,
        "service_name": service_name,
        "barber_external_id": barber_external_id,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "customer_email": customer_email,
        "notes": notes,
    }
    envelope = await _dispatch_agendapro(name="agendapro.create_appointment", args=args)
    result: dict[str, Any] = envelope["result"]
    await _handle_session_status(session, result=result, tenant_id=tenant_id)
    return result


async def delegate_modify(
    session: AsyncSession,
    *,
    creds: AgendaProCredentials,
    tenant_id: uuid.UUID,
    external_ref: str,
    new_starts_at: datetime | None,
    new_duration_min: int | None,
    new_barber_external_id: str | None,
    new_service_name: str | None,
) -> dict[str, Any]:
    args = {
        "context_id": creds.context_id,
        "external_ref": external_ref,
        "new_starts_at": new_starts_at.isoformat() if new_starts_at else None,
        "new_duration_min": new_duration_min,
        "new_barber_external_id": new_barber_external_id,
        "new_service_name": new_service_name,
    }
    envelope = await _dispatch_agendapro(name="agendapro.modify_appointment", args=args)
    result: dict[str, Any] = envelope["result"]
    await _handle_session_status(session, result=result, tenant_id=tenant_id)
    return result


async def delegate_cancel(
    session: AsyncSession,
    *,
    creds: AgendaProCredentials,
    tenant_id: uuid.UUID,
    external_ref: str,
    reason: str | None,
) -> dict[str, Any]:
    args = {
        "context_id": creds.context_id,
        "external_ref": external_ref,
        "reason": reason,
    }
    envelope = await _dispatch_agendapro(name="agendapro.cancel_appointment", args=args)
    result: dict[str, Any] = envelope["result"]
    await _handle_session_status(session, result=result, tenant_id=tenant_id)
    return result
