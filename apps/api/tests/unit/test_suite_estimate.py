"""Spec 047, enmienda del 2026-10-29, T195/T206 — el coste de la suite se estima
antes de correrla (requisito 61.8; research D52).

Una pasada son 3 llamadas del agente (la mayor parte del prompt, de la caché), 2 del
clasificador, 2 mensajes del cliente simulado y el juez; tres pasadas por prueba. A
precio (el de «Construcción y pruebas»). Un precio que no se conoce no es un coste
cero: la estimación dice cuál falta.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from nexus_api.services.router_catalog import Price
from nexus_api.services.testing.estimate import (
    AGENT_CALLS,
    CUSTOMER_CALLS,
    JUDGE_CALLS,
    estimate_suite,
)

pytestmark = pytest.mark.unit


def _price(input_: str, output: str) -> Price:
    return Price(valid_from=date(2026, 1, 1), input=Decimal(input_), output=Decimal(output))


def test_the_suite_is_estimated_per_call_and_pass() -> None:
    prices = {"m/agent": _price("3", "15"), "m/sim": _price("1", "5"), "m/judge": _price("1", "5")}
    out = estimate_suite(
        tests=20,
        prices=prices,
        agent_model="m/agent",
        customer_model="m/sim",
        judge_model="m/judge",
    )
    assert out.calls == {
        "agent": 20 * 3 * AGENT_CALLS,
        "classify": 0,
        "customer_sim": 20 * 3 * CUSTOMER_CALLS,
        "judge": 20 * 3 * JUDGE_CALLS,
    }
    assert out.amount_micros is not None and out.amount_micros > 0
    assert out.unknown == []
    cheaper = estimate_suite(
        tests=10,
        prices=prices,
        agent_model="m/agent",
        customer_model="m/sim",
        judge_model="m/judge",
    )
    assert cheaper.amount_micros is not None and cheaper.amount_micros < out.amount_micros


def test_an_unknown_price_is_not_zero() -> None:
    out = estimate_suite(
        tests=1,
        prices={"m/agent": _price("3", "15")},
        agent_model="m/agent",
        customer_model="m/sim",
        judge_model=None,
    )
    assert out.amount_micros is None and out.unknown == ["m/sim"]
    assert out.calls["judge"] == 0


def test_seventeen_tests_cost_what_they_measured() -> None:
    """Staging, 2026-11-04: 17 pruebas en Sol costaron de 2 a 3 USD a precio de venta y
    el modal decía 10,97. Con el juez y el cliente simulado en Terra, cerca de eso."""
    sol = Price(
        valid_from=date(2026, 1, 1),
        input=Decimal("4"),
        output=Decimal("20"),
        cache_read=Decimal("0.4"),
    )
    terra = Price(
        valid_from=date(2026, 1, 1),
        input=Decimal("2"),
        output=Decimal("12"),
        cache_read=Decimal("0.2"),
    )
    out = estimate_suite(
        tests=17,
        prices={"sol": sol, "terra": terra},
        agent_model="sol",
        classify_model="sol",
        customer_model="terra",
        judge_model="terra",
    )
    assert out.amount_micros is not None
    assert 2_000_000 <= out.amount_micros <= 4_500_000
