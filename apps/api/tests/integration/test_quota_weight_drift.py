"""Spec 007 · US3 — cambiar una tarifa sin su peso se delata.

Las tarifas viven en la base para que cambiarlas sea una fila y no un despliegue
(0072). Con los pesos también en la base, actualizar un precio y olvidar su peso
deja el multiplicador de ese carril donde nadie lo mira. Es el modo de fallo que
devuelve el sistema al estado que esta spec corrige.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from nexus_api.metering.pricing_policy import QUOTA_TARGET_MULTIPLIER, weight_drift

pytestmark = [pytest.mark.integration]

SELL = Decimal(10)
#: sonnet: 3,00 / 0,30 / 15,00 USD por millón, y sus pesos correctos a 2,2x.
PRICES = {
    "m": {"input": Decimal("3.00"), "cache_read": Decimal("0.30"), "output": Decimal("15.00")}
}
GOOD = {"m": {"input": Decimal("0.66"), "cache_read": Decimal("0.066"), "output": Decimal("3.3")}}


def test_a_catalog_in_agreement_reports_nothing() -> None:
    assert weight_drift(PRICES, GOOD, sell_usd_per_million=SELL) == []


def test_a_price_that_moved_without_its_weight_is_named() -> None:
    """R6.1 — el aviso dice el modelo **y** el carril."""
    prices = {"m": {**PRICES["m"], "output": Decimal("18.00")}}  # el proveedor subió
    drifts = weight_drift(prices, GOOD, sell_usd_per_million=SELL)
    assert len(drifts) == 1
    assert drifts[0].model_id == "m"
    assert drifts[0].lane == "output"
    assert drifts[0].expected == QUOTA_TARGET_MULTIPLIER * Decimal("18.00") / SELL


def test_a_drift_that_stays_above_the_floor_is_not_the_same_as_one_that_sinks() -> None:
    """R6.2 — una imprecisión y dinero saliendo no pueden dar el mismo aviso."""
    mild = weight_drift(
        {"m": {**PRICES["m"], "output": Decimal("18.00")}}, GOOD, sell_usd_per_million=SELL
    )
    assert mild[0].below_floor is False, "3,3 x 10 / 18 = 1,83x: sigue sobre el suelo"

    severe = weight_drift(
        {"m": {**PRICES["m"], "output": Decimal("40.00")}}, GOOD, sell_usd_per_million=SELL
    )
    assert severe[0].below_floor is True, "3,3 x 10 / 40 = 0,83x: por debajo del suelo"


def test_a_model_with_no_weights_is_not_reported_as_drift() -> None:
    """R1.7 — ``whisper-1`` no tiene pesos y no los necesita. No es una deriva."""
    assert weight_drift(PRICES, {"m": None}, sell_usd_per_million=SELL) == []


def test_a_half_weighted_model_is_not_reported_as_drift_either() -> None:
    """Le corresponde a ``weights_for`` rechazarlo, no a esta comprobación
    avisar tres veces de lo mismo."""
    half = {"m": {"input": Decimal("0.66"), "cache_read": None, "output": Decimal("3.3")}}
    assert weight_drift(PRICES, half, sell_usd_per_million=SELL) == []


def test_the_real_catalog_has_no_drift() -> None:
    """El caso que importa: el catálogo sembrado por la 0120 es coherente."""
    from tests.unit.test_quota_margin import PRICES as REAL_PRICES
    from tests.unit.test_quota_margin import lanes_of

    prices = {
        m: {"input": p[0], "cache_read": p[1], "output": p[2]} for m, p in REAL_PRICES.items()
    }
    weights = {
        m: {
            "input": lanes_of(m).input,
            "cache_read": lanes_of(m).cache_read,
            "output": lanes_of(m).output,
        }
        for m in REAL_PRICES
    }
    assert weight_drift(prices, weights, sell_usd_per_million=SELL) == []
