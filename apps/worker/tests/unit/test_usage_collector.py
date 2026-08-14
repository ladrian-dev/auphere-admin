"""Emisión de consumo (WP-17).

Lo que se fija aquí:

- un turno con 1 classify + 2 respond emite **6 eventos** (input y output
  por llamada), con claves de idempotencia distintas por llamada;
- el ``call_seq`` va por llamada, no por evento: dos medidores de la misma
  llamada comparten número, que es lo que hace que reprocesar el stream
  no duplique facturación;
- fuera de un turno la instrumentación es no-op — evals y scripts llaman
  al mismo proveedor LLM y no deben ensuciar la facturación;
- **un fallo publicando NO propaga**: perder la medición es un problema de
  negocio, romper el turno es un problema de producción;
- el volcado ocurre aunque el turno reviente: esos tokens ya se gastaron.
"""

from __future__ import annotations

import json
import uuid

import pytest

from nexus_worker.metering import collector

pytestmark = pytest.mark.asyncio


class _FakeRedis:
    def __init__(self, *, boom: bool = False) -> None:
        self.entries: list[tuple[str, dict]] = []
        self._boom = boom

    async def xadd(self, stream, fields, **kwargs):
        if self._boom:
            raise RuntimeError("redis caído")
        self.entries.append((stream, dict(fields)))
        return b"1-1"


