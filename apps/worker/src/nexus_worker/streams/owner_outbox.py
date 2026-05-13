"""Owner outbox dispatcher.

Mirrors :mod:`nexus_worker.streams.outbound` but drains
``owner_consultations WHERE status='pending'`` instead of customer-side
messages. For each row:

1. Resolve the recipient owner phone via :class:`OwnerPhoneIndexRepository`.
2. Render the YCloud template with the row's stored params.
3. Send through :class:`WhatsAppYCloudAdapter`. The ``from_phone`` is the
   Auphere multi-tenant number (``settings.auphere_owner_phone``), NOT
   the tenant's business number — the owner sees Auphere talking to them,
   not their own business sending messages to itself.
4. On success: mark ``status='sent'``, persist ``ycloud_message_id`` so
   the inbound webhook can match an owner reply via ``quoted_message_id``.
5. On failure: increment a retry counter inside ``cancelled_reason``
   prefix and either retry the next tick or mark ``cancelled`` after
   :data:`MAX_ATTEMPTS`.

Tenant isolation: each row carries ``tenant_id`` and the dispatcher
enters :func:`tenant_scoped_session` BEFORE reading any tenant-scoped
table. The ``Tenant`` table itself is global (no RLS) and is read inside
the scoped session for convenience.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
import structlog
from nexus_api.config import get_settings
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import OwnerConsultation, OwnerPhoneIndex, Tenant
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from nexus_channels.whatsapp_ycloud.adapter import WhatsAppYCloudAdapter

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 1.0
DEFAULT_BATCH_SIZE = 25
MAX_ATTEMPTS = 5


async def run_owner_outbox_dispatcher(
    *,
    adapter: WhatsAppYCloudAdapter,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    """Background task. Returns when ``stop`` is set."""
    settings = get_settings()
    from_phone = settings.auphere_owner_phone
    if not from_phone:
        log.warning("owner_outbox.disabled.no_auphere_owner_phone")
        # Still loop — operator can set the env var without a restart in
        # dev. We just no-op until it's present.
    log.info(
        "owner_outbox.dispatcher.start",
        tick_seconds=tick_seconds,
        batch=batch_size,
        from_phone=from_phone,
    )
    sm = get_sessionmaker()
    while not stop.is_set():
        from_phone = get_settings().auphere_owner_phone
        if not from_phone:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
            continue
        try:
            tenant_ids = await _list_tenants_with_pending(sm)
            for tid in tenant_ids:
                if stop.is_set():
                    break
                await _drain_tenant(sm, tid, adapter, from_phone, batch_size)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("owner_outbox.dispatcher.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("owner_outbox.dispatcher.stopped")


async def _list_tenants_with_pending(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
) -> list[uuid.UUID]:
    """Cheap discovery query — RLS is bypassed because we read with the
    migration role here (no ``SET LOCAL ROLE`` issued). Returning the
    distinct list lets us scope the actual drains by tenant."""
    async with sm() as session:
        rows = await session.execute(
            sa.select(OwnerConsultation.tenant_id)
            .where(OwnerConsultation.status == "pending")
            .distinct()
        )
        return [row[0] for row in rows]


async def _drain_tenant(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
    tenant_id: uuid.UUID,
    adapter: WhatsAppYCloudAdapter,
    from_phone: str,
    batch_size: int,
) -> None:
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        # Fetch owner phone first — same scope, RLS-free (lookup table).
        phone_row = await session.execute(
            sa.select(OwnerPhoneIndex.phone_e164)
            .where(OwnerPhoneIndex.tenant_id == tenant_id)
            .where(OwnerPhoneIndex.active.is_(True))
            .order_by(OwnerPhoneIndex.added_at.asc())
            .limit(1)
        )
        owner_phone = phone_row.scalar_one_or_none()

        tenant_row = await session.get(Tenant, tenant_id)
        if tenant_row is None:  # pragma: no cover
            return

        rows = await session.execute(
            sa.select(OwnerConsultation)
            .where(OwnerConsultation.status == "pending")
            .order_by(OwnerConsultation.asked_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        pending = list(rows.scalars())
        if not pending:
            return
        log.info(
            "owner_outbox.dispatcher.batch",
            tenant_id=str(tenant_id),
            count=len(pending),
            has_owner_phone=bool(owner_phone),
        )
        for row in pending:
            await _send_one(
                session=session,
                row=row,
                adapter=adapter,
                from_phone=from_phone,
                recipient=owner_phone,
                tenant_name=tenant_row.name,
            )


async def _send_one(
    *,
    session: AsyncSession,
    row: OwnerConsultation,
    adapter: WhatsAppYCloudAdapter,
    from_phone: str,
    recipient: str | None,
    tenant_name: str,
) -> None:
    if recipient is None:
        row.status = "cancelled"
        row.cancelled_at = datetime.now(UTC)
        row.cancelled_reason = "no owner_phone_index for tenant"
        log.warning(
            "owner_outbox.cancelled.no_recipient",
            tenant_id=str(row.tenant_id),
            consultation_id=str(row.id),
        )
        return

    body_params = _body_params_for_template(row, tenant_name=tenant_name)
    try:
        result = await adapter.send_template(
            from_phone=from_phone,
            recipient=recipient,
            template_name=row.template_name,
            language="es",
            body_params=body_params,
            tenant_id=row.tenant_id,
            channel_id=uuid.UUID(int=0),  # backchannel — no per-tenant channel row
        )
    except Exception as exc:
        row.reminded_count += 1
        if row.reminded_count >= MAX_ATTEMPTS:
            row.status = "cancelled"
            row.cancelled_at = datetime.now(UTC)
            row.cancelled_reason = (
                f"dispatcher: send failed {row.reminded_count}x: {type(exc).__name__}: {exc}"
            )[:500]
            log.warning(
                "owner_outbox.permanent_failure",
                tenant_id=str(row.tenant_id),
                consultation_id=str(row.id),
                error=row.cancelled_reason,
            )
        else:
            log.info(
                "owner_outbox.retry",
                tenant_id=str(row.tenant_id),
                consultation_id=str(row.id),
                attempts=row.reminded_count,
                error=str(exc)[:200],
            )
        return

    row.status = "sent"
    row.sent_at = datetime.now(UTC)
    row.ycloud_message_id = result.provider_message_id
    log.info(
        "owner_outbox.sent",
        tenant_id=str(row.tenant_id),
        consultation_id=str(row.id),
        ycloud_message_id=row.ycloud_message_id,
    )


def _body_params_for_template(row: OwnerConsultation, *, tenant_name: str) -> dict[str, str]:
    """Render the YCloud body parameters dict for the row.

    Both Phase 1 templates (``auphere_owner_consult`` and
    ``auphere_owner_action_request``) were created in YCloud with
    **named** variables (not positional ``{{1}}…{{4}}``). The dict keys
    match the variable names registered in the template:

    - ``tenant_name`` — tenant business name
    - ``question`` — question / action description
    - ``urgency`` — urgency label (low / normal / high)
    - ``correlation_id`` — short ref the owner quotes when replying

    Keeping the key set identical across templates lets us add new
    template variants without touching this renderer. The downstream
    :class:`WhatsAppYCloudAdapter.send_template` accepts both list (for
    legacy positional templates like ``alert_*``) and dict (named) and
    renders the right Meta payload shape for each.
    """
    params = row.template_params_json or {}
    return {
        "tenant_name": str(params.get("tenant_name") or tenant_name),
        "question": str(params.get("question") or row.question_text),
        "urgency": str(params.get("urgency") or row.urgency),
        "correlation_id": row.correlation_id,
    }
