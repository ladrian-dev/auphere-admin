"""WP-09: distinct conversations progress in parallel.

32 threads with a 100 ms dispatch must complete in well under a second —
strictly serial they would take 3.2 s. This is the property that raises the
platform ceiling from ~10-14 turns/min to the Escenario-A target.

Also pins that ``max_inflight`` truly caps simultaneous dispatches, and
that tenant context does not leak across concurrent turns (the ContextVar
guarantee the isolation suite relies on).
"""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest
from fakeredis import aioredis as fakeaioredis

from nexus_worker.streams import consumer as consumer_mod

pytestmark = pytest.mark.asyncio

STREAM = "nexus:inbound"
GROUP = "g"

N_THREADS = 32


def _fields(user: str) -> dict[str, str]:
    return {
        "tenant_id": str(uuid.uuid4()),
        "channel_id": str(uuid.uuid4()),
        "user_id": user,
        "content": "hola",
        "provider": "meta",
    }


async def _run_consumer(redis, monkeypatch, dispatch, *, expected: int, **kwargs) -> None:
    monkeypatch.setattr(consumer_mod, "process_inbound", dispatch)
    stop = asyncio.Event()
    processed = 0

    async def on_processed(event):
        nonlocal processed
        processed += 1
        if processed >= expected:
            stop.set()

    await asyncio.wait_for(
        consumer_mod.run_inbound_consumer(
            redis,
            pipeline=None,
            stream=STREAM,
            group=GROUP,
            consumer_name="c1",
            block_ms=10,
            stop=stop,
            on_processed=on_processed,
            **kwargs,
        ),
        timeout=15.0,
    )


async def test_32_threads_process_concurrently(monkeypatch) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    for i in range(N_THREADS):
        await redis.xadd(STREAM, _fields(f"user-{i}"))

    async def dispatch(event, *, pipeline):
        await asyncio.sleep(0.1)
        return {}

    started = time.perf_counter()
    await _run_consumer(redis, monkeypatch, dispatch, expected=N_THREADS, slots=64, max_inflight=64)
    elapsed = time.perf_counter() - started

    # Serial would be 3.2 s; concurrent should be a few 100 ms batches.
    assert elapsed < 1.0, f"expected concurrent processing, took {elapsed:.2f}s"


async def test_max_inflight_caps_concurrency(monkeypatch) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    for i in range(12):
        await redis.xadd(STREAM, _fields(f"user-{i}"))

    active = 0
    peak = 0

    async def dispatch(event, *, pipeline):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1
        return {}

    await _run_consumer(redis, monkeypatch, dispatch, expected=12, slots=32, max_inflight=4)

    assert peak <= 4, f"max_inflight=4 but peak concurrency was {peak}"
    assert peak >= 2, "expected some real concurrency under the cap"


async def test_contextvar_isolation_across_concurrent_turns(monkeypatch) -> None:
    """The runtime's tenant/customer context is ContextVar-based; slot
    workers are separate asyncio tasks, so concurrent turns must never read
    each other's value (garantía 7 under WP-09 concurrency)."""
    import contextvars

    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    for i in range(8):
        await redis.xadd(STREAM, _fields(f"user-{i}"))

    var: contextvars.ContextVar[str | None] = contextvars.ContextVar("cust", default=None)
    readback: dict[str, str | None] = {}

    async def dispatch(event, *, pipeline):
        var.set(event.user_id)
        await asyncio.sleep(0.05)  # interleave with the other turns
        readback[event.user_id] = var.get()
        return {}

    await _run_consumer(redis, monkeypatch, dispatch, expected=8, slots=16, max_inflight=16)

    assert len(readback) == 8
    for user, value in readback.items():
        assert value == user, f"context leaked: {user} read {value}"
