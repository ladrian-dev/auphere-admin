"""Flor y Encanto, 2026-10-05: «Y tulipanes?» and, three seconds later,
«y para mañana qué horarios hay?» got two full answers with two sets of
product cards. People send one thought in several bubbles; the slot waits a
moment and answers everything that is waiting in one turn."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fakeredis import aioredis as fakeaioredis

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


def _item(fields: dict[str, str]) -> tuple[str, bytes, dict[bytes, bytes]]:
    return (STREAM, b"1-0", {k.encode(): v.encode() for k, v in fields.items()})


def test_fold_followups_merges_text_of_the_same_conversation_in_order() -> None:
    t, c = str(uuid.uuid4()), str(uuid.uuid4())
    first = _fields("569", "Y tulipanes?", t, c)
    queued = [
        _item(_fields("569", "y para mañana qué horarios hay?", t, c)),
        _item(_fields("569", "gracias", t, c)),
        _item(_fields("570", "hola", t, c)),  # another customer: stops here
        _item(_fields("569", "y esto?", t, c)),  # never reached, order kept
    ]
    merged, folded = consumer_mod.fold_followups(first, queued)
    assert merged["content"] == "Y tulipanes?\ny para mañana qué horarios hay?\ngracias"
    assert len(folded) == 2
    event = consumer_mod._to_event(merged)
    assert event.content.startswith("Y tulipanes?")
    assert [t for t, _ in event.folded] == ["y para mañana qué horarios hay?", "gracias"]
    assert event.folded[0][1] == "wamid.y para"


def test_fold_followups_leaves_media_reactions_and_replies_alone() -> None:
    t, c = str(uuid.uuid4()), str(uuid.uuid4())
    first = _fields("569", "ya pagué", t, c)
    receipt = _fields("569", "", t, c, kind="image", media_provider_id="m1")
    merged, folded = consumer_mod.fold_followups(first, [_item(receipt)])
    assert folded == [] and merged == first
    # An image first: its own turn, nothing folds into it.
    merged, folded = consumer_mod.fold_followups(receipt, [_item(first)])
    assert folded == []
    reply = _fields("569", "ese", t, c, context_message_id="wamid.x")
    assert consumer_mod.fold_followups(first, [_item(reply)])[1] == []
    reaction = _fields("569", "", t, c, kind="reaction", reaction_emoji="❤️")
    assert consumer_mod.fold_followups(first, [_item(reaction)])[1] == []


async def test_two_quick_bubbles_become_one_turn_and_both_are_acked(monkeypatch) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    tenant, channel = str(uuid.uuid4()), str(uuid.uuid4())
    await redis.xadd(STREAM, _fields("56911112222", "Y tulipanes?", tenant, channel))
    await redis.xadd(STREAM, _fields("56911112222", "y para mañana?", tenant, channel))

    seen: list = []

    async def record(event, *, pipeline):
        seen.append(event)
        return {}

    monkeypatch.setattr(consumer_mod, "process_inbound", record)
    stop = asyncio.Event()

    async def on_processed(event):
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
            coalesce_window_ms=100,
        ),
        timeout=10.0,
    )
    assert len(seen) == 1, [e.content for e in seen]
    assert seen[0].content == "Y tulipanes?\ny para mañana?"
    assert [t for t, _ in seen[0].folded] == ["y para mañana?"]
    pending = await redis.xpending(STREAM, GROUP)
    assert pending["pending"] == 0


async def test_window_zero_keeps_one_turn_per_bubble(monkeypatch) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    tenant, channel = str(uuid.uuid4()), str(uuid.uuid4())
    await redis.xadd(STREAM, _fields("56911112222", "uno", tenant, channel))
    seen: list = []

    async def record(event, *, pipeline):
        seen.append(event.content)
        await redis.xadd(STREAM, _fields("56911112222", "dos", tenant, channel))
        return {}

    monkeypatch.setattr(consumer_mod, "process_inbound", record)
    stop = asyncio.Event()
    n = 0

    async def on_processed(event):
        nonlocal n
        n += 1
        if n >= 2:
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
            coalesce_window_ms=0,
        ),
        timeout=10.0,
    )
    assert seen == ["uno", "dos"]
