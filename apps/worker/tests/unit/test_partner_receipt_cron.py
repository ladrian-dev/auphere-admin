"""Unit tests for the partner-receipt cron's pure period logic."""

from __future__ import annotations

from datetime import date

import pytest

from nexus_worker.streams.partner_receipt_cron import _previous_month

pytestmark = [pytest.mark.unit]


class TestPreviousMonth:
    def test_mid_year(self) -> None:
        assert _previous_month(date(2026, 7, 1)) == (2026, 6)

    def test_january_rolls_to_december(self) -> None:
        assert _previous_month(date(2026, 1, 1)) == (2025, 12)

    def test_march(self) -> None:
        assert _previous_month(date(2026, 3, 1)) == (2026, 2)
