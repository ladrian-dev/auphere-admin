"""Spec 047, T027 — una respuesta por ráfaga y un turno a la vez por conversación.

Requisitos 1.1 y 1.2 (research D9 y D43). Cada entrante se guarda y programa el
turno de su conversación a +3 s en una cola diferida de Redis, deduplicada por
conversación. El turno toma, con el candado por conversación de la base, todos
los mensajes sin ``turn_id``. Un turno a la vez: el que llega mientras otro
corre espera, y entra en el siguiente.

«Hola» / «quiero cita» / «mañana por la tarde» en menos de 3 s es **un** turno
que los tiene en cuenta todos — no tres respuestas cruzadas (Historia 1).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
from fakeredis import aioredis as fakeaioredis
from nexus_worker.config import WorkerSettings
from nexus_worker.runtime import turns
from nexus_worker.runtime.dispatcher import accept_inbound, run_turn
from nexus_worker.streams import consumer as consumer_mod

from ._turn_world import RecordingPipeline, inbound_rows, make_world

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

STREAM = "nexus:inbound:standard"
GROUP = "nexus-worker"
WINDOW_MS = 3000


def _fields(world: Any, content: str, **extra: str) -> dict[str, str]:
    return {
        "tenant_id": str(world.tenant_id),
        "channel_id": str(world.channel_id),
        "user_id": "+34600111222",
        "content": content,
        "provider": "meta",
        "provider_message_id": f"wamid.{abs(hash(content))}",
        **extra,
    }


async def _consume(
    redis: Any, world: Any, content: str, pipeline: Any, *, window_ms: int = WINDOW_MS, **extra: str
) -> None:
    await redis.xadd(STREAM, _fields(world, content, **extra))
    resp = await redis.xreadgroup(groupname=GROUP, consumername="c1", streams={STREAM: ">"})
    entry_id, raw = resp[0][1][0]
    acked = await consumer_mod.handle_entry(
        redis,
        pipeline=pipeline,
        stream=STREAM,
        group=GROUP,
        entry_id=entry_id,
        raw_fields=raw,
        coalesce_window_ms=window_ms,
    )
    assert acked is True, "guardado y programado: el stream ya no lo necesita"


async def test_three_quick_messages_are_one_turn(db_session) -> None:
    world = await make_world(db_session)
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    pipeline = RecordingPipeline()

    for text in ("hola", "quiero cita", "mañana por la tarde"):
        await _consume(redis, world, text, pipeline)
    assert pipeline.calls == [], "el turno espera a que acabe la ráfaga"

    queue = turns.due_queue(STREAM)
    early = await consumer_mod.drain_due_turns(
        redis, queues=[queue], pipeline=pipeline, now_ms=int(time.time() * 1000)
    )
    assert early == 0, "dentro de la ventana no se abre ningún turno"

    ran = await consumer_mod.drain_due_turns(
        redis,
        queues=[queue],
        pipeline=pipeline,
        now_ms=int(time.time() * 1000) + WINDOW_MS + 1,
    )

    assert ran == 1
    assert len(pipeline.calls) == 1, "una sola respuesta para la ráfaga"
    said = pipeline.calls[0]["user_message"]
    assert said.index("hola") < said.index("quiero cita") < said.index("mañana por la tarde")
    rows = await inbound_rows(world)
    assert len(rows) == 3
    assert {r.turn_id for r in rows} == {rows[0].id}, "los tres en el mismo turno"
    assert await redis.zcard(queue) == 0, "el turno acabó: no queda nada programado"


async def _drain(redis: Any, pipeline: Any) -> int:
    return await consumer_mod.drain_due_turns(
        redis,
        queues=[turns.due_queue(STREAM)],
        pipeline=pipeline,
        now_ms=int(time.time() * 1000) + WINDOW_MS + 1,
    )


def _reaction(emoji: str, provider: str = "meta") -> dict[str, str]:
    return {"reaction_emoji": emoji, "reaction_target_wamid": "mid.abc", "provider": provider}


@pytest.mark.parametrize(
    ("content", "emoji", "provider"),
    [
        ("[reaction:❤:on=mid.abc]", "❤", "meta"),
        ("[reaction:❤:on=mid.abc]", "❤", "meta_instagram"),
        ("[reaction:(removed):on=mid.abc]", "", "meta_messenger"),
    ],
)
async def test_a_reaction_is_kept_and_opens_no_turn(db_session, content, emoji, provider) -> None:
    """Spec 049: «se registran sin disparar al agente». Ocurrió en WhatsApp en
    staging el 2026-10-31: un corazón gastó un turno y el agente contestó."""
    world = await make_world(db_session)
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    pipeline = RecordingPipeline()

    await _consume(redis, world, content, pipeline, **_reaction(emoji, provider))

    assert await redis.zcard(turns.due_queue(STREAM)) == 0, "nada programado"
    assert await _drain(redis, pipeline) == 0
    assert pipeline.calls == []
    [row] = await inbound_rows(world)
    assert row.content == content, "la bandeja la sigue enseñando"
    assert row.skipped_reason is None
    assert row.turn_id is None


async def test_a_reaction_opens_no_turn_without_a_window(db_session) -> None:
    world = await make_world(db_session)
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    pipeline = RecordingPipeline()

    await _consume(redis, world, "[reaction:❤:on=mid.abc]", pipeline, window_ms=0, **_reaction("❤"))

    assert pipeline.calls == []


@pytest.mark.parametrize("reaction_first", [True, False])
async def test_a_reaction_stays_out_of_the_turn_of_a_message(db_session, reaction_first) -> None:
    """Ni antes ni dentro de la ráfaga: el agente solo lee lo que le escribieron."""
    world = await make_world(db_session)
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    pipeline = RecordingPipeline()
    reaction = ("[reaction:❤:on=mid.abc]", _reaction("❤"))
    text = ("¿abrís mañana?", {})

    for content, extra in (reaction, text) if reaction_first else (text, reaction):
        await _consume(redis, world, content, pipeline, **extra)

    assert await _drain(redis, pipeline) == 1
    assert [c["user_message"] for c in pipeline.calls] == ["¿abrís mañana?"]
    by_content = {r.content: r for r in await inbound_rows(world)}
    assert by_content["¿abrís mañana?"].turn_id is not None
    assert by_content["[reaction:❤:on=mid.abc]"].turn_id is None


async def test_a_redelivered_reaction_still_opens_no_turn(db_session) -> None:
    world = await make_world(db_session)
    reaction = world.event(
        "[reaction:❤:on=mid.abc]",
        wamid="reaction:mid.abc:1",
        reaction_emoji="❤",
        reaction_target_wamid="mid.abc",
    )

    first = await accept_inbound(reaction)
    again = await accept_inbound(reaction)

    assert first.no_turn == "reaction"
    assert again.duplicate and again.no_turn == "reaction"


async def test_each_message_pushes_the_turn_back(db_session) -> None:
    """La ventana cuenta desde el último mensaje, no desde el primero."""
    world = await make_world(db_session)
    redis = fakeaioredis.FakeRedis()
    queue = turns.due_queue(STREAM)
    first = await accept_inbound(world.event("hola"))
    assert first.conversation_id is not None
    t0 = 1_000_000

    await turns.schedule_turn(
        redis,
        queue=queue,
        tenant_id=world.tenant_id,
        conversation_id=first.conversation_id,
        window_ms=WINDOW_MS,
        now_ms=t0,
    )
    await turns.schedule_turn(
        redis,
        queue=queue,
        tenant_id=world.tenant_id,
        conversation_id=first.conversation_id,
        window_ms=WINDOW_MS,
        now_ms=t0 + 2000,
    )

    member = turns.member_for(world.tenant_id, first.conversation_id)
    assert await redis.zscore(queue, member) == t0 + 2000 + WINDOW_MS
    assert await redis.zcard(queue) == 1, "deduplicada por conversación"


async def test_a_burst_that_never_stops_still_gets_an_answer(db_session) -> None:
    """Un contacto que escribe cada 2 s no deja al turno esperando para siempre."""
    world = await make_world(db_session)
    redis = fakeaioredis.FakeRedis()
    queue = turns.due_queue(STREAM)
    acc = await accept_inbound(world.event("hola"))
    assert acc.conversation_id is not None
    t0 = 1_000_000
    for i in range(30):
        await turns.schedule_turn(
            redis,
            queue=queue,
            tenant_id=world.tenant_id,
            conversation_id=acc.conversation_id,
            window_ms=WINDOW_MS,
            now_ms=t0 + i * 2000,
        )

    member = turns.member_for(world.tenant_id, acc.conversation_id)
    assert await redis.zscore(queue, member) == t0 + turns.max_wait_ms(WINDOW_MS)


async def test_a_message_during_a_turn_goes_into_the_next(db_session) -> None:
    world = await make_world(db_session)
    block = asyncio.Event()
    pipeline = RecordingPipeline(block=block)
    first = await accept_inbound(world.event("hola"))
    assert first.conversation_id is not None
    running = asyncio.create_task(
        run_turn(
            tenant_id=world.tenant_id, conversation_id=first.conversation_id, pipeline=pipeline
        )
    )
    await asyncio.wait_for(pipeline.started.wait(), timeout=10)

    await accept_inbound(world.event("¿sigues ahí?"))
    busy = await run_turn(
        tenant_id=world.tenant_id, conversation_id=first.conversation_id, pipeline=pipeline
    )
    assert busy["turn"] == "busy", "un turno a la vez por conversación"

    block.set()
    await asyncio.wait_for(running, timeout=10)
    await run_turn(
        tenant_id=world.tenant_id, conversation_id=first.conversation_id, pipeline=pipeline
    )

    assert [c["user_message"] for c in pipeline.calls] == ["hola", "¿sigues ahí?"]
    rows = await inbound_rows(world)
    assert rows[0].turn_id != rows[1].turn_id


async def test_two_workers_never_open_two_turns_of_one_conversation(db_session) -> None:
    world = await make_world(db_session)
    block = asyncio.Event()
    pipeline = RecordingPipeline(block=block)
    acc = await accept_inbound(world.event("hola"))
    assert acc.conversation_id is not None

    one = asyncio.create_task(
        run_turn(tenant_id=world.tenant_id, conversation_id=acc.conversation_id, pipeline=pipeline)
    )
    other = asyncio.create_task(
        run_turn(tenant_id=world.tenant_id, conversation_id=acc.conversation_id, pipeline=pipeline)
    )
    await asyncio.wait_for(pipeline.started.wait(), timeout=10)
    done, _ = await asyncio.wait({one, other}, timeout=10, return_when=asyncio.FIRST_COMPLETED)
    loser = done.pop()
    outcome = loser.result()
    assert outcome.get("turn") in {"busy", "none"}, outcome

    block.set()
    await asyncio.wait_for(asyncio.gather(one, other), timeout=10)
    assert len(pipeline.calls) == 1


async def test_a_busy_conversation_is_tried_again_after_the_window(db_session) -> None:
    """La cola diferida no pierde al que encontró la conversación ocupada."""
    world = await make_world(db_session)
    redis = fakeaioredis.FakeRedis()
    queue = turns.due_queue(STREAM)
    block = asyncio.Event()
    pipeline = RecordingPipeline(block=block)
    acc = await accept_inbound(world.event("hola"))
    assert acc.conversation_id is not None
    running = asyncio.create_task(
        run_turn(tenant_id=world.tenant_id, conversation_id=acc.conversation_id, pipeline=pipeline)
    )
    await asyncio.wait_for(pipeline.started.wait(), timeout=10)
    await accept_inbound(world.event("¿sigues ahí?"))
    now = int(time.time() * 1000)
    await turns.schedule_turn(
        redis,
        queue=queue,
        tenant_id=world.tenant_id,
        conversation_id=acc.conversation_id,
        window_ms=WINDOW_MS,
        now_ms=now,
    )

    await consumer_mod.drain_due_turns(
        redis, queues=[queue], pipeline=pipeline, now_ms=now + WINDOW_MS + 1
    )
    member = turns.member_for(world.tenant_id, acc.conversation_id)
    score = await redis.zscore(queue, member)
    assert score is not None, "sigue programada para cuando acabe el turno"

    block.set()
    await asyncio.wait_for(running, timeout=10)
    await consumer_mod.drain_due_turns(redis, queues=[queue], pipeline=pipeline, now_ms=int(score))

    assert [c["user_message"] for c in pipeline.calls] == ["hola", "¿sigues ahí?"]


def test_the_window_is_a_platform_setting(monkeypatch) -> None:
    """Tres segundos por defecto (research, Parte 7); Auphere la cambia por
    despliegue con ``NEXUS_RUNNER_COALESCE_WINDOW_MS``."""
    monkeypatch.delenv("NEXUS_RUNNER_COALESCE_WINDOW_MS", raising=False)
    assert WorkerSettings(_env_file=None).runner_coalesce_window_ms == 3000
    monkeypatch.setenv("NEXUS_RUNNER_COALESCE_WINDOW_MS", "1500")
    assert WorkerSettings(_env_file=None).runner_coalesce_window_ms == 1500
