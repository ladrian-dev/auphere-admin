"""Reglas puras del libro Fase 3: included primero, caducidad, partición."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from nexus_api.metering.pricing_policy import LaneWeights
from nexus_api.metering.quota import quota_tokens
from nexus_api.metering.wallet import effective_included, split_spend


def test_included_spent_before_purchased() -> None:
    inc, pur = split_spend(30, included=10, purchased=100)
    assert inc == 10
    assert pur == 20


def test_cannot_spend_without_quota() -> None:
    inc, pur = split_spend(50, included=0, purchased=0)
    assert inc == 0
    assert pur == 0


def test_spend_stops_at_available() -> None:
    inc, pur = split_spend(80, included=5, purchased=10)
    assert inc == 5
    assert pur == 10


def test_expired_included_is_zero() -> None:
    past = datetime.now(UTC) - timedelta(seconds=1)
    assert effective_included(10_000, past) == 0


def test_future_included_counts() -> None:
    future = datetime.now(UTC) + timedelta(days=10)
    assert effective_included(10_000, future) == 10_000


def test_missing_expiry_is_zero() -> None:
    assert effective_included(10_000, None) == 0


def test_unit_is_quota_tokens_per_lane() -> None:
    """Spec 007 — la unidad del libro es lo que devuelve ``quota_tokens``.

    Con pesos neutros se ve el desglose en crudo: uncached + caché + salida,
    cada uno por su carril. Lo que este caso fija es que el **wallet** cuenta
    esa unidad y no otra, no cuánto vale cada carril — eso lo fija
    ``test_quota_lanes.py``.
    """
    neutral = LaneWeights(input=Decimal(1), cache_read=Decimal(1), output=Decimal(1))
    qty = quota_tokens(
        prompt_tokens=10_000,
        cache_read=9_000,
        output_tokens=100,
        weights=neutral,
    )
    assert qty == 1_000 + 9_000 + 100
