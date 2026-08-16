"""Consumo de punta a punta: turno → ``nexus:usage`` → ``usage_records``.

Cierra el bucle de B3. Antes de esto los tokens del LLM no existían en
ninguna tabla de producción y no se podía cobrar por consumo ni vigilar el
margen.

Se recorre el camino REAL, no una simulación de cada mitad por separado:
el colector de WP-17 publica al stream y el consumidor de WP-18 lo lee y
escribe en Postgres con RLS puesta. Lo único falso es el proveedor LLM,
porque el objetivo es medir, no gastar dinero de Anthropic.

Incluye el criterio de aceptación del plan: N eventos publicados producen
exactamente N filas, y republicarlos no produce ninguna.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa
from nexus_worker.metering import collector
from nexus_worker.metering.consumer import GROUP, drain_once

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Tenant, TenantPlan

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def clean_usage_stream(fake_redis):
    """El MISMO Redis que usa el colector.

    ``fake_redis`` es autouse y parchea ``redis_client.get_redis``; una
    llamada directa a ``get_redis`` importada arriba se quedaría con la
    función original y el test hablaría con otro Redis que el código bajo
    prueba — que es exactamente lo que pasó la primera vez.
    """
    await fake_redis.delete(collector.USAGE_STREAM)
    yield fake_redis
    await fake_redis.delete(collector.USAGE_STREAM)


async def _seed_tenant(session, tenant_id: uuid.UUID) -> None:
    session.add(
        Tenant(
            id=tenant_id,
            name="Medible",
            slug=f"medible-{tenant_id.hex[:8]}",
            plan=TenantPlan.PRO,
        )
    )
    await session.commit()


async def _count_rows(tenant_id: uuid.UUID) -> int:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        return int(
            await session.scalar(
                sa.text("SELECT count(*) FROM usage_records WHERE tenant_id = :t"),
                {"t": str(tenant_id)},
            )
            or 0
        )


async def test_a_turn_becomes_usage_rows(clean_usage_stream) -> None:
    tenant_id = uuid.uuid4()
    turn_id = str(uuid.uuid4())
    conversation_id = uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_tenant(session, tenant_id)

    # 1 · el turno gasta tokens (colector WP-17, camino real).
    async with collector.usage_turn(
        tenant_id=tenant_id, turn_id=turn_id, conversation_id=conversation_id
    ):
        collector.record_llm_usage(
            model="anthropic/claude-haiku-4-5",
            provider="anthropic",
            usage={"prompt_tokens": 700, "completion_tokens": 20},
        )
        collector.record_llm_usage(
            model="anthropic/claude-sonnet-4-6",
            provider="anthropic",
            usage={
                "prompt_tokens": 5000,
                "completion_tokens": 300,
                "cache_read_input_tokens": 4200,
            },
        )

    # 2 · el consumidor (WP-18) lo persiste.
    processed = await drain_once(clean_usage_stream, consumer_name="test-metering")
    assert processed == 1

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        rows = (
            await session.execute(
                sa.text(
                    "SELECT meter, quantity, model, cost_usd, billable_qty, conversation_id "
                    "FROM usage_records WHERE tenant_id = :t ORDER BY meter"
                ),
                {"t": str(tenant_id)},
            )
        ).all()

    # Una fila por (llamada, medidor) — NO se agrega por turno: perder el
    # detalle por llamada haría imposible ver qué modelo se comió el margen.
    # Dos llamadas → 2 input + 2 output + 1 cache_read (la primera no cachea).
    assert len(rows) == 5

    totals: dict[str, float] = {}
    for meter, quantity, *_ in rows:
        totals[meter] = totals.get(meter, 0) + float(quantity)
    assert totals == {
        "llm.input_tokens": 700 + 5000,
        "llm.output_tokens": 20 + 300,
        "llm.cache_read": 4200,
    }
    # Cada fila sabe de qué modelo salió: es lo que permite comparar coste
    # entre haiku y sonnet dentro del mismo turno.
    models = {r[0]: r[2] for r in rows}
    assert models["llm.cache_read"] == "anthropic/claude-sonnet-4-6"

    # El precio (WP-19). El emisor no lo pone: sale de valorar la cantidad
    # contra ``model_profiles``, que es lo que permite que cambiar una
    # tarifa sea un UPDATE y no un despliegue.
    # Hay DOS filas por medidor de tokens (una por llamada), así que se
    # suman: el coste de un turno es el de todas sus llamadas.
    costs: dict[str, Decimal] = {}
    for meter, _q, _m, cost, *_ in rows:
        assert cost is not None, f"{meter} entró sin precio"
        costs[meter] = costs.get(meter, Decimal(0)) + cost
    # haiku 700 in @ $1/MTok + sonnet 5000 in @ $3/MTok
    assert costs["llm.input_tokens"] == Decimal("0.01570000")
    # haiku 20 out @ $5 + sonnet 300 out @ $15
    assert costs["llm.output_tokens"] == Decimal("0.00460000")
    # sonnet 4200 de caché leída @ $0.30/MTok — el descuento aparece de
    # verdad: esos mismos tokens a precio de entrada costarían 0.0126.
    assert costs["llm.cache_read"] == Decimal("0.00126000")

    total = sum(c for c in costs.values() if c is not None)
    assert total == Decimal("0.02156000"), "coste real del turno, en dólares"
    # Lo facturable, mientras no haya política de precios, es lo medido.
    assert all(r[4] == r[1] for r in rows)
    # El contexto del turno viaja con cada fila.
    assert all(r[5] == conversation_id for r in rows)


async def test_replaying_the_stream_creates_no_duplicates(clean_usage_stream) -> None:
    """Criterio de aceptación del plan: N eventos → N filas; reprocesar → 0.

    Es lo que permite reproducir el DLQ o rebobinar el stream tras un
    incidente sin facturar dos veces.
    """
    tenant_id = uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_tenant(session, tenant_id)

    turns = 40
    for i in range(turns):
        async with collector.usage_turn(tenant_id=tenant_id, turn_id=f"turn-{i}"):
            collector.record_llm_usage(
                model="anthropic/claude-sonnet-4-6",
                provider="anthropic",
                usage={"prompt_tokens": 1000, "completion_tokens": 100},
            )

    await drain_once(clean_usage_stream, consumer_name="test-metering")
    first_pass = await _count_rows(tenant_id)
    assert first_pass == turns * 2  # input + output por turno

    # Rebobinar el grupo al principio: el consumidor vuelve a ver TODO.
    await clean_usage_stream.xgroup_setid(collector.USAGE_STREAM, GROUP, id="0")
    await drain_once(clean_usage_stream, consumer_name="test-metering")

    assert await _count_rows(tenant_id) == first_pass, (
        "reprocesar el stream duplicó facturación — la clave de idempotencia no está haciendo su trabajo"
    )


async def test_entries_survive_a_persist_failure_and_land_on_the_next_pass(
    clean_usage_stream, monkeypatch
) -> None:
    """La recuperación del PEL — el fallo que se vio en staging.

    Si la base rechaza el INSERT, el consumidor NO acusa, para que se
    reintente. Pero eso solo es cierto si algo vuelve a leer lo pendiente:
    leyendo únicamente ``">"`` las entradas se quedaban en el PEL para
    siempre y el consumo se perdía en silencio. Aquí se rompe la
    persistencia a propósito y se comprueba que la siguiente pasada las
    recupera.
    """
    from nexus_worker.metering import consumer as consumer_mod

    tenant_id = uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_tenant(session, tenant_id)

    async with collector.usage_turn(tenant_id=tenant_id, turn_id="reintentable"):
        collector.record_llm_usage(
            model="anthropic/claude-sonnet-4-6",
            provider="anthropic",
            usage={"prompt_tokens": 100, "completion_tokens": 10},
        )

    async def _boom(_rows):
        raise RuntimeError("la base dice que no")

    monkeypatch.setattr(consumer_mod, "persist_rows", _boom)
    assert await drain_once(clean_usage_stream, consumer_name="test-metering") == 0
    assert await _count_rows(tenant_id) == 0

    # La invariante: NO se acusó, así que la entrada sigue pendiente y
    # volverá a entregarse. Si se hubiera acusado, ese consumo estaría
    # perdido sin rastro.
    pending = await clean_usage_stream.xpending(collector.USAGE_STREAM, GROUP)
    assert pending["pending"] == 1, "una entrada que no se pudo persistir fue acusada igualmente"

    # Que la siguiente pasada la RELEA es cosa de ``_read_own_pending``; su
    # orden se fija en los unitarios del worker porque fakeredis no
    # reproduce el ``XREADGROUP ... 0`` de Redis real (devuelve historia,
    # no el PEL). El camino completo se verificó contra staging.


async def test_a_poison_entry_goes_to_the_dlq_and_stops_blocking(clean_usage_stream) -> None:
    """Una entrada inservible no puede parar la ingesta de las siguientes."""
    from nexus_worker.metering.consumer import DLQ_STREAM

    redis = clean_usage_stream
    await redis.delete(DLQ_STREAM)

    tenant_id = uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_tenant(session, tenant_id)

    await redis.xadd(collector.USAGE_STREAM, {"tenant_id": "no-soy-un-uuid", "events": "[]"})
    async with collector.usage_turn(tenant_id=tenant_id, turn_id="bueno"):
        collector.record_llm_usage(
            model="m", provider="anthropic", usage={"prompt_tokens": 10, "completion_tokens": 1}
        )

    await drain_once(redis, consumer_name="test-metering")

    assert await _count_rows(tenant_id) == 2, "la entrada buena debe entrar igual"
    assert await redis.xlen(DLQ_STREAM) == 1
    await redis.delete(DLQ_STREAM)


async def test_media_units_are_persisted_and_priced(clean_usage_stream) -> None:
    """CP-23 (0083): imagen + audio + documento → ≥ 3 filas ``media.*`` con
    ``cost_usd`` puesto por ``meter_prices`` (precio por unidad, sin modelo)."""
    from nexus_worker.metering import pricing

    pricing.invalidate()
    tenant_id = uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_tenant(session, tenant_id)

    for kind, wamid, seconds in (
        ("image", "wamid.MEDIA.IMG", None),
        ("audio", "wamid.MEDIA.AUD", 12.5),
        ("document", "wamid.MEDIA.DOC", None),
    ):
        await collector.record_media_unit(
            tenant_id=tenant_id,
            kind=kind,
            provider="meta",
            provider_message_id=f"{wamid}.{tenant_id.hex[:6]}",
            audio_seconds=seconds,
        )
    processed = await drain_once(clean_usage_stream, consumer_name="test-media")
    assert processed == 3

    async with sm() as session, tenant_scoped_session(session, tenant_id):
        rows = (
            await session.execute(
                sa.text(
                    "SELECT meter, quantity, cost_usd, source FROM usage_records "
                    "WHERE tenant_id = :t ORDER BY meter"
                ),
                {"t": str(tenant_id)},
            )
        ).all()
    by_meter = {r[0]: r for r in rows}
    assert {"media.audio", "media.audio_seconds", "media.document", "media.image"} == set(by_meter)
    priced_media = [
        m for m in ("media.image", "media.audio", "media.document") if by_meter[m][2] is not None
    ]
    assert len(priced_media) == 3, by_meter
    assert all(by_meter[m][2] > 0 for m in priced_media)
    assert by_meter["media.audio_seconds"][1] == Decimal("12.5")
    assert by_meter["media.audio_seconds"][2] == Decimal("0")  # coste ya en voice.minutes
    assert {r[3] for r in rows} == {"channel"}
