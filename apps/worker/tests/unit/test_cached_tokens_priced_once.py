"""INC-70: un token en caché se valora una vez, en su fila de caché.

LiteLLM da ``prompt_tokens`` con todo dentro: lo nuevo, lo leído de caché y, en
Anthropic, lo escrito en caché. Valorar la fila ``llm.input_tokens`` por esa
cantidad cobraba esos tokens a precio de entrada y otra vez en su propia fila.
``cost_usd`` salía unas tres veces más alto, y con él la partida «Construcción y
pruebas», que se agotó dos veces en staging.

Va por ``persist_rows``, el único camino de producción que valora: un test sobre
``price_row`` suelto no ve el fallo, porque una fila no sabe qué lleva su llamada.
"""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from litellm.llms.anthropic.chat.transformation import AnthropicConfig

from nexus_worker.metering import collector, consumer
from nexus_worker.metering.pricing import ModelPrice

SOL = ModelPrice(
    model_id="openai/gpt-5.6-sol",
    input_per_mtok=Decimal("4"),
    output_per_mtok=Decimal("20"),
    cache_read_per_mtok=Decimal("0.40"),
)
SONNET = ModelPrice(
    model_id="anthropic/claude-sonnet-4-6",
    input_per_mtok=Decimal("3"),
    output_per_mtok=Decimal("15"),
    cache_read_per_mtok=Decimal("0.30"),
    cache_write_per_mtok=Decimal("3.75"),
)
CATALOG = {p.model_id: p for p in (SOL, SONNET)}


class _Session:
    execute = AsyncMock()

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    def begin(self) -> _Session:
        return self


@asynccontextmanager
async def _no_scope(*_: object):
    yield


