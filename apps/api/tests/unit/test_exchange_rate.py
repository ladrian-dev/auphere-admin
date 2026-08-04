"""Unit tests for the CLP→USD exchange-rate service (money-sensitive)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from nexus_api.services.exchange_rate import (
    ExchangeRateUnavailable,
    _parse_observed_dollar,
    clp_to_usd,
)

pytestmark = [pytest.mark.unit]


class TestParse:
    def test_takes_the_most_recent_value(self) -> None:
        payload = {
            "nombre": "Dólar observado",
            "serie": [
                {"fecha": "2026-07-22T04:00:00.000Z", "valor": 932.84},
                {"fecha": "2026-07-21T04:00:00.000Z", "valor": 933},
            ],
        }
        assert _parse_observed_dollar(payload) == Decimal("932.84")

    @pytest.mark.parametrize(
        "payload", [{}, {"serie": []}, {"serie": [{}]}, {"serie": [{"valor": 0}]}]
    )
    def test_raises_on_bad_payload(self, payload: dict) -> None:
        with pytest.raises(ExchangeRateUnavailable):
            _parse_observed_dollar(payload)


class TestConversion:
    def test_converts_at_the_given_rate(self) -> None:
        # 36980 CLP * 2.5% = 924.5 CLP commission; at 932.84 -> ~0.99 USD
        assert clp_to_usd(Decimal("924.50"), clp_per_usd=Decimal("932.84")) == Decimal("0.99")

    def test_bigger_amount(self) -> None:
        # 1,000,000 CLP / 932.84 -> 1072.00 USD
        assert clp_to_usd(Decimal("1000000"), clp_per_usd=Decimal("932.84")) == Decimal("1072.00")

    def test_rejects_non_positive_rate(self) -> None:
        with pytest.raises(ExchangeRateUnavailable):
            clp_to_usd(Decimal("100"), clp_per_usd=Decimal("0"))
