"""Block H: WhatsApp provider 5xx burst tracker — sliding window + audit emit.

Window default 2min, threshold default 5. Once tripped the tracker
writes a single ``channel.whatsapp_5xx_burst`` audit row and enters a
cooldown so a sustained burst doesn't generate one audit per tick.
"""

from __future__ import annotations

import uuid
from time import monotonic

import pytest
import sqlalchemy as sa
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


def test_tracker_under_threshold_does_not_alert():
    reset_default_tracker()
    t = WhatsAppBurstTracker(threshold=5, window_seconds=120)
    tid = uuid.uuid4()
    for _ in range(4):
        assert t.should_alert(tid, 503) is False


def test_tracker_above_threshold_alerts_once_then_cools():
    reset_default_tracker()
    t = WhatsAppBurstTracker(threshold=3, window_seconds=120, cooldown_seconds=600)
    tid = uuid.uuid4()
    assert t.should_alert(tid, 502) is False
    assert t.should_alert(tid, 503) is False
    assert t.should_alert(tid, 504) is True
    # Next call within cooldown — even after another 3 strikes — must not alert.
    for _ in range(5):
        t.should_alert(tid, 503)
    assert t.should_alert(tid, 503) is False


def test_tracker_ignores_non_5xx_codes():
    reset_default_tracker()
    t = WhatsAppBurstTracker(threshold=2, window_seconds=120)
    tid = uuid.uuid4()
    assert t.should_alert(tid, 401) is False
    assert t.should_alert(tid, 422) is False
    assert t.should_alert(tid, 200) is False


def test_tracker_treats_zero_as_transport_error():
    reset_default_tracker()
    t = WhatsAppBurstTracker(threshold=2, window_seconds=120)
    tid = uuid.uuid4()
    assert t.should_alert(tid, 0) is False
    assert t.should_alert(tid, 0) is True


def test_tracker_window_drops_old_entries(monkeypatch):
    reset_default_tracker()
    t = WhatsAppBurstTracker(threshold=3, window_seconds=10, cooldown_seconds=600)
    tid = uuid.uuid4()
    fake_now = [monotonic()]

    def now() -> float:
        return fake_now[0]

    monkeypatch.setattr("nexus_worker.streams.burst_tracker.time.monotonic", now)
    # Pre-fill 2 strikes, advance past window, then 2 more — should NOT trip.
    t.should_alert(tid, 503)
    t.should_alert(tid, 503)
    fake_now[0] += 11.0
    assert t.should_alert(tid, 503) is False
    assert t.should_alert(tid, 503) is False
    # Third within new window trips.
    assert t.should_alert(tid, 503) is True


@pytest.mark.asyncio
async def test_tracker_writes_audit_log_when_alerting(db_session):
    reset_default_tracker()
    tid = await _seed(db_session)
    t = WhatsAppBurstTracker(threshold=2, window_seconds=120, cooldown_seconds=600)

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
