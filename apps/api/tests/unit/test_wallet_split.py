"""Reglas puras del libro Fase 3: included primero, caducidad, partición."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


def test_unit_is_quota_tokens_c3() -> None:
    qty = quota_tokens(prompt_tokens=10_000, cache_read=9_000, output_tokens=100)
    assert qty == 1_000 + 900 + 100
