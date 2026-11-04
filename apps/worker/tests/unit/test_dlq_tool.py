"""La salida de ``nexus:inbound:dlq``: listar, descartar y reinyectar.

Bug ``dlq-sin-salida``. El vigilante decía «revisar y reinyectar» y no había con
qué. Estas pruebas fijan lo que la herramienta promete al operador: en seco por
defecto, un registro por cada escritura, y nunca el cuerpo ni un teléfono.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from typing import Any

import pytest
from fakeredis import aioredis as fakeaioredis
from nexus_api.core.streams import INBOUND_DLQ_STREAM
from structlog.testing import capture_logs

from nexus_worker.ops import dlq
from nexus_worker.streams import consumer as consumer_mod
from nexus_worker.streams import platform_watcher as watcher

pytestmark = pytest.mark.asyncio

STREAM = "nexus:inbound:standard"
GROUP = "nexus-worker"
DAY = 86_400
PHONE = "34600111222"
BODY = "quiero cancelar mi cita de las cinco"
WAMID = "wamid.HBgLMzQ2MDAxMTEyMjIVAgASGBQzQTdC"


def _original(**extra: str) -> dict[str, str]:
    return {
        "tenant_id": str(uuid.uuid4()),
        "channel_id": str(uuid.uuid4()),
        "user_id": PHONE,
        "content": BODY,
        "customer_name": "Ana Pérez",
        "customer_phone": f"+{PHONE}",
        "provider": "meta",
        "provider_message_id": WAMID,
        "mark_read": "1",
        **extra,
    }


async def _dead(
    redis: Any,
    *,
    age_s: float = 3600,
    now: float | None = None,
    stream: str = STREAM,
    error: str = "boom",
    original: dict[str, str] | None = None,
) -> str:
    """Una entrada como la deja ``_dead_letter``, con el mensaje de hace ``age_s``."""
    now = time.time() if now is None else now
    source_id = f"{int((now - age_s) * 1000)}-0"
    raw = await redis.xadd(
        INBOUND_DLQ_STREAM,
        {
            **(original if original is not None else _original()),
            "dlq_source_stream": stream,
            "dlq_source_entry_id": source_id,
            "dlq_error": error,
            "dlq_attempts": "5",
        },
    )
    return raw.decode() if isinstance(raw, bytes) else raw


@pytest.fixture
async def redis() -> Any:
    client = fakeaioredis.FakeRedis()
    await client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    return client


def _text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


async def _stream_fields(redis: Any, stream: str = STREAM) -> list[dict[str, str]]:
    return [
        {_text(k): _text(v) for k, v in fields.items()}
        for _id, fields in await redis.xrange(stream)
    ]


def _events(logs: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [e for e in logs if e["event"] == name]


# ── list ─────────────────────────────────────────────────────────────────────


async def test_list_says_cause_tenant_age_and_attempts(redis: Any) -> None:
    entry_id = await _dead(redis, age_s=3 * DAY + 3600, error="password authentication failed")

    with capture_logs() as logs:
        code = await dlq.run(redis, ["list"])

    assert code == 0
    [entry] = _events(logs, "ops.dlq.entry")
    assert entry["entry_id"] == entry_id
    assert entry["cause"] == "password authentication failed"
    assert uuid.UUID(entry["tenant_id"])
    assert entry["attempts"] == 5
    assert entry["age"] == "3d 1h"
    assert entry["source_stream"] == STREAM


async def test_list_never_shows_the_body_or_a_phone(redis: Any) -> None:
    """Ni el cuerpo, ni el teléfono, ni el nombre, ni el ``wamid`` (lleva el
    teléfono codificado). Tampoco a través de la causa: un error de SQLAlchemy
    arrastra los parámetros del INSERT."""
    await _dead(
        redis,
        error=(
            "(sqlalchemy.dialects.postgresql.asyncpg.Error) <class "
            "'asyncpg.exceptions.StringDataRightTruncationError'>: value too long for type "
            f"character varying(64)\n[SQL: INSERT INTO customers (phone, name) VALUES ($1, $2)]\n"
            f"[parameters: ('+{PHONE}', 'Ana Pérez', '{BODY}')]"
        ),
    )
    await _dead(redis, error=f'Key (phone)=(+{PHONE}) already exists, "{PHONE}" repeated')
    await _dead(redis, error=f"invalid input for query argument $3: '{BODY}' (expected int)")
    await _dead(redis, error=f"Meta refused {WAMID} for +{PHONE} (ana@example.com)")
    await _dead(redis, error=f"invalid input for query argument $3: '{BODY[:12]}")

    with capture_logs() as logs:
        await dlq.run(redis, ["list"])

    dumped = json.dumps(logs, ensure_ascii=False, default=str)
    for secret in (
        PHONE,
        BODY,
        BODY[:12],
        "Ana Pérez",
        WAMID,
        "[parameters",
        "[SQL",
        "ana@example.com",
    ):
        assert secret not in dumped, secret
    [first, second, third, fourth, fifth] = _events(logs, "ops.dlq.entry")
    assert "StringDataRightTruncationError" in first["cause"], "se conserva el tipo de error"
    assert "already exists" in second["cause"]
    assert "invalid input for query argument" in third["cause"]
    assert "Meta refused" in fourth["cause"]
    assert "invalid input for query argument" in fifth["cause"], "una comilla sin cerrar"


async def test_list_counts_what_it_does_not_show(redis: Any) -> None:
    for _ in range(3):
        await _dead(redis)

    with capture_logs() as logs:
        await dlq.run(redis, ["list", "--limit", "2"])

    assert len(_events(logs, "ops.dlq.entry")) == 2
    [summary] = _events(logs, "ops.dlq.summary")
    assert (summary["total"], summary["selected"], summary["shown"]) == (3, 3, 2)


async def test_an_empty_dlq_is_not_an_error(redis: Any) -> None:
    with capture_logs() as logs:
        assert await dlq.run(redis, ["list"]) == 0
    [summary] = _events(logs, "ops.dlq.summary")
    assert summary["total"] == 0


async def test_it_reads_a_client_that_decodes_too() -> None:
    """``get_redis`` de producción decodifica; el de las pruebas, no."""
    client = fakeaioredis.FakeRedis(decode_responses=True)
    await client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    await _dead(client)

    with capture_logs() as logs:
        assert await dlq.run(client, ["reinject", "--all", "--yes", "--reason", "probando"]) == 0

    assert _events(logs, "ops.dlq.reinjected")
    assert await client.xlen(INBOUND_DLQ_STREAM) == 0


# ── filtros ──────────────────────────────────────────────────────────────────


async def test_filters_by_age_and_id(redis: Any) -> None:
    old = await _dead(redis, age_s=60 * DAY)
    recent = await _dead(redis, age_s=3600)

    with capture_logs() as logs:
        await dlq.run(redis, ["list", "--older-than", "30d"])
    assert [e["entry_id"] for e in _events(logs, "ops.dlq.entry")] == [old]

    with capture_logs() as logs:
        await dlq.run(redis, ["list", "--newer-than", "2h"])
    assert [e["entry_id"] for e in _events(logs, "ops.dlq.entry")] == [recent]

    with capture_logs() as logs:
        await dlq.run(redis, ["list", "--id", recent])
    assert [e["entry_id"] for e in _events(logs, "ops.dlq.entry")] == [recent]

    with capture_logs() as logs:
        await dlq.run(redis, ["list", "--id", old, "--newer-than", "2h"])
    assert _events(logs, "ops.dlq.entry") == [], "los filtros se suman"


async def test_age_counts_from_the_message_not_from_when_it_was_parked(redis: Any) -> None:
    """Una entrada aparcada hoy con un mensaje de hace 40 días tiene 40 días."""
    await _dead(redis, age_s=40 * DAY)
    with capture_logs() as logs:
        await dlq.run(redis, ["list"])
    assert _events(logs, "ops.dlq.entry")[0]["age_s"] >= 40 * DAY


async def test_an_entry_without_a_source_id_counts_from_the_dlq_id(redis: Any) -> None:
    await redis.xadd(INBOUND_DLQ_STREAM, {**_original(), "dlq_error": "boom"}, id="1000-0")
    with capture_logs() as logs:
        await dlq.run(redis, ["list"])
    assert _events(logs, "ops.dlq.entry")[0]["age_s"] > 365 * DAY


@pytest.mark.parametrize(
    ("raw", "seconds"), [("30m", 1800), ("12h", 43_200), ("7d", 604_800), ("90s", 90)]
)
async def test_ages_are_written_like_people_write_them(raw: str, seconds: int) -> None:
    assert dlq.parse_age(raw) == seconds


@pytest.mark.parametrize("raw", ["30", "1w", "ayer", "-1d", ""])
async def test_an_age_that_is_not_one_touches_nothing(redis: Any, raw: str) -> None:
    await _dead(redis, age_s=60 * DAY)
    with pytest.raises(SystemExit) as exc:
        await dlq.run(redis, ["discard", f"--older-than={raw}", "--yes", "--reason", "x"])
    assert exc.value.code == 2
    assert await redis.xlen(INBOUND_DLQ_STREAM) == 1


# ── el ensayo y las escrituras ───────────────────────────────────────────────


@pytest.mark.parametrize("command", ["discard", "reinject"])
async def test_without_yes_nothing_is_written(redis: Any, command: str) -> None:
    await _dead(redis)

    with capture_logs() as logs:
        code = await dlq.run(redis, [command, "--all"])

    assert code == 0
    assert await redis.xlen(INBOUND_DLQ_STREAM) == 1
    assert await redis.xlen(STREAM) == 0
    assert len(_events(logs, f"ops.dlq.would_{command}")) == 1
    assert _events(logs, f"ops.dlq.{command}ed") == []
    [summary] = _events(logs, "ops.dlq.summary")
    assert summary["applied"] is False


@pytest.mark.parametrize("command", ["discard", "reinject"])
async def test_writing_asks_for_a_selection(redis: Any, command: str) -> None:
    """Un ``discard --yes`` a secas no se vacía la cola por descuido; y el ensayo
    es el mismo comando sin ``--yes``, así que tampoco corre sin selección."""
    await _dead(redis)
    for argv in ([command], [command, "--yes", "--reason", "x"]):
        with pytest.raises(SystemExit) as exc:
            await dlq.run(redis, argv)
        assert exc.value.code == 2
    assert await redis.xlen(INBOUND_DLQ_STREAM) == 1


@pytest.mark.parametrize("command", ["discard", "reinject"])
async def test_writing_asks_for_a_reason(redis: Any, command: str) -> None:
    await _dead(redis)
    with pytest.raises(SystemExit) as exc:
        await dlq.run(redis, [command, "--all", "--yes"])
    assert exc.value.code == 2
    assert await redis.xlen(INBOUND_DLQ_STREAM) == 1


async def test_discard_leaves_a_record_with_id_tenant_age_and_reason(redis: Any) -> None:
    original = _original()
    entry_id = await _dead(redis, age_s=60 * DAY, original=original)
    keep = await _dead(redis, age_s=3600)

    with capture_logs() as logs:
        code = await dlq.run(
            redis, ["discard", "--older-than", "30d", "--yes", "--reason", "rotación de agosto"]
        )

    assert code == 0
    assert [_text(i) for i, _ in await redis.xrange(INBOUND_DLQ_STREAM)] == [keep]
    [record] = _events(logs, "ops.dlq.discarded")
    assert record["entry_id"] == entry_id
    assert record["tenant_id"] == original["tenant_id"]
    assert record["age_s"] >= 60 * DAY
    assert record["reason"] == "rotación de agosto"
    assert BODY not in json.dumps(logs, ensure_ascii=False, default=str)


async def test_reinject_republishes_the_original_fields_without_dlq_ones(redis: Any) -> None:
    original = _original()
    entry_id = await _dead(redis, original=original)

    with capture_logs() as logs:
        code = await dlq.run(
            redis, ["reinject", "--id", entry_id, "--yes", "--reason", "arreglado"]
        )

    assert code == 0
    assert await redis.xlen(INBOUND_DLQ_STREAM) == 0
    assert await _stream_fields(redis) == [original], "los campos originales, sin dlq_*"
    [record] = _events(logs, "ops.dlq.reinjected")
    assert record["entry_id"] == entry_id
    assert record["tenant_id"] == original["tenant_id"]
    assert record["reason"] == "arreglado"
    assert record["new_entry_id"]
    assert PHONE not in json.dumps(logs, ensure_ascii=False, default=str)


async def test_running_it_twice_publishes_once(redis: Any) -> None:
    await _dead(redis)
    argv = ["reinject", "--all", "--yes", "--reason", "arreglado"]
    assert await dlq.run(redis, argv) == 0
    assert await dlq.run(redis, argv) == 0
    assert await redis.xlen(STREAM) == 1


async def test_a_failed_publish_keeps_the_entry(redis: Any, monkeypatch: Any) -> None:
    """Es la última copia del mensaje: o se mueve entera, o se queda donde estaba."""
    await _dead(redis)

    async def _down(*_a: Any, **_k: Any) -> Any:
        raise ConnectionError("valkey no contesta")

    monkeypatch.setattr(dlq, "xadd_capped", _down)
    with capture_logs() as logs:
        code = await dlq.run(redis, ["reinject", "--all", "--yes", "--reason", "x"])

    assert code == 1
    assert await redis.xlen(INBOUND_DLQ_STREAM) == 1
    assert _events(logs, "ops.dlq.failed")


async def test_an_id_that_is_not_there_is_said_out_loud(redis: Any) -> None:
    await _dead(redis)
    with capture_logs() as logs:
        code = await dlq.run(redis, ["discard", "--id", "1-0", "--yes", "--reason", "x"])
    assert code == 3
    assert await redis.xlen(INBOUND_DLQ_STREAM) == 1
    [missing] = _events(logs, "ops.dlq.id_not_found")
    assert missing["entry_id"] == "1-0"


# ── lo que reinyectar no hace ────────────────────────────────────────────────


async def test_a_stale_entry_is_not_reinjected_without_saying_so(redis: Any) -> None:
    """Contestar hoy a un mensaje de hace dos meses mueve ``last_inbound_at``: la
    plataforma cree abierta la ventana de 24 h de Meta y no lo está."""
    await _dead(redis, age_s=60 * DAY)

    with capture_logs() as logs:
        code = await dlq.run(redis, ["reinject", "--all", "--yes", "--reason", "x"])

    assert code == 3, "no se hizo lo que se pidió, y eso no sale con 0"
    assert await redis.xlen(INBOUND_DLQ_STREAM) == 1
    assert await redis.xlen(STREAM) == 0
    [refused] = _events(logs, "ops.dlq.refused")
    assert refused["refusal"] == "stale"

    with capture_logs() as logs:
        code = await dlq.run(
            redis, ["reinject", "--all", "--allow-stale", "--yes", "--reason", "decidido"]
        )
    assert code == 0
    assert await redis.xlen(STREAM) == 1


async def test_the_rehearsal_tells_what_would_be_refused(redis: Any) -> None:
    await _dead(redis, age_s=60 * DAY)
    with capture_logs() as logs:
        code = await dlq.run(redis, ["reinject", "--all"])
    assert code == 0
    assert [e["refusal"] for e in _events(logs, "ops.dlq.refused")] == ["stale"]
    assert _events(logs, "ops.dlq.would_reinject") == []


@pytest.mark.parametrize(
    "stream",
    [
        "nexus:usage",  # existe y se consume, pero no es de entrantes
        "nexus:inbound:priority",  # es de entrantes, pero nadie la consume aquí
    ],
)
async def test_it_does_not_publish_where_nobody_will_read_it(redis: Any, stream: str) -> None:
    await redis.xgroup_create("nexus:usage", GROUP, id="0", mkstream=True)
    await _dead(redis, stream=stream)

    with capture_logs() as logs:
        code = await dlq.run(redis, ["reinject", "--all", "--yes", "--reason", "x"])

    assert code == 3
    assert await redis.xlen(INBOUND_DLQ_STREAM) == 1
    [refused] = _events(logs, "ops.dlq.refused")
    assert refused["refusal"] == "source_stream_not_consumed"


async def test_it_publishes_where_the_group_reads(redis: Any) -> None:
    await redis.xgroup_create("nexus:inbound", GROUP, id="0", mkstream=True)
    await _dead(redis, stream="nexus:inbound")
    assert await dlq.run(redis, ["reinject", "--all", "--yes", "--reason", "x"]) == 0
    assert await redis.xlen("nexus:inbound") == 1


@pytest.mark.parametrize("missing", ["tenant_id", "channel_id", "user_id", "content"])
async def test_it_refuses_an_entry_the_consumer_would_throw_away(redis: Any, missing: str) -> None:
    """El consumidor acusa y tira una entrada sin estos campos: se perdería la
    última copia sin que nadie lo supiera."""
    original = _original()
    del original[missing]
    await _dead(redis, original=original)

    with capture_logs() as logs:
        code = await dlq.run(redis, ["reinject", "--all", "--yes", "--reason", "x"])

    assert code == 3
    assert await redis.xlen(STREAM) == 0
    assert [e["refusal"] for e in _events(logs, "ops.dlq.refused")] == ["missing_fields"]


@pytest.mark.parametrize("wamid", [None, ""])
async def test_it_refuses_what_it_could_not_tell_from_a_duplicate(
    redis: Any, wamid: str | None
) -> None:
    """Sin ``provider_message_id`` el consumidor no distingue un duplicado de un
    mensaje nuevo: podría contestar dos veces."""
    original = _original()
    if wamid is None:
        del original["provider_message_id"]
    else:
        original["provider_message_id"] = wamid
    await _dead(redis, original=original)

    with capture_logs() as logs:
        code = await dlq.run(redis, ["reinject", "--all", "--yes", "--reason", "x"])

    assert code == 3
    assert await redis.xlen(STREAM) == 0
    assert [e["refusal"] for e in _events(logs, "ops.dlq.refused")] == ["no_provider_message_id"]


async def test_discarding_refuses_nothing(redis: Any) -> None:
    """Un descarte no contesta a nadie: las barreras son de la reinyección."""
    await _dead(redis, age_s=60 * DAY, stream="nexus:usage")
    assert await dlq.run(redis, ["discard", "--all", "--yes", "--reason", "x"]) == 0
    assert await redis.xlen(INBOUND_DLQ_STREAM) == 0


# ── la ida y la vuelta, por el código de verdad ──────────────────────────────


async def _kill(redis: Any, fields: dict[str, str], monkeypatch: Any) -> None:
    """Un mensaje que agota sus intentos en ``handle_entry``."""

    async def boom(event: Any, *, pipeline: Any) -> Any:
        raise RuntimeError("password authentication failed")

    monkeypatch.setattr(consumer_mod, "process_inbound", boom)
    await redis.xadd(
        STREAM,
        {**fields, "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"},
    )
    resp = await redis.xreadgroup(groupname=GROUP, consumername="c1", streams={STREAM: ">"})
    entry_id, raw = resp[0][1][0]
    for _ in range(consumer_mod.MAX_DELIVERY_ATTEMPTS - 1):
        await redis.xclaim(STREAM, GROUP, "c1", 0, [entry_id])
    assert await consumer_mod.handle_entry(
        redis, pipeline=None, stream=STREAM, group=GROUP, entry_id=entry_id, raw_fields=raw
    )


async def test_round_trip_through_the_consumer(redis: Any, monkeypatch: Any) -> None:
    """Lo que el consumidor aparcó, la herramienta lo devuelve, y el consumidor
    lo lee como el mismo mensaje."""
    fields = _original()
    await _kill(redis, fields, monkeypatch)
    assert await redis.xlen(INBOUND_DLQ_STREAM) == 1

    assert await dlq.run(redis, ["reinject", "--all", "--yes", "--reason", "arreglado"]) == 0
    assert await redis.xlen(INBOUND_DLQ_STREAM) == 0

    handled: list[Any] = []

    async def ok(event: Any, *, pipeline: Any) -> dict[str, Any]:
        handled.append(event)
        return {}

    monkeypatch.setattr(consumer_mod, "process_inbound", ok)
    resp = await redis.xreadgroup(groupname=GROUP, consumername="c1", streams={STREAM: ">"})
    entry_id, raw = resp[0][1][0]
    assert await consumer_mod.handle_entry(
        redis, pipeline=None, stream=STREAM, group=GROUP, entry_id=entry_id, raw_fields=raw
    )
    assert handled == [consumer_mod._to_event(fields)]


async def test_an_entry_that_dies_again_counts_as_new(redis: Any, monkeypatch: Any) -> None:
    """Vuelve a la DLQ con id nuevo, y por eso el vigilante vuelve a avisar."""

    async def fake_notify(alert: Any) -> None:
        return None

    monkeypatch.setattr(watcher, "_notify", fake_notify)
    await _kill(redis, _original(), monkeypatch)
    assert [a.kind for a in await watcher.process_tick(redis)] == ["dlq_entries"]
    assert await watcher.process_tick(redis) == []

    assert await dlq.run(redis, ["reinject", "--all", "--yes", "--reason", "x"]) == 0
    assert await watcher.process_tick(redis) == [], "reinyectar no es una entrada nueva"

    resp = await redis.xreadgroup(groupname=GROUP, consumername="c2", streams={STREAM: ">"})
    entry_id, raw = resp[0][1][0]
    for _ in range(consumer_mod.MAX_DELIVERY_ATTEMPTS - 1):
        await redis.xclaim(STREAM, GROUP, "c2", 0, [entry_id])
    assert await consumer_mod.handle_entry(
        redis, pipeline=None, stream=STREAM, group=GROUP, entry_id=entry_id, raw_fields=raw
    )

    assert [a.kind for a in await watcher.process_tick(redis)] == ["dlq_entries"]


async def test_the_three_names_of_the_queue_are_one(redis: Any) -> None:
    assert consumer_mod.DLQ_STREAM == watcher.DLQ_STREAM == dlq.DLQ_STREAM == INBOUND_DLQ_STREAM


# ── como orden de una tarea de ECS ───────────────────────────────────────────


async def test_it_runs_as_a_command_without_loading_the_graph() -> None:
    """``python -m`` es lo que lanza la tarea. Fuera de ``nexus_worker.streams``,
    cuyo ``__init__`` importa el consumidor y con él LangGraph."""
    code = (
        "import sys, runpy\n"
        "sys.argv = ['dlq', '--help']\n"
        "try:\n"
        "    runpy.run_module('nexus_worker.ops.dlq', run_name='__main__')\n"
        "except SystemExit as exc:\n"
        "    assert exc.code == 0, exc.code\n"
        "for heavy in ('langgraph', 'litellm', 'nexus_worker.streams.consumer'):\n"
        "    assert heavy not in sys.modules, heavy\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert "reinject" in done.stdout
