"""Block H / WP-08: WhatsApp provider 5xx burst tracker — Redis-backed.

Window default 2min (fixed bucket since WP-08), threshold default 5. Once
tripped the tracker writes a single ``channel.whatsapp_5xx_burst`` audit row
and enters a cooldown so a sustained burst doesn't generate one audit per
tick. State lives in Redis so every egress replica shares one count.
"""

from __future__ import annotations

import uuid

import fakeredis.aioredis
import pytest
import sqlalchemy as sa
from nexus_worker.streams import burst_tracker as bt_mod
from nexus_worker.streams.burst_tracker import (
    WhatsAppBurstTracker,
    reset_default_tracker,
)

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AuditLog,
    Tenant,
    TenantPlan,
    TenantStatus,
)

pytestmark = pytest.mark.asyncio


def _tracker(**kwargs) -> WhatsAppBurstTracker:
    reset_default_tracker()
    return WhatsAppBurstTracker(redis=fakeredis.aioredis.FakeRedis(), **kwargs)


async def _seed(db_session) -> uuid.UUID:
    tid = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tid,
            name=f"Burst {tid.hex[:6]}",
            slug=f"burst-{tid.hex[:6]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
        )
    )
    await db_session.commit()
    return tid


async def test_tracker_under_threshold_does_not_alert():
    t = _tracker(threshold=5, window_seconds=120)
    tid = uuid.uuid4()
    for _ in range(4):
        assert await t.should_alert(tid, 503) is False


async def test_tracker_above_threshold_alerts_once_then_cools():
    t = _tracker(threshold=3, window_seconds=120, cooldown_seconds=600)
    tid = uuid.uuid4()
    assert await t.should_alert(tid, 502) is False
    assert await t.should_alert(tid, 503) is False
    assert await t.should_alert(tid, 504) is True
    # Next call within cooldown — even after another 3 strikes — must not alert.
    for _ in range(5):
        await t.should_alert(tid, 503)
    assert await t.should_alert(tid, 503) is False


async def test_tracker_ignores_non_5xx_codes():
    t = _tracker(threshold=2, window_seconds=120)
    tid = uuid.uuid4()
    assert await t.should_alert(tid, 401) is False
    assert await t.should_alert(tid, 422) is False
    assert await t.should_alert(tid, 200) is False


async def test_tracker_treats_zero_as_transport_error():
    t = _tracker(threshold=2, window_seconds=120)
    tid = uuid.uuid4()
    assert await t.should_alert(tid, 0) is False
    assert await t.should_alert(tid, 0) is True


async def test_tracker_window_drops_old_entries(monkeypatch):
    t = _tracker(threshold=3, window_seconds=10, cooldown_seconds=600)
    tid = uuid.uuid4()
    fake_now = [1_000_000.0]

    monkeypatch.setattr(bt_mod.time, "time", lambda: fake_now[0])
    # Pre-fill 2 strikes, advance past the bucket, then 2 more — no trip.
    await t.should_alert(tid, 503)
    await t.should_alert(tid, 503)
    fake_now[0] += 11.0  # next 10s bucket
    assert await t.should_alert(tid, 503) is False
    assert await t.should_alert(tid, 503) is False
    # Third within the new bucket trips.
    assert await t.should_alert(tid, 503) is True


async def test_tracker_shared_state_across_instances():
    """Two tracker instances (two egress replicas) sharing one Redis see a
    single combined count — the WP-08 property that motivated the port."""
    redis = fakeredis.aioredis.FakeRedis()
    reset_default_tracker()
    a = WhatsAppBurstTracker(threshold=3, window_seconds=120, redis=redis)
    b = WhatsAppBurstTracker(threshold=3, window_seconds=120, redis=redis)
    tid = uuid.uuid4()
    assert await a.should_alert(tid, 503) is False
    assert await b.should_alert(tid, 503) is False
    assert await a.should_alert(tid, 503) is True


async def test_tracker_redis_down_suppresses_alert():
    class _Boom:
        async def incr(self, *a, **k):
            raise ConnectionError("redis down")

    reset_default_tracker()
    t = WhatsAppBurstTracker(threshold=1, redis=_Boom())
    assert await t.should_alert(uuid.uuid4(), 503) is False


async def test_tracker_writes_audit_log_when_alerting(db_session):
    tid = await _seed(db_session)
    t = _tracker(threshold=2, window_seconds=120, cooldown_seconds=600)

    fired_a = await t.record_failure_and_maybe_audit(tid, 502, error_message="upstream")
    fired_b = await t.record_failure_and_maybe_audit(tid, 503, error_message="upstream")
    assert fired_a is False
    assert fired_b is True

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tid):
        rows = await session.execute(
            sa.select(AuditLog).where(AuditLog.action == "channel.whatsapp_5xx_burst")
        )
        items = list(rows.scalars())
        assert len(items) == 1
        assert items[0].after_json["threshold"] == 2
