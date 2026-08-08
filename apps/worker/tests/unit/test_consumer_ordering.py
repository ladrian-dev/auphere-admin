"""WP-09: partitioned-consumer ordering guarantee.

Two messages of the SAME conversation must process strictly in order even
when the second arrives while the first is still in flight — that is the
whole point of partitioning by ``thread_id`` instead of going fully
concurrent.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fakeredis import aioredis as fakeaioredis

from nexus_worker.streams import consumer as consumer_mod

pytestmark = pytest.mark.asyncio

STREAM = "nexus:inbound"
GROUP = "g"


def _fields(user: str, content: str, tenant: str, channel: str) -> dict[str, str]:
    return {
        "tenant_id": tenant,
        "channel_id": channel,
        "user_id": user,
        "content": content,
        "provider": "meta",
    }


async def test_same_thread_processes_in_order(monkeypatch) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    tenant, channel = str(uuid.uuid4()), str(uuid.uuid4())

    # Two messages, same conversation; the first dispatch is slow.
    await redis.xadd(STREAM, _fields("56911112222", "primero", tenant, channel))
    await redis.xadd(STREAM, _fields("56911112222", "segundo", tenant, channel))

    order: list[str] = []
    first_started = asyncio.Event()

    async def slow_then_fast(event, *, pipeline):
        if event.content == "primero":
            first_started.set()
            await asyncio.sleep(0.2)  # second message arrives mid-flight
        order.append(event.content)
        return {}

    monkeypatch.setattr(consumer_mod, "process_inbound", slow_then_fast)

    stop = asyncio.Event()
    processed = 0

    async def on_processed(event):
        nonlocal processed
        processed += 1
        if processed >= 2:
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
            slots=8,
            max_inflight=8,
        ),
        timeout=10.0,
    )

    assert order == ["primero", "segundo"]


async def test_slot_for_is_stable_and_spreads() -> None:
    tenant, channel = str(uuid.uuid4()), str(uuid.uuid4())
    a = consumer_mod.slot_for(_fields("user-a", "x", tenant, channel), 64)
    a_again = consumer_mod.slot_for(_fields("user-a", "y", tenant, channel), 64)
    assert a == a_again  # same conversation → same slot, always

    slots = {
        consumer_mod.slot_for(_fields(f"user-{i}", "x", tenant, channel), 64)
        for i in range(200)
    }
    # 200 distinct conversations must not funnel into a handful of slots.
    assert len(slots) > 32


async def test_malformed_entry_routes_to_slot_zero() -> None:
    assert consumer_mod.slot_for({"content": "no ids"}, 64) == 0