@pytest.fixture(autouse=True)
def _no_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin Postgres ni Redis: aquí importa lo que vale cada fila, no el INSERT."""
    monkeypatch.setattr(consumer, "get_catalog", AsyncMock(return_value=CATALOG))
    monkeypatch.setattr(consumer, "get_unit_prices", AsyncMock(return_value={}))
    monkeypatch.setattr(consumer, "get_sessionmaker", lambda: _Session)
    monkeypatch.setattr(consumer, "tenant_scoped_session", _no_scope)
    monkeypatch.setattr(consumer, "_bump_budget", AsyncMock())
    monkeypatch.setattr(consumer, "_debit_channel_wallet", AsyncMock())
    monkeypatch.setattr(consumer, "_record_build_line", AsyncMock())


def _entry(*calls: tuple[str, dict[str, int]], source: str = "channel") -> dict[str, str]:
    """Una entrada del stream con las llamadas dadas, como las publica el colector."""
    events = []
    for seq, (model, usage) in enumerate(calls, start=1):
        for usage_key, meter in collector.LLM_METERS.items():
            if usage.get(usage_key):
                events.append(
                    {
                        "meter": meter,
                        "quantity": float(usage[usage_key]),
                        "idempotency_key": f"t1:{seq}:{meter}",
                        "occurred_at": "2026-11-02T10:00:00+00:00",
                        "provider": model.split("/", 1)[0],
                        "model": model,
                    }
                )
    return {
        "tenant_id": str(uuid.uuid4()),
        "turn_id": "t1",
        "source": source,
        "events": json.dumps(events),
    }


async def _priced(*calls: tuple[str, dict[str, int]], source: str = "channel") -> list[dict]:
    tenant_id, rows = consumer.rows_from_entry(_entry(*calls, source=source))
    await consumer.persist_rows({tenant_id: rows})
    return rows


def _cost(rows: list[dict[str, Any]], meter: str) -> Decimal:
    return sum((r["cost_usd"] for r in rows if r["meter"] == meter), Decimal(0))


def _total(rows: list[dict[str, Any]]) -> Decimal:
    return sum((r["cost_usd"] for r in rows), Decimal(0))


async def test_the_reproduction_of_inc_70() -> None:
    """1000 tokens con 900 en caché a 4 / 0,40: 0,00076. Salía 0,00436."""
    rows = await _priced(
        (SOL.model_id, {"prompt_tokens": 1000, "cache_read_input_tokens": 900}),
    )
    assert _cost(rows, "llm.input_tokens") == Decimal("0.00040000")
    assert _cost(rows, "llm.cache_read") == Decimal("0.00036000")
    assert _total(rows) == Decimal("0.00076000")


async def test_anthropic_writes_are_not_priced_as_input_too() -> None:
    """Con la escritura pasa lo mismo: está dentro de ``prompt_tokens`` y se paga
    a 1,25x en su fila. Sale de la función real de LiteLLM a propósito: si una
    versión deja de sumarla, restarla aquí valoraría de menos sin avisar."""
    usage = AnthropicConfig().calculate_usage(
        {
            "input_tokens": 100,
            "output_tokens": 0,
            "cache_creation_input_tokens": 300,
            "cache_read_input_tokens": 600,
        },
        reasoning_content=None,
    )
    fields = collector.usage_fields(SimpleNamespace(usage=usage))
    assert fields["prompt_tokens"] == 1000, "LiteLLM ya no suma la caché a prompt_tokens"

    rows = await _priced((SONNET.model_id, fields))

    assert _cost(rows, "llm.input_tokens") == Decimal("0.00030000")
    assert _cost(rows, "llm.cache_read") == Decimal("0.00018000")
    assert _cost(rows, "llm.cache_write") == Decimal("0.00112500")
    assert _total(rows) == Decimal("0.00160500")


async def test_calls_of_one_turn_are_priced_apart() -> None:
    """La caché de una llamada no descuenta la entrada de otra."""
    rows = await _priced(
        (SOL.model_id, {"prompt_tokens": 2000}),
        (SOL.model_id, {"prompt_tokens": 1000, "cache_read_input_tokens": 1000}),
    )
    assert _cost(rows, "llm.input_tokens") == Decimal("0.00800000")
    assert _cost(rows, "llm.cache_read") == Decimal("0.00040000")


async def test_a_prompt_served_entirely_from_cache_costs_zero_as_input_not_none() -> None:
    """Cero sí es la verdad aquí: la entrada se conoce y no quedó nada por cobrar.
    ``None`` diría «medido, sin precio» y la contaría como pendiente de valorar."""
    rows = await _priced(
        (SOL.model_id, {"prompt_tokens": 1000, "cache_read_input_tokens": 1000}),
    )
    assert _cost(rows, "llm.input_tokens") == Decimal("0")
    assert all(r["cost_usd"] is not None for r in rows)


async def test_what_was_measured_stays_as_measured() -> None:
    """Valorar no cambia ``quantity``: es el dato irrecuperable, y de él sale el
    cobro al cliente."""
    weights = {
        SOL.model_id: {
            "input": Decimal("0.88"),
            "cache_read": Decimal("0.088"),
            "output": Decimal("4.4"),
        }
    }
    tenant_id, rows = consumer.rows_from_entry(
        _entry((SOL.model_id, {"prompt_tokens": 1000, "cache_read_input_tokens": 900}))
    )
    before = consumer._turn_quota(rows, weights)
    await consumer.persist_rows({tenant_id: rows})

    assert {r["meter"]: r["quantity"] for r in rows} == {
        "llm.input_tokens": 1000.0,
        "llm.cache_read": 900.0,
    }
    # 100 x 0,88 + 900 x 0,088 = 167,2: el cobro no dependía del fallo ni cambia.
    assert consumer._turn_quota(rows, weights) == before == {"t1": 167}


async def test_what_cannot_be_priced_stays_none() -> None:
    rows = await _priced(("anthropic/inventado", {"prompt_tokens": 1000}))
    assert [r["cost_usd"] for r in rows] == [None]


async def test_rows_without_a_model_keep_their_unit_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        consumer, "get_unit_prices", AsyncMock(return_value={"media.image": Decimal("0.01")})
    )
    tenant_id = uuid.uuid4()
    rows = [
        {
            "tenant_id": tenant_id,
            "occurred_at": None,
            "meter": "media.image",
            "quantity": 2.0,
            "billable_qty": 2.0,
            "cost_usd": None,
            "model": None,
            "idempotency_key": "wamid:media.image",
            "source": "channel",
        }
    ]
    await consumer.persist_rows({tenant_id: rows})
    assert rows[0]["cost_usd"] == Decimal("0.02000000")


async def test_the_build_line_adds_the_right_amount(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lo que agotaba la partida: coste por 2,2 en cien milésimas. La misma llamada
    sumaba 959 y suma 167."""
    monkeypatch.undo()
    monkeypatch.setattr(consumer, "get_catalog", AsyncMock(return_value=CATALOG))
    monkeypatch.setattr(consumer, "get_unit_prices", AsyncMock(return_value={}))
    monkeypatch.setattr(consumer, "get_sessionmaker", lambda: _Session)
    monkeypatch.setattr(consumer, "tenant_scoped_session", _no_scope)
    monkeypatch.setattr(consumer, "_partner_for", AsyncMock(return_value=uuid.uuid4()))
    monkeypatch.setattr(
        "nexus_api.core.partner_context.apply_partner_to_session", AsyncMock(return_value=None)
    )
    record = AsyncMock(return_value=[])
    monkeypatch.setattr("nexus_api.services.wallet.build_budget.record", record)

    await _priced(
        (SOL.model_id, {"prompt_tokens": 1000, "cache_read_input_tokens": 900}),
        source="tests",
    )

    assert record.await_args.args[-1] == 167
