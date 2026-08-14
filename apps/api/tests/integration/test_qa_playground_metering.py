"""El consumo del QA Playground se mide, y NO se le cobra al cliente (0079).

Este archivo existe por un agujero comprobado el 2026-08-13: tres turnos
reales por el Playground gastaron tokens de Anthropic y dejaron **cero**
filas en ``usage_records``. El contexto ``usage_turn`` se abría en un solo
sitio —``dispatcher.py``, el camino de canal— y el Playground ejecuta el
pipeline en proceso dentro de la API. ``record_usage`` es no-op fuera de
turno a propósito, así que no fallaba: se callaba.

Se cubren los **dos** caminos del Playground, no uno. ``/send`` es el
síncrono heredado; ``/runs`` + SSE es el que usa el frontend actual, y su
driver corre en una ``asyncio.Task`` propia — asyncio da a cada Task un
contexto nuevo, así que un ``usage_turn`` abierto en el handler no
llegaría a los nodos del grafo y el consumo volvería a desaparecer con
todos los tests en verde. Medir sólo ``/send`` habría dejado callado
justo el camino real.

Y el que de verdad importa: **el panel de margen no cuenta el QA como
coste del cliente**. Medirlo sin distinguirlo no habría arreglado nada,
habría cambiado un agujero por una mentira — y una mentira sesgada, porque
el cliente que más pruebas recibe es el mejor atendido.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from nexus_worker.metering import collector
from nexus_worker.metering.consumer import drain_once

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def qa_headers(operator_id: str, admin_headers: dict[str, str]) -> dict[str, str]:
    return {**admin_headers, "X-Operator-Id": operator_id}


def _op_id() -> str:
    import secrets

    return secrets.token_urlsafe(16)


@pytest_asyncio.fixture
async def tenant_id(db_session: Any) -> uuid.UUID:
    from nexus_api.db.models import Tenant, TenantPlan

    tid = uuid.uuid4()
    async with db_session.begin():
        db_session.add(
            Tenant(id=tid, name="QA-Metering", slug=f"qam-{tid.hex[:6]}", plan=TenantPlan.PRO)
        )
    return tid


@pytest_asyncio.fixture
async def clean_usage_stream(fake_redis) -> AsyncIterator[Any]:
    """El MISMO Redis que usa el colector — ``fake_redis`` es autouse y
    parchea ``redis_client.get_redis``."""
    await fake_redis.delete(collector.USAGE_STREAM)
    yield fake_redis
    await fake_redis.delete(collector.USAGE_STREAM)


async def _create_thread(client, admin_headers, op: str, tenant_id: uuid.UUID) -> str:
    r = await client.post(
        "/qa/threads",
        json={"tenant_id": str(tenant_id), "title": "metering"},
        headers=qa_headers(op, admin_headers),
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _spend_tokens() -> None:
    """Lo que hace el runtime real dentro del grafo: una llamada al LLM
    pasa por ``LiteLLMProvider._raw_complete`` y anota su consumo."""
    collector.record_llm_usage(
        model="anthropic/claude-sonnet-4-6",
        provider="anthropic",
        usage={"prompt_tokens": 1200, "completion_tokens": 340},
    )


async def _usage_rows(tenant_id: uuid.UUID) -> list[Any]:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        return (
            await session.execute(
                sa.text(
                    "SELECT meter, quantity, source FROM usage_records "
                    "WHERE tenant_id = :t ORDER BY meter"
                ),
                {"t": str(tenant_id)},
            )
        ).all()


# ── camino 1: POST /send (síncrono) ──────────────────────────────────────────


async def test_send_turn_lands_in_usage_records_as_qa(
    client, admin_headers, tenant_id, clean_usage_stream, monkeypatch
) -> None:
    class _Fake:
        async def ainvoke(self, state, config):
            _spend_tokens()
            return {
                "tenant_id": state["tenant_id"],
                "response": "listo",
                "ucm": None,
                "intent": "info",
                "tool_calls": [],
            }

    monkeypatch.setattr("nexus_api.api.qa._get_qa_pipeline", lambda *, live: _Fake())

    op = _op_id()
    thread_id = await _create_thread(client, admin_headers, op, tenant_id)
    r = await client.post(
        f"/qa/threads/{thread_id}/send",
        json={"message": "hola"},
        headers=qa_headers(op, admin_headers),
    )
    assert r.status_code == 200, r.text

    assert await drain_once(clean_usage_stream, consumer_name="test-qa-send") == 1

    rows = await _usage_rows(tenant_id)
    # Antes de la 0079 esta lista estaba VACÍA: el turno gastaba tokens y
    # no dejaba rastro en ninguna tabla.
    assert [r[0] for r in rows] == ["llm.input_tokens", "llm.output_tokens"]
    assert {float(r[1]) for r in rows} == {1200.0, 340.0}
    assert {r[2] for r in rows} == {"qa"}


# ── camino 2: POST /runs + SSE (el que usa el frontend) ──────────────────────


async def test_streaming_turn_lands_in_usage_records_as_qa(
    client, admin_headers, tenant_id, clean_usage_stream, monkeypatch
) -> None:
    """El driver corre en su propia Task. Si ``usage_turn`` se abriese en
    el handler en vez de dentro del driver, el ContextVar no llegaría aquí
    y este test sería el único que lo notaría."""

    class _FakeStream:
        async def astream_events(self, state, config, version="v2"):
            _spend_tokens()
            # Un evento cualquiera: lo que se prueba es la medición, no el
            # formato de cable (eso ya tiene sus tests).
            if False:  # pragma: no cover - fija el tipo de generador
                yield {}

    monkeypatch.setattr("nexus_api.api.qa._get_qa_pipeline", lambda *, live: _FakeStream())

    op = _op_id()
    thread_id = await _create_thread(client, admin_headers, op, tenant_id)
    r = await client.post(
        f"/qa/threads/{thread_id}/runs",
        json={"message": "hola"},
        headers=qa_headers(op, admin_headers),
    )
    assert r.status_code == 202, r.text
    run_id = r.json()["run_id"]

    async with client.stream(
        "GET",
        f"/qa/threads/{thread_id}/stream",
        params={"run_id": str(run_id)},
        headers=qa_headers(op, admin_headers),
    ) as response:
        async for chunk in response.aiter_text():
            if "event: run.completed" in chunk or "event: run.failed" in chunk:
                break
    # El publish del consumo ocurre al salir del ``usage_turn``, dentro del
    # bloque ``finally`` del driver; el stream puede cerrarse un pelo antes.
    await asyncio.sleep(0.1)

    assert await drain_once(clean_usage_stream, consumer_name="test-qa-stream") == 1

    rows = await _usage_rows(tenant_id)
    assert {r[2] for r in rows} == {"qa"}
    assert {r[0] for r in rows} == {"llm.input_tokens", "llm.output_tokens"}


# ── el que importa: el panel de margen no le cobra esto al cliente ───────────


async def test_qa_spend_is_not_billed_to_the_client(
    client, admin_headers, tenant_id, clean_usage_stream, monkeypatch
) -> None:
    """Mismo tenant, dos orígenes. ``/admin/tenants/{id}/cost`` es lo que
    lee el panel de margen: tiene que devolver SOLO el consumo de canal
    como coste del cliente, y el de QA aparte — visible, pero no en la
    factura.
    """
    from nexus_worker.metering.collector import SOURCE_CHANNEL, SOURCE_QA, usage_turn

    # 1 · consumo de canal: un cliente real hablando por WhatsApp.
    async with usage_turn(tenant_id=tenant_id, turn_id=str(uuid.uuid4()), source=SOURCE_CHANNEL):
        collector.record_llm_usage(
            model="anthropic/claude-sonnet-4-6",
            provider="anthropic",
            usage={"prompt_tokens": 1_000_000, "completion_tokens": 0},
        )
    # 2 · consumo de QA: el operador probando ese mismo agente.
    async with usage_turn(tenant_id=tenant_id, turn_id=str(uuid.uuid4()), source=SOURCE_QA):
        collector.record_llm_usage(
            model="anthropic/claude-sonnet-4-6",
            provider="anthropic",
            usage={"prompt_tokens": 9_000_000, "completion_tokens": 0},
        )

    assert await drain_once(clean_usage_stream, consumer_name="test-qa-margin") == 2

    body = (await client.get(f"/admin/tenants/{tenant_id}/cost", headers=admin_headers)).json()

    # El cliente consumió 1M de tokens de entrada; el operador 9M. Si el QA
    # entrase en el coste, la cifra del cliente sería DIEZ veces la real.
    channel_rows = sum(b["records"] for b in body["buckets"])
    assert channel_rows == 1
    assert body["total_records"] == 1
    assert body["internal_qa_records"] == 1

    # Y con precio puesto (la 0072 tarifa sonnet), el coste del cliente es
    # el de 1M de tokens, no el de 10M. Se exige ``complete``: sin precio,
    # los dos totales serían 0 y el test pasaría sin comparar nada.
    assert body["complete"] is True
    assert body["total_cost_usd"] > 0
    assert body["internal_qa_cost_usd"] == pytest.approx(body["total_cost_usd"] * 9, rel=1e-6)


async def test_channel_turns_keep_counting_as_channel(clean_usage_stream, db_session) -> None:
    """Control en la otra dirección. El fallo caro de esta migración no es
    que el QA se cuele en la factura — es que un turno REAL se etiquete
    como interno y deje de facturarse sin que nadie lo note."""
    from nexus_api.db.models import Tenant, TenantPlan

    tid = uuid.uuid4()
    async with db_session.begin():
        db_session.add(Tenant(id=tid, name="Canal", slug=f"can-{tid.hex[:6]}", plan=TenantPlan.PRO))

    # Sin declarar ``source``: es exactamente lo que hace ``dispatcher.py``.
    async with collector.usage_turn(tenant_id=tid, turn_id=str(uuid.uuid4())):
        _spend_tokens()

    assert await drain_once(clean_usage_stream, consumer_name="test-channel-default") == 1
    rows = await _usage_rows(tid)
    assert rows
    assert {r[2] for r in rows} == {"channel"}
