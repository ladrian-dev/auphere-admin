"""Block H: GET /admin/tenants/:id/isolation/metrics + record_isolation_event.

The endpoint reads the last 24h from ``isolation_events`` (RLS scoped)
and aggregates by metric. The ``record_isolation_event`` call site must
write a row that lands inside the active tenant context — these tests
exercise both ends + the cross-tenant guarantee.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text

from nexus_api.config import get_settings
from nexus_api.core.metrics import (
    ISOLATION_TOOL_WHITELIST_VIOLATION,
    counters,
    isolation_event_drainer,
    record_isolation_event,
    reset_event_queue,
)
from nexus_api.db.models import IsolationEvent

pytestmark = pytest.mark.asyncio


def _bearer() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().admin_token}"}


async def _scoped_insert(scoped_session_factory, tenant_id: uuid.UUID, metric: str) -> None:
    """Insert an isolation event row directly via RLS-scoped session."""
    session = await scoped_session_factory(tenant_id)
    try:
        session.add(IsolationEvent(tenant_id=tenant_id, metric=metric, payload={"k": "v"}))
        await session.commit()
    finally:
        await session.close()


async def test_endpoint_returns_seven_canonical_metrics(client, seed_tenants):
    tid = seed_tenants["a"]
    r = await client.get(f"/admin/tenants/{tid}/isolation/metrics", headers=_bearer())
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == str(tid)
    assert body["window_hours"] == 24
    metrics = {m["metric"]: m for m in body["metrics"]}
    assert len(metrics) == 7
    # All zero in absence of events.
    for m in metrics.values():
        assert m["count_24h"] == 0
        assert m["last_breach_at"] is None
    # The unscoped_query metric is the only system-level (non-persisted) one.
    assert metrics["isolation.unscoped_query"]["persisted"] is False
    assert metrics["isolation.tool_whitelist_violation"]["persisted"] is True


async def test_endpoint_aggregates_seeded_events(client, seed_tenants, scoped_session_factory):
    tid = seed_tenants["a"]
    await _scoped_insert(scoped_session_factory, tid, ISOLATION_TOOL_WHITELIST_VIOLATION)
    await _scoped_insert(scoped_session_factory, tid, ISOLATION_TOOL_WHITELIST_VIOLATION)
    r = await client.get(f"/admin/tenants/{tid}/isolation/metrics", headers=_bearer())
    assert r.status_code == 200
    metrics = {m["metric"]: m for m in r.json()["metrics"]}
    target = metrics[ISOLATION_TOOL_WHITELIST_VIOLATION]
    assert target["count_24h"] == 2
    assert target["last_breach_at"] is not None


async def test_endpoint_does_not_leak_across_tenants(client, seed_tenants, scoped_session_factory):
    tid_a = seed_tenants["a"]
    tid_b = seed_tenants["b"]
    await _scoped_insert(scoped_session_factory, tid_b, ISOLATION_TOOL_WHITELIST_VIOLATION)
    await _scoped_insert(scoped_session_factory, tid_b, ISOLATION_TOOL_WHITELIST_VIOLATION)

    r_a = await client.get(f"/admin/tenants/{tid_a}/isolation/metrics", headers=_bearer())
    r_b = await client.get(f"/admin/tenants/{tid_b}/isolation/metrics", headers=_bearer())
    assert r_a.status_code == 200 and r_b.status_code == 200
    metrics_a = {m["metric"]: m for m in r_a.json()["metrics"]}
    metrics_b = {m["metric"]: m for m in r_b.json()["metrics"]}
    assert metrics_a[ISOLATION_TOOL_WHITELIST_VIOLATION]["count_24h"] == 0
    assert metrics_b[ISOLATION_TOOL_WHITELIST_VIOLATION]["count_24h"] == 2


async def test_endpoint_requires_bearer(client, seed_tenants):
    tid = seed_tenants["a"]
    r = await client.get(f"/admin/tenants/{tid}/isolation/metrics")
    assert r.status_code in (401, 403)


async def test_record_isolation_event_persists_via_drainer(db_session, seed_tenants):
    """End-to-end: producer → deque → drainer → ``isolation_events`` row."""
    tid = seed_tenants["a"]
    counters.reset()
    reset_event_queue()
    record_isolation_event(ISOLATION_TOOL_WHITELIST_VIOLATION, tid, {"tool": "payment.charge"})
    assert counters.get(ISOLATION_TOOL_WHITELIST_VIOLATION) == 1
    assert counters.get(f"{ISOLATION_TOOL_WHITELIST_VIOLATION}:{tid}") == 1

    stop = asyncio.Event()
    drainer_task = asyncio.create_task(isolation_event_drainer(stop, poll_seconds=0.05))
    # Give the drainer one tick.
    await asyncio.sleep(0.2)
    stop.set()
    await asyncio.wait_for(drainer_task, timeout=1.0)

    async with db_session.begin():
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)}
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        rows = await db_session.execute(
            text("SELECT metric, payload FROM isolation_events WHERE metric = :m"),
            {"m": ISOLATION_TOOL_WHITELIST_VIOLATION},
        )
        items = list(rows)
        assert len(items) == 1
        assert items[0][0] == ISOLATION_TOOL_WHITELIST_VIOLATION
        assert items[0][1] == {"tool": "payment.charge"}


async def test_unscoped_query_metric_does_not_persist(seed_tenants):
    """The enforcer fires before tenant context — that metric is in-memory only."""
    tid = seed_tenants["a"]
    reset_event_queue()
    counters.reset()
    record_isolation_event("isolation.unscoped_query", tid)
    assert counters.get("isolation.unscoped_query") == 1
    from nexus_api.core.metrics import get_event_queue

    assert len(get_event_queue()) == 0
