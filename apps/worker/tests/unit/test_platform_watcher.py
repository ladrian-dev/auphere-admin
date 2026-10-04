"""WP-06: the platform watcher detects each condition and notifies once.

Uses fakeredis for the counters the hot paths write, and monkeypatches the
notification sink so the tests assert on delivered alerts, not on email
infrastructure.
"""

from __future__ import annotations

import time
import uuid

import pytest
from fakeredis import aioredis as fakeaioredis

from nexus_worker.streams import platform_watcher as pw

pytestmark = pytest.mark.asyncio


@pytest.fixture
def delivered(monkeypatch) -> list[pw.Alert]:
    sink: list[pw.Alert] = []

    async def fake_notify(alert: pw.Alert) -> None:
        sink.append(alert)

    monkeypatch.setattr(pw, "_notify", fake_notify)
    return sink


async def test_dlq_entries_alert(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.xadd(pw.DLQ_STREAM, {"dlq_error": "boom"})

    out = await pw.process_tick(redis)

    kinds = [a.kind for a in out]
    assert "dlq_entries" in kinds
    assert delivered[0].count == 1


async def test_dedup_suppresses_second_tick(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.xadd(pw.DLQ_STREAM, {"dlq_error": "boom"})

    first = await pw.process_tick(redis)
    second = await pw.process_tick(redis)

    assert [a.kind for a in first] == ["dlq_entries"]
    assert second == []  # same window → deduplicated


async def test_turn_error_burst_alert(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    tenant = uuid.uuid4()
    window = int(time.time()) // 600
    await redis.set(f"nexus:alert:turn_errors:{tenant}:{window}", "6")

    out = await pw.process_tick(redis)

    burst = [a for a in out if a.kind == "turn_error_burst"]
    assert len(burst) == 1
    assert burst[0].tenant_id == tenant
    assert burst[0].count == 6


async def test_turn_errors_below_threshold_do_not_alert(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    window = int(time.time()) // 600
    await redis.set(f"nexus:alert:turn_errors:{uuid.uuid4()}:{window}", "5")

    out = await pw.process_tick(redis)
    assert [a for a in out if a.kind == "turn_error_burst"] == []


async def test_meta_failure_burst_alert(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    window = int(time.time()) // 600
    await redis.set(f"nexus:alert:metafail:131047:{window}", "21")

    out = await pw.process_tick(redis)

    burst = [a for a in out if a.kind == "meta_failure_burst"]
    assert len(burst) == 1
    assert "131047" in burst[0].subject


async def test_cache_ratio_low_alert_with_volume(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    hour = int(time.time()) // 3600
    await redis.set(f"nexus:alert:llmtok:input:{hour}", "90000")
    await redis.set(f"nexus:alert:llmtok:cache_read:{hour}", "20000")

    out = await pw.process_tick(redis)

    assert [a.kind for a in out if a.kind == "cache_ratio_low"] == ["cache_ratio_low"]


async def test_cache_ratio_ignored_without_volume(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    hour = int(time.time()) // 3600
    await redis.set(f"nexus:alert:llmtok:input:{hour}", "500")
    await redis.set(f"nexus:alert:llmtok:cache_read:{hour}", "0")

    out = await pw.process_tick(redis)
    assert [a for a in out if a.kind == "cache_ratio_low"] == []


async def test_worker_dead_after_silence(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    now = time.time()
    # Last seen 10 minutes ago, no heartbeat key present.
    await redis.set("nexus:alert:worker_lastseen:nexus-worker", str(now - 600))

    out = await pw.process_tick(redis, now=now)

    dead = [a for a in out if a.kind == "worker_dead"]
    assert len(dead) == 1
    assert "nexus-worker" in dead[0].subject


async def test_worker_alive_no_alert(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.set("nexus:health:nexus-worker:host-1", "1")

    out = await pw.process_tick(redis)
    assert [a for a in out if a.kind == "worker_dead"] == []


async def test_queue_backlog_alert(delivered) -> None:
    redis = fakeaioredis.FakeRedis()
    # Entry delivered to a consumer 10 minutes ago and never acked. Craft the
    # entry id timestamp in the past so the age computation crosses 300s.
    old_ms = int((time.time() - 600) * 1000)
    await redis.xadd(pw.INBOUND_STREAM, {"content": "x"}, id=f"{old_ms}-0")
    await redis.xgroup_create(pw.INBOUND_STREAM, pw.INBOUND_GROUP, id="0")
    await redis.xreadgroup(
        groupname=pw.INBOUND_GROUP,
        consumername="c-dead",
        streams={pw.INBOUND_STREAM: ">"},
        count=1,
    )

    out = await pw.process_tick(redis)

    backlog = [a for a in out if a.kind == "queue_backlog"]
    assert len(backlog) == 1
    assert backlog[0].count == 1


async def test_the_burst_row_carries_a_target_so_it_is_written(monkeypatch) -> None:
    """``audit_log.target`` is NOT NULL. Without one the insert failed, the
    ``suppress`` around it swallowed the error and the row never existed."""
    import contextlib

    from nexus_api.core import tenant_context
    from nexus_api.db import base

    added: list = []

    class _Session:
        def add(self, row) -> None:
            added.append(row)

        async def commit(self) -> None:
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> None:
            return None

    monkeypatch.setattr(base, "get_sessionmaker", lambda: _Session)
    monkeypatch.setattr(
        tenant_context, "tenant_scoped_session", lambda *_a, **_k: contextlib.nullcontext()
    )
    tenant = uuid.uuid4()
    alert = pw.Alert(
        kind="turn_error_burst", dedup_key="k", subject="s", detail="d", tenant_id=tenant, count=7
    )
    await pw._write_tenant_audit_row(alert)
    assert len(added) == 1
    assert added[0].target == f"tenant:{tenant}"
    assert added[0].action == "platform.turn_error_burst"
