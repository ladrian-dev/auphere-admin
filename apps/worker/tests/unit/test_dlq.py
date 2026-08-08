"""WP-04: dead-letter semantics of ``handle_entry``.

Contract: a failing entry stays pending (no ack) while its delivery count is
below ``MAX_DELIVERY_ATTEMPTS``; at the cap it is copied to
``nexus:inbound:dlq`` with diagnosis fields and acked so it stops occupying
the PEL. Success acks. Malformed entries ack immediately (nothing to retry).
"""

from __future__ import annotations

import uuid

import pytest
from fakeredis import aioredis as fakeaioredis

from nexus_worker.streams import consumer as consumer_mod

pytestmark = pytest.mark.asyncio

STREAM = "nexus:inbound"
GROUP = "g"


def _fields(**extra: str) -> dict[str, str]:
    return {
        "tenant_id": str(uuid.uuid4()),
        "channel_id": str(uuid.uuid4()),
        "user_id": "56911112222",
        "content": "hola",
        "provider": "meta",
        **extra,
    }


async def _deliver_once(redis) -> tuple[str, dict]:
    """Read the next entry through the group so it lands in the PEL."""
    resp = await redis.xreadgroup(
        groupname=GROUP, consumername="c1", streams={STREAM: ">"}, count=1
    )
    entry_id, raw_fields = resp[0][1][0]
    return entry_id, raw_fields


async def test_failure_below_cap_leaves_entry_pending(monkeypatch) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    await redis.xadd(STREAM, _fields())

    async def boom(event, *, pipeline):
        raise RuntimeError("transient")

    monkeypatch.setattr(consumer_mod, "process_inbound", boom)
    entry_id, raw_fields = await _deliver_once(redis)

    acked = await consumer_mod.handle_entry(
        redis,
        pipeline=None,
        stream=STREAM,
        group=GROUP,
        entry_id=entry_id,
        raw_fields=raw_fields,
    )

    assert acked is False
    pending = await redis.xpending(STREAM, GROUP)
    assert pending["pending"] == 1
    assert await redis.xlen(consumer_mod.DLQ_STREAM) == 0


async def test_fifth_failure_dead_letters_and_acks(monkeypatch) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    fields = _fields(traceparent="00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01")
    await redis.xadd(STREAM, fields)

    async def boom(event, *, pipeline):
        raise RuntimeError("poison payload")

    monkeypatch.setattr(consumer_mod, "process_inbound", boom)

    entry_id, raw_fields = await _deliver_once(redis)
    # Redeliver via XCLAIM until the delivery counter reaches the cap.
    for _ in range(consumer_mod.MAX_DELIVERY_ATTEMPTS - 1):
        await redis.xclaim(STREAM, GROUP, "c1", 0, [entry_id])

    acked = await consumer_mod.handle_entry(
        redis,
        pipeline=None,
        stream=STREAM,
        group=GROUP,
        entry_id=entry_id,
        raw_fields=raw_fields,
    )

    assert acked is True
    pending = await redis.xpending(STREAM, GROUP)
    assert pending["pending"] == 0  # acked — no longer blocking the PEL
    dlq = await redis.xrange(consumer_mod.DLQ_STREAM)
    assert len(dlq) == 1
    dlq_fields = {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in dlq[0][1].items()
    }
    assert dlq_fields["dlq_source_stream"] == STREAM
    assert dlq_fields["dlq_error"] == "poison payload"
    assert dlq_fields["dlq_attempts"] == str(consumer_mod.MAX_DELIVERY_ATTEMPTS)
    assert dlq_fields["tenant_id"] == fields["tenant_id"]
    # Replayable payload, without transport metadata.
    assert "traceparent" not in dlq_fields


async def test_success_acks_and_calls_on_processed(monkeypatch) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    await redis.xadd(STREAM, _fields())

    seen: list = []

    async def ok(event, *, pipeline):
        return {}

    async def on_processed(event):
        seen.append(event)

    monkeypatch.setattr(consumer_mod, "process_inbound", ok)
    entry_id, raw_fields = await _deliver_once(redis)

    acked = await consumer_mod.handle_entry(
        redis,
        pipeline=None,
        stream=STREAM,
        group=GROUP,
        entry_id=entry_id,
        raw_fields=raw_fields,
        on_processed=on_processed,
    )

    assert acked is True
    assert len(seen) == 1
    assert (await redis.xpending(STREAM, GROUP))["pending"] == 0
