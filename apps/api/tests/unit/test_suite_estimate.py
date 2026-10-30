"""Spec 047, enmienda del 2026-10-29, T195/T206 — el coste de la suite se estima
antes de correrla (requisito 61.8; research D52).

Una pasada son de media 4 turnos del agente, 4 mensajes del cliente simulado y el
juez; tres pasadas por prueba. A precio (el de «Construcción y pruebas»). Un
precio que no se conoce no es un coste cero: la estimación dice cuál falta.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from nexus_api.services.router_catalog import Price
from nexus_api.services.testing.estimate import (
    AGENT_TURNS,
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
        "agent": 20 * 3 * AGENT_TURNS,
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
