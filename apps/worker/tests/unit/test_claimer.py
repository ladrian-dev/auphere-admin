"""WP-04: the stream claimer recovers entries orphaned by a dead replica.

Scenario pinned here: consumer ``c-dead`` reads an entry (it lands in its
PEL) and the process dies before acking. ``claim_once`` running on another
replica takes ownership via XAUTOCLAIM and delivers the message through the
same ``handle_entry`` path — the customer gets their reply instead of
silence. Entries idle for less than ``min_idle_ms`` are left alone (their
owner may still be mid-turn).
"""

from __future__ import annotations

import uuid

import pytest
from fakeredis import aioredis as fakeaioredis

from nexus_worker.streams import claimer as claimer_mod
from nexus_worker.streams import consumer as consumer_mod

pytestmark = pytest.mark.asyncio

STREAM = "nexus:inbound"
GROUP = "g"


def _fields() -> dict[str, str]:
    return {
        "tenant_id": str(uuid.uuid4()),
        "channel_id": str(uuid.uuid4()),
        "user_id": "56911112222",
        "content": "hola",
        "provider": "meta",
    }


async def _orphan_entry(redis) -> None:
    """Deliver one entry to a consumer that will never ack it."""
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    await redis.xadd(STREAM, _fields())
    await redis.xreadgroup(
        groupname=GROUP, consumername="c-dead", streams={STREAM: ">"}, count=1
    )


async def test_orphaned_entry_is_reclaimed_and_processed(monkeypatch) -> None:
    redis = fakeaioredis.FakeRedis()
    await _orphan_entry(redis)

    processed: list = []

    async def ok(event, *, pipeline):
        processed.append(event)
        return {}

    monkeypatch.setattr(consumer_mod, "process_inbound", ok)

    reclaimed = await claimer_mod.claim_once(
        redis,
        None,
        stream=STREAM,
        group=GROUP,
        consumer_name="c-alive-claimer",
        min_idle_ms=0,  # everything counts as orphaned in the test
    )

    assert reclaimed == 1
    assert len(processed) == 1
    assert (await redis.xpending(STREAM, GROUP))["pending"] == 0


async def test_fresh_entries_are_not_stolen(monkeypatch) -> None:
    redis = fakeaioredis.FakeRedis()
    await _orphan_entry(redis)

    async def ok(event, *, pipeline):
        return {}

    monkeypatch.setattr(consumer_mod, "process_inbound", ok)

    reclaimed = await claimer_mod.claim_once(
        redis,
        None,
        stream=STREAM,
        group=GROUP,
        consumer_name="c-alive-claimer",
        min_idle_ms=3_600_000,  # one hour — nothing is that old yet
    )

    assert reclaimed == 0
    # Still pending, still owned by the dead consumer.
    assert (await redis.xpending(STREAM, GROUP))["pending"] == 1


async def test_backlog_hook_fires_over_threshold(monkeypatch) -> None:
    redis = fakeaioredis.FakeRedis()
    await _orphan_entry(redis)

    calls: list[tuple[int, float]] = []

    async def hook(count: int, oldest_age_s: float) -> None:
        calls.append((count, oldest_age_s))

    monkeypatch.setattr(claimer_mod, "BACKLOG_COUNT_THRESHOLD", 0)
    await claimer_mod._check_backlog(redis, stream=STREAM, group=GROUP, on_backlog=hook)

    assert len(calls) == 1
    assert calls[0][0] == 1  # one pending entry
