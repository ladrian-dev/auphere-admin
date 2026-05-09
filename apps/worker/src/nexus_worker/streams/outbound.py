"""Outbound message dispatcher.

Drains ``messages WHERE status='pending'`` and pushes each one through the
:class:`WhatsAppYCloudAdapter`. Drives the WhatsApp side of every smoke test
that asks "agent answers in the customer's WhatsApp".

Tenant isolation:
- Outer loop discovers tenants once per tick via a tenant-agnostic query
  on the ``tenants`` table (RLS-free; it's a global table).
- Per tenant, a fresh session enters ``tenant_scoped_session`` and runs the
  ``SELECT ... FOR UPDATE SKIP LOCKED`` against ``messages``. RLS limits the
  scan to that tenant's rows; SKIP LOCKED lets multiple worker replicas
  share the load without waiting on each other.

Backoff:
- Each row tracks ``attempts``. On send failure we increment, capture the
  error in ``last_error``, and re-set status='pending' until attempts hits
  ``MAX_ATTEMPTS``. After that the row is parked in 'failed' and the
  alerter (block H+) bubbles it up.
- A simple exponential pause within the same tick is unnecessary because
  the loop tick itself is the natural backoff unit (default 500ms).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Channel,
    ChannelType,
    Conversation,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
    Tenant,
    TenantStatus,
)
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from nexus_channels.whatsapp_ycloud.adapter import WhatsAppYCloudAdapter

log = structlog.get_logger(__name__)

# Tunables — outbound is bursty (think reminder fan-out at the same minute)
# but most ticks see zero pending rows. 500ms tick + 50 rows per tenant per
# tick == 100 msg/s headroom per worker which exceeds the 50 msg/s target.
DEFAULT_TICK_SECONDS = 0.5
DEFAULT_BATCH_SIZE = 50
MAX_ATTEMPTS = 3


async def run_outbound_dispatcher(
    *,
    adapter: WhatsAppYCloudAdapter,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    """Background task. Returns when ``stop`` is set."""
    log.info("outbound.dispatcher.start", tick_seconds=tick_seconds, batch=batch_size)
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            tenant_ids = await _list_active_tenants(sm)
            for tid in tenant_ids:
                if stop.is_set():
                    break
                await _drain_tenant(sm, tid, adapter, batch_size)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("outbound.dispatcher.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("outbound.dispatcher.stopped")


async def _list_active_tenants(sm: sa.orm.sessionmaker) -> list[uuid.UUID]:  # type: ignore[type-arg]
    async with sm() as session:
        rows = await session.execute(
            sa.select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE)
        )
        return [row[0] for row in rows]


async def _drain_tenant(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
    tenant_id: uuid.UUID,
    adapter: WhatsAppYCloudAdapter,
    batch_size: int,
) -> None:
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        result = await session.execute(
            sa.select(Message)
            .where(
                Message.direction == MessageDirection.OUTBOUND,
                Message.status == MessageStatus.PENDING,
            )
            .order_by(Message.created_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        pending = list(result.scalars())
        if not pending:
            return
        log.info(
            "outbound.dispatcher.batch",
            tenant_id=str(tenant_id),
            count=len(pending),
        )
        for msg in pending:
            await _send_one(session, msg, adapter, tenant_id)


async def _send_one(
    session: AsyncSession,
    msg: Message,
    adapter: WhatsAppYCloudAdapter,
    tenant_id: uuid.UUID,
) -> None:
    """Resolve the channel + recipient, send via adapter, update status."""
    # Channel + recipient: walk the foreign keys. RLS keeps them tenant-scoped.
    info = await session.execute(
        sa.select(Channel.id, Channel.provider_identifier, Channel.type, Customer.identifier)
        .join(Conversation, Conversation.channel_id == Channel.id)
        .join(Customer, Customer.id == Conversation.customer_id)
        .where(Conversation.id == msg.conversation_id)
        .limit(1)
    )
    row = info.first()
    if row is None:
        msg.status = MessageStatus.FAILED
        msg.attempts += 1
        msg.last_error = "channel/customer not found for conversation"
        log.warning(
            "outbound.dispatcher.no_channel_for_conversation",
            tenant_id=str(tenant_id),
            message_id=str(msg.id),
        )
        return
    channel_id, business_phone, channel_type, recipient = row
    if channel_type != ChannelType.WHATSAPP:
        # Other channels arrive in Phase 3+. Park the row so the alerter
        # can flag it; outbound dispatcher does not silently drop.
        msg.status = MessageStatus.FAILED
        msg.last_error = f"unsupported channel type: {channel_type}"
        return
    try:
        result = await adapter.send_text(
            from_phone=business_phone,
            recipient=recipient,
            text=msg.content,
            tenant_id=tenant_id,
            channel_id=channel_id,
        )
    except Exception as exc:
        msg.attempts += 1
        msg.last_error = f"{type(exc).__name__}: {exc}"[:500]
        if msg.attempts >= MAX_ATTEMPTS:
            msg.status = MessageStatus.FAILED
            log.warning(
                "outbound.dispatcher.permanent_failure",
                tenant_id=str(tenant_id),
                message_id=str(msg.id),
                attempts=msg.attempts,
                error=msg.last_error,
            )
        else:
            log.info(
                "outbound.dispatcher.retry",
                tenant_id=str(tenant_id),
                message_id=str(msg.id),
                attempts=msg.attempts,
                error=msg.last_error,
            )
        return
    msg.status = MessageStatus.SENT
    msg.last_error = None
    msg.trace_id = result.provider_message_id
    if msg.cost_usd is None and result.cost_usd_estimate is not None:
        msg.cost_usd = result.cost_usd_estimate
    msg.latency_ms = msg.latency_ms or _ms_since(msg.created_at)
    log.info(
        "outbound.dispatcher.sent",
        tenant_id=str(tenant_id),
        message_id=str(msg.id),
        provider_message_id=result.provider_message_id,
    )


def _ms_since(when: datetime) -> int | None:
    if when is None:
        return None
    delta = datetime.now(UTC) - when.astimezone(UTC) if when.tzinfo else None
    if delta is None:
        return None
    return int(delta.total_seconds() * 1000)