@pytest.fixture
def fake_redis(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr("nexus_api.core.redis_client.get_redis", lambda: redis)
    return redis


def _events_of(redis: _FakeRedis) -> list[dict]:
    out: list[dict] = []
    for _stream, fields in redis.entries:
        out.extend(json.loads(fields["events"]))
    return out


async def test_a_turn_emits_one_event_per_meter_per_call(fake_redis) -> None:
    tenant_id, turn_id = uuid.uuid4(), str(uuid.uuid4())

    async with collector.usage_turn(tenant_id=tenant_id, turn_id=turn_id):
        # classify: sin cache
        collector.record_llm_usage(
            model="anthropic/claude-haiku-4-5",
            provider="anthropic",
            usage={"prompt_tokens": 500, "completion_tokens": 12},
        )
        # respond dos veces (la segunda tras ejecutar una tool)
        for _ in range(2):
            collector.record_llm_usage(
                model="anthropic/claude-sonnet-4-6",
                provider="anthropic",
                usage={"prompt_tokens": 4000, "completion_tokens": 220},
            )

    events = _events_of(fake_redis)
    assert len(events) == 6

    meters = sorted(e["meter"] for e in events)
    assert meters == ["llm.input_tokens"] * 3 + ["llm.output_tokens"] * 3

    # Una sola entrada de stream por turno: el lote entero de golpe.
    assert len(fake_redis.entries) == 1
    stream, fields = fake_redis.entries[0]
    assert stream == collector.USAGE_STREAM
    assert fields["tenant_id"] == str(tenant_id)
    assert fields["turn_id"] == turn_id

    # Idempotencia: {turn_id}:{call_seq}:{meter}. El número es de la
    # LLAMADA, así que input y output de la misma llamada lo comparten.
    keys = {e["idempotency_key"] for e in events}
    assert len(keys) == 6
    assert f"{turn_id}:1:llm.input_tokens" in keys
    assert f"{turn_id}:1:llm.output_tokens" in keys
    assert f"{turn_id}:3:llm.output_tokens" in keys


async def test_cache_meters_only_appear_when_nonzero(fake_redis) -> None:
    async with collector.usage_turn(tenant_id=uuid.uuid4(), turn_id="t1"):
        collector.record_llm_usage(
            model="anthropic/claude-sonnet-4-6",
            provider="anthropic",
            usage={
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "cache_read_input_tokens": 3000,
                "cache_creation_input_tokens": 0,
            },
        )

    meters = {e["meter"] for e in _events_of(fake_redis)}
    assert meters == {"llm.input_tokens", "llm.output_tokens", "llm.cache_read"}


async def test_outside_a_turn_it_is_a_noop(fake_redis) -> None:
    """Evals y scripts usan el mismo proveedor; no deben facturar."""
    collector.record_llm_usage(
        model="anthropic/claude-sonnet-4-6",
        provider="anthropic",
        usage={"prompt_tokens": 999, "completion_tokens": 99},
    )
    assert fake_redis.entries == []


async def test_a_failing_turn_still_publishes_what_it_spent(fake_redis) -> None:
    with pytest.raises(RuntimeError, match="el grafo revienta"):
        async with collector.usage_turn(tenant_id=uuid.uuid4(), turn_id="t2"):
            collector.record_llm_usage(
                model="anthropic/claude-sonnet-4-6",
                provider="anthropic",
                usage={"prompt_tokens": 1200, "completion_tokens": 40},
            )
            raise RuntimeError("el grafo revienta")

    assert len(_events_of(fake_redis)) == 2


async def test_publish_failure_never_propagates(monkeypatch) -> None:
    """La garantía que hace seguro instrumentar el camino crítico."""
    monkeypatch.setattr("nexus_api.core.redis_client.get_redis", lambda: _FakeRedis(boom=True))

    async with collector.usage_turn(tenant_id=uuid.uuid4(), turn_id="t3"):
        collector.record_llm_usage(
            model="m",
            provider="anthropic",
            usage={"prompt_tokens": 10, "completion_tokens": 1},
        )
    # Si llegamos aquí, no propagó.


async def test_channel_message_is_keyed_by_provider_message_id(fake_redis) -> None:
    tenant_id = uuid.uuid4()
    await collector.record_channel_message(
        tenant_id=tenant_id, provider="meta", provider_message_id="wamid.ABC"
    )

    events = _events_of(fake_redis)
    assert len(events) == 1
    assert events[0]["meter"] == "channel.message"
    assert events[0]["quantity"] == 1.0
    assert events[0]["idempotency_key"] == "wamid.ABC:channel"


async def test_channel_message_without_wamid_is_skipped(fake_redis) -> None:
    """Sin clave estable preferimos un hueco a una fila duplicada en una
    factura."""
    await collector.record_channel_message(
        tenant_id=uuid.uuid4(), provider="meta", provider_message_id=None
    )
    assert fake_redis.entries == []


class _RecordingRedis:
    """Registra las lecturas para fijar el ORDEN, que es lo que estuvo mal."""

    def __init__(self) -> None:
        self.reads: list[str] = []
        self.claimed = False

    async def xgroup_create(self, *a, **kw):
        return True

    async def xreadgroup(self, group, consumer, streams, count=None, block=None):
        self.reads.append(next(iter(streams.values())))
        return []

    async def xautoclaim(self, *a, **kw):
        self.claimed = True
        return (b"0-0", [], [])


async def test_drain_reads_pending_then_orphans_then_new() -> None:
    """El orden importa y es la corrección del fallo visto en staging.

    Leer solo ``">"`` deja para siempre en el PEL lo que falló al
    persistir: "no acusar para que se reintente" solo es cierto si algo
    vuelve a leerlo. Y sin ``XAUTOCLAIM``, el trabajo de una réplica
    muerta se pierde — en facturación, eso es dinero.
    """
    from nexus_worker.metering.consumer import drain_once

    redis = _RecordingRedis()
    processed = await drain_once(redis, consumer_name="c1")

    assert processed == 0
    assert redis.reads == ["0", ">"], "primero lo propio pendiente, luego lo nuevo"
    assert redis.claimed, "hay que reclamar lo huérfano de réplicas muertas"


# ── origen del consumo (0079) ────────────────────────────────────────────────


async def test_a_turn_declares_its_source_and_defaults_to_channel(fake_redis) -> None:
    """``source`` viaja en la entrada de stream, no en cada evento: es una
    propiedad del turno, no de la llamada al LLM.

    El defecto es ``channel`` a propósito. Un camino nuevo que olvide
    declararlo cuenta como tráfico real, que es el error que se ve en la
    factura; el revés —consumo de cliente etiquetado como interno— se
    descontaría de los ingresos y no lo notaría nadie.
    """
    async with collector.usage_turn(tenant_id=uuid.uuid4(), turn_id="canal"):
        collector.record_llm_usage(
            model="m", provider="anthropic", usage={"prompt_tokens": 10, "completion_tokens": 1}
        )
    async with collector.usage_turn(
        tenant_id=uuid.uuid4(), turn_id="playground", source=collector.SOURCE_QA
    ):
        collector.record_llm_usage(
            model="m", provider="anthropic", usage={"prompt_tokens": 10, "completion_tokens": 1}
        )

    sources = [fields["source"] for _stream, fields in fake_redis.entries]
    assert sources == ["channel", "qa"]


async def test_an_invented_source_falls_back_to_channel(fake_redis) -> None:
    """Mismo criterio que ``USAGE_METERS``: el conjunto es cerrado. Un
    valor inventado no puede colar consumo como interno — cae al lado
    facturable, que es el que alguien revisa."""
    async with collector.usage_turn(tenant_id=uuid.uuid4(), turn_id="raro", source="gratis-total"):
        collector.record_llm_usage(
            model="m", provider="anthropic", usage={"prompt_tokens": 10, "completion_tokens": 1}
        )

    assert fake_redis.entries[0][1]["source"] == "channel"


async def test_channel_messages_are_channel_source(fake_redis) -> None:
    """Los salientes entregados se publican fuera de turno y también
    tienen que quedar del lado facturable."""
    await collector.record_channel_message(
        tenant_id=uuid.uuid4(), provider="meta", provider_message_id="wamid.X"
    )
    assert fake_redis.entries[0][1]["source"] == "channel"
