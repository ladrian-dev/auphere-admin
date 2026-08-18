"""El registro de runs del Companion — log durable y reanudación (CO-01).

Lo que estas pruebas defienden es la corrección C1 de la investigación: el
run no muere con la conexión, y reengancharse no pierde ni duplica un solo
evento. Todo sobre ``fakeredis``, sin base de datos ni LLM.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from nexus_api.api import companion_streaming as streaming

pytestmark = pytest.mark.asyncio


def _frames(wire: list[str]) -> list[tuple[int, str, dict]]:
    """Parsea el formato de cable SSE a (seq, evento, datos)."""
    out: list[tuple[int, str, dict]] = []
    for frame in wire:
        seq = event = None
        data: dict = {}
        for line in frame.strip().splitlines():
            if line.startswith("id: "):
                seq = int(line[4:])
            elif line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        out.append((seq or 0, event or "", data))
    return out


# ── catálogo cerrado ───────────────────────────────────────────────────


async def test_publish_refuses_an_event_outside_the_catalogue(fake_redis) -> None:
    with pytest.raises(streaming.UnknownCompanionEvent):
        await streaming.publish(fake_redis, uuid.uuid4(), seq=1, event="tool.result", data={"x": 1})


async def test_publish_drops_undeclared_keys(fake_redis) -> None:
    """La defensa real de C8: aunque alguien meta el cuerpo de un mensaje
    ajeno en un payload, no llega al log."""
    run_id = uuid.uuid4()
    await streaming.publish(
        fake_redis,
        run_id,
        seq=1,
        event="text.delta",
        data={"message_id": "m1", "text": "hola", "content": "lo que escribió un cliente"},
    )
    events, _gap = await streaming.read_events(fake_redis, run_id)
    assert events[0].data == {"message_id": "m1", "text": "hola"}


async def test_the_key_filter_is_not_a_no_op() -> None:
    """Control del control: si el filtro dejara de filtrar, esto falla."""
    clean = streaming.sanitise_payload("cost.updated", {"input_tokens": 5, "content": "x"})
    assert clean == {"input_tokens": 5}


async def test_the_log_carries_a_ttl(fake_redis) -> None:
    run_id = uuid.uuid4()
    await streaming.publish(fake_redis, run_id, seq=1, event="ping", data={"ts": 1.0})
    ttl = await fake_redis.ttl(streaming.run_key(run_id))
    assert 0 < ttl <= streaming.RUN_LOG_TTL_SECONDS


# ── historial y reanudación ────────────────────────────────────────────


async def test_read_events_filters_by_since_seq(fake_redis) -> None:
    run_id = uuid.uuid4()
    for seq in range(1, 6):
        await streaming.publish(
            fake_redis, run_id, seq=seq, event="text.delta", data={"text": str(seq)}
        )
    events, gap = await streaming.read_events(fake_redis, run_id, since_seq=3)
    assert [e.seq for e in events] == [4, 5]
    assert gap is None


async def test_read_events_signals_where_the_log_starts_when_it_rotated(fake_redis) -> None:
    """El hueco no es un callejón sin salida: dice desde dónde se puede
    seguir. Sin ese dato, ``resume.gap`` solo sirve para asustar."""
    run_id = uuid.uuid4()
    for seq in (40, 41, 42):
        await streaming.publish(fake_redis, run_id, seq=seq, event="text.delta", data={"text": "x"})
    events, gap = await streaming.read_events(fake_redis, run_id, since_seq=5)
    assert gap == 40
    assert [e.seq for e in events] == [40, 41, 42]


async def test_read_events_on_an_expired_log_is_empty_not_an_error(fake_redis) -> None:
    events, gap = await streaming.read_events(fake_redis, uuid.uuid4())
    assert events == [] and gap is None


# ── stream ─────────────────────────────────────────────────────────────


async def test_stream_replays_then_ends_on_the_terminal_event(fake_redis) -> None:
    run_id = uuid.uuid4()
    await streaming.publish(
        fake_redis, run_id, seq=1, event="run.started", data={"run_id": str(run_id)}
    )
    await streaming.publish(fake_redis, run_id, seq=2, event="text.delta", data={"text": "ho"})
    await streaming.publish(
        fake_redis, run_id, seq=3, event="run.completed", data={"status": "completed"}
    )

    wire = [f async for f in streaming.subscribe(fake_redis, run_id)]
    assert [(s, e) for s, e, _ in _frames(wire)] == [
        (1, "run.started"),
        (2, "text.delta"),
        (3, "run.completed"),
    ]


async def test_reconnecting_with_since_seq_loses_nothing_and_repeats_nothing(
    fake_redis,
) -> None:
    """El criterio de aceptación literal de CO-01: matar la conexión a
    mitad de run y reconectar con ``since_seq``."""
    run_id = uuid.uuid4()
    for seq in range(1, 4):
        await streaming.publish(
            fake_redis, run_id, seq=seq, event="text.delta", data={"text": f"t{seq}"}
        )

    first: list[str] = []
    agen = streaming.subscribe(fake_redis, run_id)
    async for frame in agen:
        first.append(frame)
        if len(first) == 2:
            await agen.aclose()  # el portátil se cierra aquí
            break
    seen = [s for s, _e, _d in _frames(first)]
    assert seen == [1, 2]

    # El trabajo siguió mientras nadie miraba.
    for seq in (4, 5):
        await streaming.publish(
            fake_redis, run_id, seq=seq, event="text.delta", data={"text": f"t{seq}"}
        )
    await streaming.publish(
        fake_redis, run_id, seq=6, event="run.completed", data={"status": "completed"}
    )

    second = [f async for f in streaming.subscribe(fake_redis, run_id, since_seq=max(seen))]
    resumed = [s for s, _e, _d in _frames(second)]
    assert resumed == [3, 4, 5, 6]
    assert not set(seen) & set(resumed), "un evento entregado dos veces"


async def test_stream_of_an_expired_log_says_so_instead_of_hanging(fake_redis) -> None:
    wire = [f async for f in streaming.subscribe(fake_redis, uuid.uuid4())]
    assert _frames(wire)[0][1] == "resume.gap"


async def test_stream_closes_when_the_row_is_terminal_without_a_terminal_event(
    fake_redis, monkeypatch
) -> None:
    """El proceso que ejecutaba el run murió sin escribir el cierre. Sin
    esta salida el cajón haría ping para siempre contra un run que ya no
    ejecuta nadie."""
    monkeypatch.setattr(streaming, "PING_INTERVAL_SECONDS", 0.05)
    run_id = uuid.uuid4()
    await streaming.publish(
        fake_redis, run_id, seq=1, event="run.started", data={"run_id": str(run_id)}
    )

    async def _terminal() -> str:
        return "interrupted"

    frames: list[str] = []
    async for frame in streaming.subscribe(fake_redis, run_id, terminal_check=_terminal):
        frames.append(frame)
        if len(frames) > 5:  # pragma: no cover - red de seguridad del test
            pytest.fail("el stream no cerró")
    parsed = _frames(frames)
    assert parsed[-1][1] == "run.completed"
    assert parsed[-1][2]["status"] == "interrupted"


# ── ciclo de vida ──────────────────────────────────────────────────────


async def test_a_run_always_writes_its_terminal_event(fake_redis) -> None:
    run_id, thread_id = uuid.uuid4(), uuid.uuid4()

    async def _driver(handle: streaming.CompanionRunHandle) -> None:
        await handle.emit("text.delta", {"text": "hola"})

    handle = await streaming.start_run(
        redis=fake_redis,
        run_id=run_id,
        thread_id=thread_id,
        principal_id="user_1",
        driver=_driver,
    )
    await handle.task
    events, _ = await streaming.read_events(fake_redis, run_id)
    assert [e.event for e in events] == ["run.started", "text.delta", "run.completed"]
    assert events[-1].data["status"] == "completed"


async def test_a_failing_driver_closes_as_error_not_as_silence(fake_redis) -> None:
    run_id = uuid.uuid4()

    async def _driver(handle: streaming.CompanionRunHandle) -> None:
        raise RuntimeError("boom")

    handle = await streaming.start_run(
        redis=fake_redis,
        run_id=run_id,
        thread_id=uuid.uuid4(),
        principal_id="user_1",
        driver=_driver,
    )
    await handle.task
    events, _ = await streaming.read_events(fake_redis, run_id)
    assert events[-1].event == "run.completed"
    assert events[-1].data["status"] == "error"


async def test_cancel_stops_a_local_run(fake_redis) -> None:
    run_id = uuid.uuid4()
    started = asyncio.Event()

    async def _driver(handle: streaming.CompanionRunHandle) -> None:
        started.set()
        await asyncio.sleep(30)

    handle = await streaming.start_run(
        redis=fake_redis,
        run_id=run_id,
        thread_id=uuid.uuid4(),
        principal_id="user_1",
        driver=_driver,
    )
    await started.wait()
    assert await streaming.cancel(fake_redis, run_id) is True
    await handle.task
    events, _ = await streaming.read_events(fake_redis, run_id)
    assert events[-1].data["status"] == "cancelled"


async def test_cancel_of_a_foreign_run_still_raises_the_flag(fake_redis) -> None:
    """El DELETE puede caer en una réplica que no ejecuta ese run. La
    bandera es lo que lo para de todos modos."""
    run_id = uuid.uuid4()
    assert await streaming.cancel(fake_redis, run_id) is False
    assert await fake_redis.exists(streaming.cancel_key(run_id))


async def test_the_driver_notices_a_cancel_raised_elsewhere(fake_redis, monkeypatch) -> None:
    monkeypatch.setattr(streaming, "CANCEL_POLL_EVERY_EVENTS", 2)
    run_id = uuid.uuid4()
    await fake_redis.set(streaming.cancel_key(run_id), "1")

    emitted = 0

    async def _driver(handle: streaming.CompanionRunHandle) -> None:
        nonlocal emitted
        for _ in range(50):
            await handle.emit("text.delta", {"text": "x"})
            emitted += 1

    handle = await streaming.start_run(
        redis=fake_redis,
        run_id=run_id,
        thread_id=uuid.uuid4(),
        principal_id="user_1",
        driver=_driver,
    )
    await handle.task
    assert emitted < 50, "el driver ignoró la bandera de cancelación"
    events, _ = await streaming.read_events(fake_redis, run_id)
    assert events[-1].data["status"] == "cancelled"


async def test_append_terminal_event_continues_the_sequence(fake_redis) -> None:
    """El reaper cierra el log de un run huérfano. Si el ``seq`` volviera a
    empezar, un lector reconectado vería el cierre como algo ya visto y se
    quedaría esperando."""
    run_id = uuid.uuid4()
    for seq in (1, 2, 3):
        await streaming.publish(fake_redis, run_id, seq=seq, event="text.delta", data={"text": "x"})
    await streaming.append_terminal_event(fake_redis, run_id, status="interrupted")
    events, _ = await streaming.read_events(fake_redis, run_id, since_seq=3)
    assert len(events) == 1
    assert events[0].seq == 4
    assert events[0].data["status"] == "interrupted"
