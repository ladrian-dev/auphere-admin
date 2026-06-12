"""Block H: cost rollup cron — daily snapshot + threshold audit emit."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    DailyCostSnapshot,
    Message,
    MessageDirection,
    MessageStatus,
    Tenant,
    TenantPlan,
    TenantStatus,
)

pytestmark = pytest.mark.asyncio


async def _seed_tenant(db_session, *, threshold: Decimal) -> dict:
    tid = uuid.uuid4()
    tenant = Tenant(
        id=tid,
        name=f"H {tid.hex[:6]}",
        slug=f"h-{tid.hex[:6]}",
        plan=TenantPlan.PRO,
        status=TenantStatus.ACTIVE,
        cost_alert_threshold_usd_per_day=threshold,
    )
    db_session.add(tenant)
    await db_session.commit()

    channel = Channel(
        tenant_id=tid,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=f"+5699999{tid.hex[:4]}",
        status=ChannelStatus.ACTIVE,
    )
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)

    customer = Customer(tenant_id=tid, identifier=f"+5691111{tid.hex[:4]}", preferences={})
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)

    conv = Conversation(
        tenant_id=tid,
        channel_id=channel.id,
        customer_id=customer.id,
        status=ConversationStatus.OPEN,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    return {"tenant_id": tid, "conversation_id": conv.id}


async def _seed_message(
    db_session, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID, cost: Decimal
) -> None:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        session.add(
            Message(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                direction=MessageDirection.OUTBOUND,
                content="x",
                status=MessageStatus.SENT,
                cost_usd=float(cost),
            )
        )
        await session.commit()


async def test_rollup_creates_snapshot_under_threshold(db_session):
    from nexus_worker.streams.cost_rollup_cron import _process

    info = await _seed_tenant(db_session, threshold=Decimal("40"))
    tid = info["tenant_id"]
    await _seed_message(
        db_session, tenant_id=tid, conversation_id=info["conversation_id"], cost=Decimal("5.00")
    )
    await _seed_message(
        db_session, tenant_id=tid, conversation_id=info["conversation_id"], cost=Decimal("10.00")
    )

    sm = get_sessionmaker()
    await _process(sm)

    async with sm() as session, tenant_scoped_session(session, tid):
        snap_row = await session.execute(sa.select(DailyCostSnapshot))
        snap = snap_row.scalar_one()
        assert snap.cost_usd_total == Decimal("15.0000")
        assert snap.message_count == 2
        assert snap.threshold_exceeded_at is None
        audit_count = await session.execute(
            sa.select(sa.func.count(AuditLog.id)).where(
                AuditLog.action == "cost.daily_threshold_exceeded"
            )
        )
        assert audit_count.scalar_one() == 0


async def test_rollup_emits_audit_when_threshold_crossed(db_session):
    from nexus_worker.streams.cost_rollup_cron import _process

    info = await _seed_tenant(db_session, threshold=Decimal("10"))
    tid = info["tenant_id"]
    await _seed_message(
        db_session, tenant_id=tid, conversation_id=info["conversation_id"], cost=Decimal("4.00")
    )
    await _seed_message(
        db_session, tenant_id=tid, conversation_id=info["conversation_id"], cost=Decimal("8.00")
    )

    sm = get_sessionmaker()
    await _process(sm)

    async with sm() as session, tenant_scoped_session(session, tid):
        snap = (await session.execute(sa.select(DailyCostSnapshot))).scalar_one()
        assert snap.cost_usd_total == Decimal("12.0000")
        assert snap.threshold_exceeded_at is not None

        audit = (
            await session.execute(
                sa.select(AuditLog).where(AuditLog.action == "cost.daily_threshold_exceeded")
            )
        ).scalar_one()
        assert Decimal(audit.after_json["threshold_usd"]) == Decimal("10")
        assert Decimal(audit.after_json["cost_usd_total"]) == Decimal("12")


async def test_rollup_does_not_double_emit_audit(db_session):
    """Two ticks, only one audit row even if total stays above threshold."""
    from nexus_worker.streams.cost_rollup_cron import _process

    info = await _seed_tenant(db_session, threshold=Decimal("5"))
    tid = info["tenant_id"]
    await _seed_message(
        db_session, tenant_id=tid, conversation_id=info["conversation_id"], cost=Decimal("10")
    )

    sm = get_sessionmaker()
    await _process(sm)
    await _process(sm)

    async with sm() as session, tenant_scoped_session(session, tid):
        count = await session.execute(
            sa.select(sa.func.count(AuditLog.id)).where(
                AuditLog.action == "cost.daily_threshold_exceeded"
            )
        )
        assert count.scalar_one() == 1


async def test_rollup_isolates_per_tenant(db_session):
    from nexus_worker.streams.cost_rollup_cron import _process

    a = await _seed_tenant(db_session, threshold=Decimal("100"))
    b = await _seed_tenant(db_session, threshold=Decimal("100"))
    await _seed_message(
        db_session,
        tenant_id=a["tenant_id"],
        conversation_id=a["conversation_id"],
        cost=Decimal("7"),
    )
    await _seed_message(
        db_session,
        tenant_id=b["tenant_id"],
        conversation_id=b["conversation_id"],
        cost=Decimal("9"),
    )

    sm = get_sessionmaker()
    await _process(sm)

    async with sm() as session, tenant_scoped_session(session, a["tenant_id"]):
        snap_a = (await session.execute(sa.select(DailyCostSnapshot))).scalar_one()
        assert snap_a.cost_usd_total == Decimal("7.0000")
    async with sm() as session, tenant_scoped_session(session, b["tenant_id"]):
        snap_b = (await session.execute(sa.select(DailyCostSnapshot))).scalar_one()
        assert snap_b.cost_usd_total == Decimal("9.0000")


# ``asyncio`` is referenced indirectly via fixtures; keep the import for type
# checkers that look at the file in isolation.
_ = asyncio
_ = datetime.now(UTC)
