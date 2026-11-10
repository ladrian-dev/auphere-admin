"""Flor y Encanto, 2026-10-05: «Y tulipanes?» and, three seconds later,
«y para mañana qué horarios hay?» got two full answers with two sets of
product cards. People send one thought in several bubbles.

Spec 047 (requisitos 1.1 y 2.1, research D43) moves the fold out of the slot:
the slot used to wait in memory and fold what that replica had queued, so two
bubbles read by two replicas still got two turns. Now each entry is **saved and
acked**, and schedules its conversation's turn in the deferred queue; every
bubble pushes the turn back and the turn takes, from the base, everything
without a turn. The end-to-end fold is ``apps/api/tests/integration/
test_turn_coalescing.py``; here, the consumer half.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from fakeredis import aioredis as fakeaioredis

from nexus_worker.runtime import turns
from nexus_worker.runtime.dispatcher import AcceptedInbound
from nexus_worker.streams import consumer as consumer_mod

pytestmark = pytest.mark.asyncio

STREAM = "nexus:inbound"
GROUP = "g"


def _fields(user: str, content: str, tenant: str, channel: str, **extra: str) -> dict[str, str]:
    return {
        "tenant_id": tenant,
        "channel_id": channel,
        "user_id": user,
        "content": content,
        "provider": "meta",
        "provider_message_id": f"wamid.{content[:6]}",
        **extra,
    }


def _fake_accept(saved: list[Any], conversation: dict[str, uuid.UUID]) -> Any:
    async def accept(event: Any) -> AcceptedInbound:
        saved.append(event)
        conv = conversation.setdefault(event.user_id, uuid.uuid4())
        return AcceptedInbound(
            event.tenant_id, event.channel_id, conversation_id=conv, message_id=uuid.uuid4()
        )

    return accept


async def _consume(redis: Any, monkeypatch: Any, *, entries: int, window_ms: int) -> list[Any]:
    saved: list[Any] = []
    ran: list[Any] = []
    monkeypatch.setattr(consumer_mod, "accept_inbound", _fake_accept(saved, {}))

    async def inline(event: Any, *, pipeline: Any) -> dict[str, Any]:
        ran.append(event)
        return {}

    monkeypatch.setattr(consumer_mod, "process_inbound", inline)
    stop = asyncio.Event()
    n = 0

    async def on_processed(event: Any) -> None:
        nonlocal n
        n += 1
        if n >= entries:
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
            coalesce_window_ms=window_ms,
        ),
        timeout=10.0,
    )
    return saved if window_ms else ran


async def test_quick_bubbles_are_saved_acked_and_scheduled_once(monkeypatch) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    tenant, channel = str(uuid.uuid4()), str(uuid.uuid4())
    await redis.xadd(STREAM, _fields("56911112222", "Y tulipanes?", tenant, channel))
    await redis.xadd(STREAM, _fields("56911112222", "y para mañana?", tenant, channel))

    saved = await _consume(redis, monkeypatch, entries=2, window_ms=60_000)

    assert [e.content for e in saved] == ["Y tulipanes?", "y para mañana?"], "each bubble saved"
    assert (await redis.xpending(STREAM, GROUP))["pending"] == 0, "both acked once saved"
    queue = turns.due_queue(STREAM)
    assert await redis.zcard(queue) == 1, "one turn for the conversation, not one per bubble"


async def test_two_conversations_get_their_own_turns(monkeypatch) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    tenant, channel = str(uuid.uuid4()), str(uuid.uuid4())
    await redis.xadd(STREAM, _fields("56911112222", "hola", tenant, channel))
    await redis.xadd(STREAM, _fields("56933334444", "buenas", tenant, channel))

    await _consume(redis, monkeypatch, entries=2, window_ms=60_000)

    assert await redis.zcard(turns.due_queue(STREAM)) == 2


async def test_window_zero_keeps_one_inline_turn_per_bubble(monkeypatch) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    tenant, channel = str(uuid.uuid4()), str(uuid.uuid4())
    await redis.xadd(STREAM, _fields("56911112222", "uno", tenant, channel))
    await redis.xadd(STREAM, _fields("56911112222", "dos", tenant, channel))

    ran = await _consume(redis, monkeypatch, entries=2, window_ms=0)

    assert [e.content for e in ran] == ["uno", "dos"]
    assert await redis.zcard(turns.due_queue(STREAM)) == 0


async def test_an_inline_turn_on_a_busy_conversation_is_scheduled(monkeypatch) -> None:
    """Window 0, the conversation is mid-turn on another replica: the message
    is saved without a turn and waits in the deferred queue for the next one."""
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    tenant, channel = str(uuid.uuid4()), str(uuid.uuid4())
    conversation = uuid.uuid4()
    await redis.xadd(STREAM, _fields("56911112222", "¿sigues?", tenant, channel))

    async def busy(event: Any, *, pipeline: Any) -> dict[str, Any]:
        return {"turn": "busy", "conversation_id": str(conversation)}

    monkeypatch.setattr(consumer_mod, "process_inbound", busy)
    resp = await redis.xreadgroup(groupname=GROUP, consumername="c1", streams={STREAM: ">"})
    entry_id, raw = resp[0][1][0]

    acked = await consumer_mod.handle_entry(
        redis, pipeline=None, stream=STREAM, group=GROUP, entry_id=entry_id, raw_fields=raw
    )

    assert acked is True
    member = turns.member_for(uuid.UUID(tenant), conversation)
    assert await redis.zscore(turns.due_queue(STREAM), member) is not None


async def test_a_save_that_fails_is_not_acked(monkeypatch) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    await redis.xadd(STREAM, _fields("569", "hola", str(uuid.uuid4()), str(uuid.uuid4())))

    async def boom(event: Any) -> AcceptedInbound:
        raise RuntimeError("bd caída")

    monkeypatch.setattr(consumer_mod, "accept_inbound", boom)
    resp = await redis.xreadgroup(groupname=GROUP, consumername="c1", streams={STREAM: ">"})
    entry_id, raw = resp[0][1][0]

    acked = await consumer_mod.handle_entry(
        redis,
        pipeline=None,
        stream=STREAM,
        group=GROUP,
        entry_id=entry_id,
        raw_fields=raw,
        coalesce_window_ms=3000,
    )

    assert acked is False
    assert (await redis.xpending(STREAM, GROUP))["pending"] == 1
    assert await redis.zcard(turns.due_queue(STREAM)) == 0, (
        "nothing scheduled for an unsaved message"
    )
