"""WP-12 (D11, cierra V4): the egress is notification-driven.

Two layers pinned here:

1. **The 0062 trigger actually fires**: inserting a pending outbound
   ``messages`` row emits ``pg_notify('nexus_outbound', tenant_id)`` — the
   contract the worker's listener consumes. Verified over a raw asyncpg
   LISTEN connection against the real database.
2. **The dispatcher drains only who has work**: with many active tenants
   and one notification, exactly one tenant is drained between sweeps —
   database cost proportional to traffic, not to tenant count.
"""

from __future__ import annotations

import asyncio
import uuid

import asyncpg
import pytest
from nexus_worker.streams import outbound as outbound_mod

from nexus_api.config import get_settings
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
)

pytestmark = pytest.mark.asyncio


def _dsn() -> str:
    return get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def test_trigger_notifies_on_pending_outbound_insert(db_session, seed_tenants) -> None:
    tenant_id = seed_tenants["a"]
    received: list[str] = []
    got_one = asyncio.Event()

    listener = await asyncpg.connect(_dsn())
    try:

        def _on_notify(_conn, _pid, _channel, payload):
            received.append(payload)
            got_one.set()

        await listener.add_listener(outbound_mod.NOTIFY_CHANNEL, _on_notify)

        async with tenant_scoped_session(db_session, tenant_id):
            channel = Channel(
                tenant_id=tenant_id,
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=f"+569{uuid.uuid4().hex[:8]}",
                status=ChannelStatus.ACTIVE,
                config={},
            )
            db_session.add(channel)
            await db_session.flush()
            customer = Customer(tenant_id=tenant_id, identifier=f"569{uuid.uuid4().hex[:8]}")
            db_session.add(customer)
            await db_session.flush()
            conversation = Conversation(
                tenant_id=tenant_id, channel_id=channel.id, customer_id=customer.id
            )
            db_session.add(conversation)
            await db_session.flush()
            db_session.add(
                Message(
                    tenant_id=tenant_id,
                    conversation_id=conversation.id,
                    direction=MessageDirection.OUTBOUND,
                    status=MessageStatus.PENDING,
                    content="hola saliente",
                )
            )
            await db_session.commit()

        await asyncio.wait_for(got_one.wait(), timeout=5.0)
        assert str(tenant_id) in received
    finally:
        await listener.close()


async def _seed_pending_outbound(db_session, tenant_id: uuid.UUID, content: str) -> None:
    async with tenant_scoped_session(db_session, tenant_id):
        channel = Channel(
            tenant_id=tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"+569{uuid.uuid4().hex[:8]}",
            status=ChannelStatus.ACTIVE,
            config={},
        )
        db_session.add(channel)
        await db_session.flush()
        customer = Customer(tenant_id=tenant_id, identifier=f"569{uuid.uuid4().hex[:8]}")
        db_session.add(customer)
        await db_session.flush()
        conversation = Conversation(
            tenant_id=tenant_id, channel_id=channel.id, customer_id=customer.id
        )
        db_session.add(conversation)
        await db_session.flush()
        db_session.add(
            Message(
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                direction=MessageDirection.OUTBOUND,
                status=MessageStatus.PENDING,
                content=content,
            )
        )
        await db_session.commit()


async def test_backlog_gauge_counts_across_tenants(db_session, seed_tenants) -> None:
    """WP-24: the gauge egress autoscales on is a GLOBAL count.

    Egress sizing is a property of the whole queue, not of one tenant —
    the sweep reads across tenants on purpose (same reasoning as the
    undrained-tenant warning). Measured as a delta because the suite
    shares one database.
    """
    from nexus_api.core import otel_metrics
    from nexus_api.db.base import get_sessionmaker

    sm = get_sessionmaker()

    await outbound_mod._publish_outbound_backlog(sm)
    baseline = otel_metrics._outbound_backlog
    assert baseline is not None

    await _seed_pending_outbound(db_session, seed_tenants["a"], "pendiente a")
    await _seed_pending_outbound(db_session, seed_tenants["b"], "pendiente b")

    await outbound_mod._publish_outbound_backlog(sm)
    after = otel_metrics._outbound_backlog
    assert after is not None

    assert after[0] == baseline[0] + 2, "the gauge must see BOTH tenants' pending rows"
    assert after[1] >= 0.0


async def test_outbound_pending_index_exists(db_session) -> None:
    """The gauge's query and the per-tenant drain both ride on the partial
    index of 0067. Without it they seq-scan every partition of
    ``messages`` every 30 s — the reason the index shipped with the gauge.
    """
    import sqlalchemy as sa

    found = await db_session.scalar(
        sa.text("SELECT count(*) FROM pg_indexes WHERE indexname = :name"),
        {"name": "ix_messages_outbound_pending"},
    )
    assert found == 1


async def test_dispatcher_drains_only_notified_tenants(monkeypatch) -> None:
    drained: list[uuid.UUID] = []

    async def fake_drain(sm, tenant_id, adapters, batch_size):
        drained.append(tenant_id)

    # 200 active tenants exist, but the sweep is far away — only the
    # notified tenant may be touched.
    many_tenants = [uuid.uuid4() for _ in range(200)]

    async def fake_list_active(sm):
        return many_tenants

    monkeypatch.setattr(outbound_mod, "_drain_tenant", fake_drain)
    monkeypatch.setattr(outbound_mod, "_list_active_tenants", fake_list_active)

    async def fake_warn(sm, active):
        return None

    monkeypatch.setattr(outbound_mod, "_warn_on_undrained_tenants", fake_warn)

    work = outbound_mod.OutboundWorkSet()
    stop = asyncio.Event()
    task = asyncio.create_task(
        outbound_mod.run_outbound_dispatcher(
            adapters={},
            stop=stop,
            sweep_seconds=3600.0,  # sweep effectively disabled…
            work=work,
            listen=False,  # …and no real LISTEN connection in the test
        )
    )
    try:
        # First iteration runs the boot sweep; wait for it and reset.
        await asyncio.sleep(0.3)
        drained.clear()

        hot_tenant = uuid.uuid4()
        work.add(hot_tenant)
        for _ in range(50):
            if drained:
                break
            await asyncio.sleep(0.05)

        assert drained == [hot_tenant], (
            "exactly the notified tenant must be drained between sweeps "
            f"(got {len(drained)} drains)"
        )
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=5.0)


async def test_boot_sweep_covers_everyone_once(monkeypatch) -> None:
    """The safety sweep visits every active tenant (lost notifications and
    re-queued retries land here) — verified via the boot sweep."""
    drained: list[uuid.UUID] = []

    async def fake_drain(sm, tenant_id, adapters, batch_size):
        drained.append(tenant_id)

    tenants = [uuid.uuid4() for _ in range(5)]

    async def fake_list_active(sm):
        return tenants

    async def fake_warn(sm, active):
        return None

    monkeypatch.setattr(outbound_mod, "_drain_tenant", fake_drain)
    monkeypatch.setattr(outbound_mod, "_list_active_tenants", fake_list_active)
    monkeypatch.setattr(outbound_mod, "_warn_on_undrained_tenants", fake_warn)

    work = outbound_mod.OutboundWorkSet()
    stop = asyncio.Event()
    task = asyncio.create_task(
        outbound_mod.run_outbound_dispatcher(
            adapters={}, stop=stop, sweep_seconds=3600.0, work=work, listen=False
        )
    )
    try:
        for _ in range(50):
            if len(drained) >= 5:
                break
            await asyncio.sleep(0.05)
        assert sorted(map(str, drained)) == sorted(map(str, tenants))
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=5.0)
