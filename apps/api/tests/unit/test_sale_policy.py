"""Spec 059 (requisitos 3.1, 3.3, 3.4, 3.7, 3.8, 3.10 y 3.11; T021) — la política de
venta por modelo, en cálculos puros.

El partner paga unidades de cuota a 10 US$ el millón, y un token de cada carril
cuesta ``peso`` unidades. Así que la venta por millón de un carril es ``peso * 10``,
y su multiplicador sobre el coste es ``venta / coste``. El panel propone los pesos
del multiplicador objetivo (``round(m * coste / 10, 6)``) y no deja ninguno por
debajo de 1,5 veces su coste.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from nexus_api.metering import sale_policy
from nexus_api.metering.pricing_policy import weight_drift

D = Decimal
SOL_COST = {"input": D("4"), "cache_read": D("0.4"), "output": D("20")}
SOL_WEIGHTS = {"input": D("0.88"), "cache_read": D("0.088"), "output": D("4.4")}


def test_the_proposal_is_the_target_times_the_cost_over_the_credit_price() -> None:
    assert sale_policy.propose(SOL_COST, D("2.2")) == SOL_WEIGHTS
    assert sale_policy.propose(SOL_COST, D("2.5")) == {
        "input": D("1.000000"),
        "cache_read": D("0.100000"),
        "output": D("5.000000"),
    }


def test_a_lane_without_cost_leaves_no_proposal() -> None:
    assert sale_policy.propose({**SOL_COST, "cache_read": None}, D("2.2")) is None


def test_the_floor_names_each_lane_that_sinks() -> None:
    sinking = {**SOL_WEIGHTS, "output": D("2.9")}  # 29 / 20 = 1,45x
    assert sale_policy.lanes_below_floor(sinking, SOL_COST) == ["output"]
    assert sale_policy.lanes_below_floor(SOL_WEIGHTS, SOL_COST) == []
    at_the_floor = {**SOL_WEIGHTS, "output": D("3")}  # 30 / 20 = 1,5x
    assert sale_policy.lanes_below_floor(at_the_floor, SOL_COST) == []


def test_a_target_under_the_floor_is_refused() -> None:
    with pytest.raises(sale_policy.SalePolicyError) as caught:
        sale_policy.check_target(D("1.49"))
    assert caught.value.code == "below_floor"
    sale_policy.check_target(D("1.5"))


def test_the_view_of_a_model_on_target() -> None:
    view = sale_policy.sale_view(costs=SOL_COST, weights=SOL_WEIGHTS, target=D("2.2"))
    assert view["state"] == "on_target"
    assert view["lanes"]["output"] == {
        "cost": "20.000000",
        "weight": "4.400000",
        "sale": "44.000000",
        "multiplier": "2.20",
    }
    assert view["proposed"] == {k: f"{v:.6f}" for k, v in SOL_WEIGHTS.items()}


def test_the_view_says_drift_and_below_floor() -> None:
    assert sale_policy.sale_view(costs=SOL_COST, weights=SOL_WEIGHTS, target=D("2.5"))["state"] == (
        "drift"
    )
    sinking = {**SOL_WEIGHTS, "output": D("2.9")}
    assert sale_policy.sale_view(costs=SOL_COST, weights=sinking, target=D("2.2"))["state"] == (
        "below_floor"
    )


def test_the_view_of_the_odd_cases() -> None:
    unweighted = {"input": None, "cache_read": None, "output": None}
    assert sale_policy.sale_view(costs=SOL_COST, weights=unweighted, target=D("2.2"))["state"] == (
        "unweighted"
    )
    no_cost = {"input": None, "cache_read": None, "output": None}
    assert sale_policy.sale_view(costs=no_cost, weights=SOL_WEIGHTS, target=D("2.2"))["state"] == (
        "no_cost"
    )
    per_minute = sale_policy.sale_view(
        costs=no_cost, weights=unweighted, target=D("2.2"), per_minute=True
    )
    assert per_minute["state"] == "per_minute" and per_minute["proposed"] is None


def test_without_a_target_there_is_no_proposal_but_the_floor_still_counts() -> None:
    view = sale_policy.sale_view(costs=SOL_COST, weights=SOL_WEIGHTS, target=None)
    assert view["proposed"] is None and view["state"] == "unknown"
    sinking = {**SOL_WEIGHTS, "output": D("2.9")}
    assert sale_policy.sale_view(costs=SOL_COST, weights=sinking, target=None)["state"] == (
        "below_floor"
    )


def test_the_drift_check_uses_the_target_it_is_given() -> None:
    prices = {"m": SOL_COST}
    weights = {"m": SOL_WEIGHTS}
    assert weight_drift(prices, weights, sell_usd_per_million=D(10), target=D("2.2")) == []
    drifts = weight_drift(prices, weights, sell_usd_per_million=D(10), target=D("2.5"))
    assert {d.lane for d in drifts} == {"input", "cache_read", "output"}
    assert drifts[0].expected == D("2.5") * SOL_COST[drifts[0].lane] / D(10)


def test_the_credit_price_is_the_billing_one() -> None:
    """``metering`` no importa ``billing`` (``test_billing_boundary``: el turno no
    depende del cobro), así que guarda su propia copia del precio del crédito. Esta
    prueba es la que impide que las dos diverjan."""
    from nexus_api.billing.pricing import CREDIT_USD_PER_MILLION

    assert D(CREDIT_USD_PER_MILLION) == sale_policy.SELL_USD_PER_MILLION
