"""Spec 065, T097 (requisito 5.9): ``cost_usd`` con el recargo del tramo, llamada a llamada.

``cost_usd`` es lo que creemos que nos factura el proveedor por cada fila de
``usage_records``; de ahí salen el margen y los presupuestos en dólares. Hasta la enmienda
del 2026-11-20 el cobro al partner ya aplicaba el tramo de Haiku 5.5 (x5 por encima de
100.000 tokens de prompt, la petición entera), pero ``cost_usd`` no: una llamada larga
costaba en nuestros números cinco veces menos que en la factura de Anthropic.

El tramo se decide como en el cobro (``LaneWeights.for_prompt``): por llamada, sobre el
prompt bruto (con las dos cachés dentro), estrictamente por encima del umbral.

Importes calculados a mano desde las tarifas por millón de Haiku 5.5 (0,10 entrada,
0,01 lectura, 0,125 escritura, 0,50 salida) y de Sonnet 4.6 (3,00 y 15,00).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from nexus_worker.metering.consumer import _apply_costs
from nexus_worker.metering.pricing import ModelPrice

HAIKU = "anthropic/claude-haiku-5-5"
SONNET = "anthropic/claude-sonnet-4-6"

CATALOG: dict[str, ModelPrice] = {
    HAIKU: ModelPrice(
        model_id=HAIKU,
        input_per_mtok=Decimal("0.10"),
        cache_read_per_mtok=Decimal("0.01"),
        cache_write_per_mtok=Decimal("0.125"),
        output_per_mtok=Decimal("0.50"),
        tier_above_tokens=100_000,
        tier_multiplier=Decimal("5"),
    ),
    # Sin tramo.
    SONNET: ModelPrice(
        model_id=SONNET,
        input_per_mtok=Decimal("3.00"),
        cache_read_per_mtok=Decimal("0.30"),
        cache_write_per_mtok=Decimal("3.75"),
        output_per_mtok=Decimal("15.00"),
    ),
}


def _call(
    model: str,
    *,
    prompt: int,
    read: int = 0,
    write: int = 0,
    output: int = 0,
    seq: int = 1,
) -> list[dict[str, Any]]:
    """Las filas nativas de UNA llamada, como las deja ``rows_from_entry``."""
    return [
        {
            "model": model,
            "meter": meter,
            "quantity": qty,
            "billable_qty": qty,
            "idempotency_key": f"t1:{seq}:{meter}",
        }
        for meter, qty in (
            ("llm.input_tokens", prompt),
            ("llm.cache_read", read),
            ("llm.cache_write", write),
            ("llm.output_tokens", output),
        )
        if qty
    ]


def _costs(rows: list[dict[str, Any]]) -> dict[str, Decimal]:
    _apply_costs(rows, CATALOG, {})
    return {r["idempotency_key"]: r["cost_usd"] for r in rows}


def test_haiku_above_100k_costs_five_times_in_every_lane() -> None:
    """150.000 de prompt (30.000 leídos, 20.000 escritos) y 1.000 de salida.
    Entrada valorada = 150.000 - 30.000 - 20.000 = 100.000.
    Sin tramo: 0,01 / 0,0003 / 0,0025 / 0,0005. Con x5: 0,05 / 0,0015 / 0,0125 / 0,0025."""
    rows = _call(HAIKU, prompt=150_000, read=30_000, write=20_000, output=1_000)
    assert _costs(rows) == {
        "t1:1:llm.input_tokens": Decimal("0.05000000"),
        "t1:1:llm.cache_read": Decimal("0.00150000"),
        "t1:1:llm.cache_write": Decimal("0.01250000"),
        "t1:1:llm.output_tokens": Decimal("0.00250000"),
    }


def test_the_tier_starts_strictly_above_the_threshold() -> None:
    """100.000 justos no pasan: 100.000 x 0,10 / 1M y 1.000 x 0,50 / 1M."""
    rows = _call(HAIKU, prompt=100_000, output=1_000)
    assert _costs(rows) == {
        "t1:1:llm.input_tokens": Decimal("0.01000000"),
        "t1:1:llm.output_tokens": Decimal("0.00050000"),
    }


def test_the_tier_is_per_call_not_per_turn() -> None:
    """Dos llamadas de 60.000 en un turno suman 120.000, pero ninguna pasa el umbral:
    60.000 x 0,10 / 1M cada una."""
    rows = _call(HAIKU, prompt=60_000, seq=1) + _call(HAIKU, prompt=60_000, seq=2)
    assert _costs(rows) == {
        "t1:1:llm.input_tokens": Decimal("0.00600000"),
        "t1:2:llm.input_tokens": Decimal("0.00600000"),
    }


def test_a_model_without_a_tier_costs_as_before() -> None:
    """Sonnet 4.6 no tiene tramo: 150.000 x 3,00 / 1M y 1.000 x 15,00 / 1M."""
    rows = _call(SONNET, prompt=150_000, output=1_000)
    assert _costs(rows) == {
        "t1:1:llm.input_tokens": Decimal("0.45000000"),
        "t1:1:llm.output_tokens": Decimal("0.01500000"),
    }
