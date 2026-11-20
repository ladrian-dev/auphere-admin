"""Spec 065, T044 (requisitos 5.5 a 5.8): el cuarto carril, la escritura en caché.

Hasta la 065 la cuota tenía tres carriles y lo escrito en caché se cobraba dentro de la
entrada, a 1x: Anthropic lo factura a 1,25x y GPT-5.6 también (research.md §D14), así que el
margen de ese carril quedaba por debajo del multiplicador. Ahora:

- un modelo con peso de escritura mayor que cero cobra la entrada como «prompt - lectura -
  escritura» y la escritura con su peso; Anthropic y GPT-5.6 igual (el cable lo fija en
  ``test_cache_write_on_the_wire``: ``prompt_tokens`` ya trae las dos cachés);
- un modelo sin tarifa de escritura (peso 0) cobra lo mismo que antes;
- un modelo con tarifa de escritura y sin peso no se cobra a cero: ``unweighted_model``;
- Haiku 5.5 por encima de 100.000 tokens de prompt **de la llamada** cobra con los pesos del
  tramo (``model_prices.surcharge``).

Los importes están calculados a mano en cada test, desde las tarifas por millón y el
multiplicador 2,2 sobre 10 USD el millón de unidades: peso = tarifa x 2,2 / 10.

Se prueban los tres sitios que debitan o desglosan con la misma llamada: ``_turn_quota`` (el
débito del canal y de las pruebas), ``_apply_lane_weights`` (el desglose de
``usage_records``) y la cuenta del copiloto (``console/companion.py``).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
import structlog
from nexus_api.api.console.companion import _turn_quota_units
from nexus_api.metering.pricing_policy import LaneWeights, UnweightedModel, weights_for

from nexus_worker.metering.consumer import _apply_lane_weights, _turn_quota
from nexus_worker.metering.pricing import ModelPrice, lane_weights_from

SONNET = "anthropic/claude-sonnet-4-6"
SOL = "openai/gpt-5.6-sol"
GPT4O = "openai/gpt-4o"
HAIKU = "anthropic/claude-haiku-5-5"
NO_WRITE_WEIGHT = "anthropic/claude-sin-peso-de-escritura"
BORN_IN_PANEL = "openai/dado-de-alta-en-el-panel"

CATALOG: dict[str, ModelPrice] = {
    # 3,00 / 0,30 / 3,75 / 15,00 USD por millón → 0,66 / 0,066 / 0,825 / 3,3.
    SONNET: ModelPrice(
        model_id=SONNET,
        input_per_mtok=Decimal("3.00"),
        cache_read_per_mtok=Decimal("0.30"),
        cache_write_per_mtok=Decimal("3.75"),
        output_per_mtok=Decimal("15.00"),
        quota_weight_input=Decimal("0.66"),
        quota_weight_cache_read=Decimal("0.066"),
        quota_weight_cache_write=Decimal("0.825"),
        quota_weight_output=Decimal("3.3"),
    ),
    # 4,00 / 0,40 / 5,00 (0239) / 20,00 → 0,88 / 0,088 / 1,10 / 4,4.
    SOL: ModelPrice(
        model_id=SOL,
        input_per_mtok=Decimal("4.00"),
        cache_read_per_mtok=Decimal("0.40"),
        cache_write_per_mtok=Decimal("5.00"),
        output_per_mtok=Decimal("20.00"),
        quota_weight_input=Decimal("0.88"),
        quota_weight_cache_read=Decimal("0.088"),
        quota_weight_cache_write=Decimal("1.10"),
        quota_weight_output=Decimal("4.4"),
    ),
    # Sin tarifa de escritura: peso 0 (0239). 2,50 / 1,25 / — / 10,00.
    GPT4O: ModelPrice(
        model_id=GPT4O,
        input_per_mtok=Decimal("2.50"),
        cache_read_per_mtok=Decimal("1.25"),
        output_per_mtok=Decimal("10.00"),
        quota_weight_input=Decimal("0.55"),
        quota_weight_cache_read=Decimal("0.275"),
        quota_weight_cache_write=Decimal("0"),
        quota_weight_output=Decimal("2.2"),
    ),
    # 0,10 / 0,01 / 0,125 / 0,50 → 0,022 / 0,0022 / 0,0275 / 0,11; x5 por encima de 100.000.
    HAIKU: ModelPrice(
        model_id=HAIKU,
        input_per_mtok=Decimal("0.10"),
        cache_read_per_mtok=Decimal("0.01"),
        cache_write_per_mtok=Decimal("0.125"),
        output_per_mtok=Decimal("0.50"),
        quota_weight_input=Decimal("0.022"),
        quota_weight_cache_read=Decimal("0.0022"),
        quota_weight_cache_write=Decimal("0.0275"),
        quota_weight_output=Decimal("0.11"),
        tier_above_tokens=100_000,
        tier_multiplier=Decimal("5"),
    ),
    # Tiene tarifa de escritura y nadie le puso el peso.
    NO_WRITE_WEIGHT: ModelPrice(
        model_id=NO_WRITE_WEIGHT,
        input_per_mtok=Decimal("3.00"),
        cache_read_per_mtok=Decimal("0.30"),
        cache_write_per_mtok=Decimal("3.75"),
        output_per_mtok=Decimal("15.00"),
        quota_weight_input=Decimal("0.66"),
        quota_weight_cache_read=Decimal("0.066"),
        quota_weight_output=Decimal("3.3"),
    ),
    # Dado de alta en el panel con tres pesos y sin tarifa de escritura: nada que cobrar.
    BORN_IN_PANEL: ModelPrice(
        model_id=BORN_IN_PANEL,
        input_per_mtok=Decimal("2.50"),
        cache_read_per_mtok=Decimal("1.25"),
        output_per_mtok=Decimal("10.00"),
        quota_weight_input=Decimal("0.55"),
        quota_weight_cache_read=Decimal("0.275"),
        quota_weight_output=Decimal("2.2"),
    ),
}
WEIGHTS = lane_weights_from(CATALOG)


def _call(
    model: str,
    *,
    prompt: int,
    read: int = 0,
    write: int = 0,
    output: int = 0,
    turn: str = "t1",
    seq: int = 1,
) -> list[dict[str, Any]]:
    """Las filas nativas de UNA llamada, como las deja ``rows_from_entry``."""
    return [
        {
            "model": model,
            "meter": meter,
            "quantity": qty,
            "billable_qty": qty,
            "idempotency_key": f"{turn}:{seq}:{meter}",
        }
        for meter, qty in (
            ("llm.input_tokens", prompt),
            ("llm.cache_read", read),
            ("llm.cache_write", write),
            ("llm.output_tokens", output),
        )
        if qty
    ]


def _debit(model: str, **usage: int) -> int:
    return _turn_quota(_call(model, **usage), WEIGHTS)["t1"]


def _breakdown(model: str, **usage: int) -> dict[str, float]:
    rows = _call(model, **usage)
    _apply_lane_weights(rows, WEIGHTS)
    return {r["meter"]: r["billable_qty"] for r in rows}


def _companion(model: str, *, prompt: int, read: int = 0, write: int = 0, output: int = 0) -> int:
    """El copiloto acumula la entrada no leída (``prompt - lectura``) y la escritura aparte."""
    return _turn_quota_units(
        uncached=prompt - read,
        cache_read=read,
        cache_write=write,
        output=output,
        lanes=weights_for(model, WEIGHTS),
    )


# ── Anthropic ──────────────────────────────────────────────────────────────


def test_anthropic_charges_input_without_both_caches_and_the_write_with_its_weight() -> None:
    """10.000 de prompt = 1.000 frescos + 6.000 leídos + 3.000 escritos; 500 de salida.

    1.000 x 0,66 + 6.000 x 0,066 + 3.000 x 0,825 + 500 x 3,3 = 660 + 396 + 2.475 + 1.650.
    Con tres carriles eran 4.000 x 0,66 + 396 + 1.650 = 4.686: la escritura a 1x.
    """
    usage = {"prompt": 10_000, "read": 6_000, "write": 3_000, "output": 500}
    assert _debit(SONNET, **usage) == 660 + 396 + 2_475 + 1_650 == 5_181
    assert _breakdown(SONNET, **usage) == {
        "llm.input_tokens": 660.0,
        "llm.cache_read": 396.0,
        "llm.cache_write": 2_475.0,
        "llm.output_tokens": 1_650.0,
    }
    assert _companion(SONNET, **usage) == 5_181, "el copiloto da la misma cifra"


# ── el margen ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("model", [SONNET, SOL, HAIKU])
@pytest.mark.parametrize(
    ("lane", "usage", "rate_attr"),
    [
        ("input", {"prompt": 100_000}, "input_per_mtok"),
        ("cache_read", {"prompt": 100_000, "read": 100_000}, "cache_read_per_mtok"),
        ("cache_write", {"prompt": 100_000, "write": 100_000}, "cache_write_per_mtok"),
        ("output", {"prompt": 0, "output": 100_000}, "output_per_mtok"),
    ],
)
def test_the_margin_is_the_multiplier_in_all_four_lanes(
    model: str, lane: str, usage: dict[str, int], rate_attr: str
) -> None:
    """Cada carril solo, 100.000 tokens: venta (unidades / 1e6 x 10 USD) entre coste (tokens x
    tarifa / 1e6) es 2,2 en los cuatro. Con la escritura dentro de la entrada, el carril de
    escritura de Sonnet salía a 0,66 x 10 / 3,75 = 1,76, por debajo del objetivo."""
    units = _debit(model, **usage)
    sale = Decimal(units) / Decimal(1_000_000) * 10
    cost = Decimal(100_000) * getattr(CATALOG[model], rate_attr) / Decimal(1_000_000)
    assert sale / cost == Decimal("2.2"), f"{model} {lane}: {sale} / {cost}"


# ── GPT-5.6 ────────────────────────────────────────────────────────────────


def test_gpt56_charges_the_write_by_its_lane_and_not_also_as_input() -> None:
    """9.000 de prompt = 1.000 frescos + 5.000 leídos + 3.000 escritos; 20 de salida.

    1.000 x 0,88 + 5.000 x 0,088 + 3.000 x 1,10 + 20 x 4,4 = 880 + 440 + 3.300 + 88. Si lo
    escrito se cobrara además como entrada serían 2.640 más.
    """
    usage = {"prompt": 9_000, "read": 5_000, "write": 3_000, "output": 20}
    assert _debit(SOL, **usage) == 880 + 440 + 3_300 + 88 == 4_708
    assert _breakdown(SOL, **usage)["llm.input_tokens"] == 880.0
    assert _breakdown(SOL, **usage)["llm.cache_write"] == 3_300.0
    assert _companion(SOL, **usage) == 4_708


# ── sin tarifa de escritura ────────────────────────────────────────────────


@pytest.mark.parametrize("model", [GPT4O, BORN_IN_PANEL])
def test_a_model_without_a_write_tariff_is_charged_as_before(model: str) -> None:
    """La escritura (si el proveedor la contara) sigue dentro de la entrada, como hasta la 065:
    (10.000 - 4.000) x 0,55 + 4.000 x 0,275 + 100 x 2,2 = 3.300 + 1.100 + 220 = 4.620.

    ``BORN_IN_PANEL`` tiene el peso nulo y tampoco tarifa: lo mismo que peso 0."""
    usage = {"prompt": 10_000, "read": 4_000, "write": 3_000, "output": 100}
    assert _debit(model, **usage) == 3_300 + 1_100 + 220 == 4_620
    assert _breakdown(model, **usage) == {
        "llm.input_tokens": 3_300.0,
        "llm.cache_read": 1_100.0,
        "llm.cache_write": 0.0,
        "llm.output_tokens": 220.0,
    }
    assert _companion(model, **usage) == 4_620


# ── el tramo de Haiku 5.5 ──────────────────────────────────────────────────


def test_haiku_above_100k_prompt_tokens_uses_the_tier_weights() -> None:
    """120.000 de prompt (20.000 escritos), 1.000 de salida, x5:
    (100.000 x 0,022 + 20.000 x 0,0275 + 1.000 x 0,11) x 5 = (2.200 + 550 + 110) x 5."""
    usage = {"prompt": 120_000, "write": 20_000, "output": 1_000}
    assert _debit(HAIKU, **usage) == (2_200 + 550 + 110) * 5 == 14_300
    assert _breakdown(HAIKU, **usage) == {
        "llm.input_tokens": 11_000.0,
        "llm.cache_write": 2_750.0,
        "llm.output_tokens": 550.0,
    }


def test_the_tier_starts_strictly_above_the_threshold() -> None:
    """100.000 justos no pasan: 100.000 x 0,022 + 1.000 x 0,11 = 2.200 + 110."""
    assert _debit(HAIKU, prompt=100_000, output=1_000) == 2_310


def test_the_tier_is_per_call_not_per_turn() -> None:
    """Dos llamadas de 60.000 en un turno no pasan el umbral: 2 x 60.000 x 0,022."""
    rows = _call(HAIKU, prompt=60_000, seq=1) + _call(HAIKU, prompt=60_000, seq=2)
    assert _turn_quota(rows, WEIGHTS)["t1"] == 2 * 1_320


# ── tarifa sin peso ────────────────────────────────────────────────────────


def test_a_write_tariff_without_its_weight_is_unweighted_not_free() -> None:
    """Con tarifa de escritura y el peso nulo, cobrar 0 por lo escrito sería el cobro
    silencioso a la baja que la 007 quitó. Se rechaza nombrando el carril, y el turno queda
    medido y sin débito, con su motivo."""
    with pytest.raises(UnweightedModel, match="cache_write"):
        weights_for(NO_WRITE_WEIGHT, WEIGHTS)
    with structlog.testing.capture_logs() as logs:
        debits = _turn_quota(
            _call(NO_WRITE_WEIGHT, prompt=10_000, read=6_000, write=3_000, output=500),
            WEIGHTS,
        )
        rows = _call(NO_WRITE_WEIGHT, prompt=10_000, write=3_000)
        _apply_lane_weights(rows, WEIGHTS)
    assert debits == {}
    assert [e["event"] for e in logs] == [
        "metering.unweighted_model",
        "metering.unweighted_model_breakdown",
    ]


def test_the_write_weight_has_no_default() -> None:
    """Un ``LaneWeights`` sin el cuarto peso es un ``TypeError``, no un 0 que nadie ve."""
    with pytest.raises(TypeError):
        LaneWeights(input=Decimal(1), cache_read=Decimal(1), output=Decimal(1))  # type: ignore[call-arg]
