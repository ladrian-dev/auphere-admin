"""Reinyectar una entrada de la DLQ no contesta dos veces. Bug ``dlq-sin-salida``.

Contra la base de verdad, por los caminos de verdad: la herramienta republica, el
consumidor guarda y programa, y el turno toma lo que haya sin tomar. La
idempotencia tiene dos capas: ``provider_message_id`` evita la segunda fila y
``messages.turn_id`` evita el segundo turno.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
import sqlalchemy as sa
from fakeredis import aioredis as fakeaioredis
from nexus_worker.ops import dlq
from nexus_worker.runtime import turns
from nexus_worker.runtime.dispatcher import accept_inbound
from nexus_worker.streams import consumer as consumer_mod

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Conversation

from ._turn_world import RecordingPipeline, inbound_rows, make_world

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

STREAM = "nexus:inbound:standard"
GROUP = "nexus-worker"
WINDOW_MS = 3000
REINJECT = ["reinject", "--all", "--yes", "--reason", "prueba"]


def _fields(world: Any, *, wamid: str = "wamid.reinjected") -> dict[str, str]:
    return {
        "tenant_id": str(world.tenant_id),
        "channel_id": str(world.channel_id),
        "user_id": "+34600111222",
        "content": "quiero cita",
        "provider": "meta",
        "provider_message_id": wamid,
    }


async def _redis() -> Any:
    redis = fakeaioredis.FakeRedis()
    await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    return redis


async def _consume_all(redis: Any, pipeline: Any) -> int:
    """Lee lo que haya en el stream, como el consumidor. Devuelve cuántas entradas."""
    resp = await redis.xreadgroup(groupname=GROUP, consumername="c1", streams={STREAM: ">"})
    count = 0
    for _stream, entries in resp or []:
        for entry_id, raw in entries:
            acked = await consumer_mod.handle_entry(
                redis,
                pipeline=pipeline,
                stream=STREAM,
                group=GROUP,
                entry_id=entry_id,
                raw_fields=raw,
                coalesce_window_ms=WINDOW_MS,
            )
            assert acked is True
            count += 1
    return count


async def _drain(redis: Any, pipeline: Any) -> int:
    return await consumer_mod.drain_due_turns(
        redis,
        queues=[turns.due_queue(STREAM)],
        pipeline=pipeline,
        now_ms=int(time.time() * 1000) + WINDOW_MS + 1,
    )


async def _park(redis: Any, fields: dict[str, str]) -> None:
    """Pasa la entrada a la DLQ por el mismo ``_dead_letter`` del consumidor."""
    await redis.xadd(STREAM, fields)
    resp = await redis.xreadgroup(groupname=GROUP, consumername="c1", streams={STREAM: ">"})
    entry_id, raw = resp[0][1][0]
    await consumer_mod._dead_letter(
        redis,
        stream=STREAM,
        group=GROUP,
        entry_id=entry_id.decode(),
        fields=consumer_mod._decode_fields(raw),
        error="password authentication failed",
        attempts=5,
    )


async def test_an_entry_that_was_never_saved_is_answered_once(db_session) -> None:
    """Los 25 de prod: sin base no hubo fila. Reinyectada, es un mensaje nuevo."""
    world = await make_world(db_session)
    redis = await _redis()
    pipeline = RecordingPipeline()
    await _park(redis, _fields(world))
    assert await inbound_rows(world) == []

    assert await dlq.run(redis, REINJECT) == 0
    assert await _consume_all(redis, pipeline) == 1
    assert await _drain(redis, pipeline) == 1

    assert len(pipeline.calls) == 1
    assert len(await inbound_rows(world)) == 1


async def test_reinjecting_what_was_already_answered_answers_nothing(db_session) -> None:
    world = await make_world(db_session)
    redis = await _redis()
    pipeline = RecordingPipeline()
    fields = _fields(world)

    await redis.xadd(STREAM, fields)
    await _consume_all(redis, pipeline)
    await _drain(redis, pipeline)
    assert len(pipeline.calls) == 1

    # La misma entrada acaba en la DLQ (el acuse se perdió, por ejemplo).
    await _park(redis, fields)
    assert await dlq.run(redis, REINJECT) == 0
    assert await _consume_all(redis, pipeline) == 1
    assert await _drain(redis, pipeline) == 0

    assert len(pipeline.calls) == 1, "no contesta dos veces"
    assert len(await inbound_rows(world)) == 1, "ni guarda dos veces"


async def test_a_second_copy_of_the_same_message_answers_nothing(db_session) -> None:
    """Si dos operadores reinyectan a la vez, o una tarea se repite tras un corte:
    la segunda copia se encuentra el mensaje ya tomado."""
    world = await make_world(db_session)
    redis = await _redis()
    pipeline = RecordingPipeline()

    await _park(redis, _fields(world))
    await redis.xadd(dlq.DLQ_STREAM, (await _dlq_fields(redis)))
    assert await redis.xlen(dlq.DLQ_STREAM) == 2
    assert await dlq.run(redis, REINJECT) == 0
    assert await _consume_all(redis, pipeline) == 2
    await _drain(redis, pipeline)

    assert len(pipeline.calls) == 1
    assert len(await inbound_rows(world)) == 1


async def _dlq_fields(redis: Any) -> dict[bytes, bytes]:
    [(_entry_id, fields)] = await redis.xrange(dlq.DLQ_STREAM)
    return dict(fields)


async def test_saved_without_a_turn_and_recent_gets_its_turn(db_session) -> None:
    """Murió después de guardarse (al programar el turno): sigue dentro del
    horizonte de 15 minutos, y el turno lo toma."""
    world = await make_world(db_session)
    redis = await _redis()
    pipeline = RecordingPipeline()

    await accept_inbound(world.event("quiero cita", wamid="wamid.reinjected"))
    await _park(redis, _fields(world))
    assert await dlq.run(redis, REINJECT) == 0
    await _consume_all(redis, pipeline)
    await _drain(redis, pipeline)

    assert len(pipeline.calls) == 1
    assert len(await inbound_rows(world)) == 1


async def test_saved_without_a_turn_and_old_stays_unanswered(db_session) -> None:
    """Pasado ``UNTAKEN_HORIZON`` no se contesta: el mensaje está en la bandeja y
    es una persona quien lo ve. Reinyectar no lo revive. Es lo que dice el runbook."""
    world = await make_world(db_session)
    redis = await _redis()
    pipeline = RecordingPipeline()

    accepted = await accept_inbound(world.event("quiero cita", wamid="wamid.reinjected"))
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, world.tenant_id):
        await session.execute(
            sa.text("UPDATE messages SET created_at = now() - interval '1 hour' WHERE id = :id"),
            {"id": accepted.message_id},
        )
        await session.commit()

    await _park(redis, _fields(world))
    assert await dlq.run(redis, REINJECT) == 0
    await _consume_all(redis, pipeline)
    await _drain(redis, pipeline)

    assert pipeline.calls == []
    assert len(await inbound_rows(world)) == 1


async def test_a_reinjected_message_moves_the_meta_window(db_session) -> None:
    """Por qué hay barrera de 24 h: una entrada que nunca se guardó se trata como
    recién llegada, y la ventana de Meta se cuenta desde ahora, no desde cuando el
    cliente escribió. Si esta prueba cambia, revisa ``REINJECT_MAX_AGE_S``."""
    world = await make_world(db_session)
    redis = await _redis()
    pipeline = RecordingPipeline()
    await _park(redis, _fields(world))
    before = time.time()

    assert await dlq.run(redis, REINJECT) == 0
    await _consume_all(redis, pipeline)

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, world.tenant_id):
        moved = await session.scalar(
            sa.select(Conversation.last_inbound_at).where(
                Conversation.channel_id == world.channel_id
            )
        )
    assert moved is not None
    assert moved.timestamp() >= before - 1
