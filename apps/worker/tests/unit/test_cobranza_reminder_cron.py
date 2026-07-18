"""Unit tests for the cobranza due-date sweep's decision logic.

DB-free: exercises the pure helpers that decide *whether* an account gets a
reminder today and *which* template — the part where an off-by-one silently
spams (or never reaches) real debtors.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from nexus_worker.streams.cobranza_reminder_cron import (
    TEMPLATE_PROXIMO,
    TEMPLATE_VENCIDO,
    _fmt_amount,
    _parse_due,
    _reminder_for,
)

pytestmark = [pytest.mark.unit]

_TODAY = date(2026, 7, 20)
_APPROVED = {TEMPLATE_PROXIMO, TEMPLATE_VENCIDO}


def _account(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": 49,
        "client_name": "Johnny Regardiz",
        "client_phone": "+584249398142",
        "total_amount": 1668.0,
        "paid_amount": 0.0,
        "status": "PENDING",
        "due_date": "2026-07-23",  # 3 days out
    }
    base.update(over)
    return base


class TestCadence:
    @pytest.mark.parametrize(
        ("due", "expected_stage", "expected_template"),
        [
            ("2026-07-23", "T-3", TEMPLATE_PROXIMO),  # 3 days before
            ("2026-07-20", "T0", TEMPLATE_PROXIMO),  # due today
            ("2026-07-13", "T+7", TEMPLATE_VENCIDO),  # 7 days overdue
        ],
    )
    def test_sends_on_the_three_configured_days(
        self, due: str, expected_stage: str, expected_template: str
    ) -> None:
        plan = _reminder_for(_account(due_date=due), today=_TODAY, approved=_APPROVED)
        assert plan is not None
        stage, template, _due = plan
        assert (stage, template) == (expected_stage, expected_template)

    @pytest.mark.parametrize("due", ["2026-07-24", "2026-07-22", "2026-07-19", "2026-07-01"])
    def test_silent_on_every_other_day(self, due: str) -> None:
        """No reminder on days outside the cadence — debtors are not spammed."""
        assert _reminder_for(_account(due_date=due), today=_TODAY, approved=_APPROVED) is None


class TestSkips:
    def test_skips_cancelled_account(self) -> None:
        acct = _account(status="CANCELLED")
        assert _reminder_for(acct, today=_TODAY, approved=_APPROVED) is None

    def test_skips_when_nothing_owed(self) -> None:
        acct = _account(total_amount=100.0, paid_amount=100.0)
        assert _reminder_for(acct, today=_TODAY, approved=_APPROVED) is None

    @pytest.mark.parametrize("phone", ["", "   ", None])
    def test_skips_account_without_phone(self, phone: str | None) -> None:
        acct = _account(client_phone=phone)
        assert _reminder_for(acct, today=_TODAY, approved=_APPROVED) is None

    def test_skips_account_without_due_date(self) -> None:
        assert _reminder_for(_account(due_date=None), today=_TODAY, approved=_APPROVED) is None

    def test_stays_idle_while_template_not_approved(self) -> None:
        """The whole point of the approval guard: nothing goes out until Meta
        approves the template."""
        assert _reminder_for(_account(), today=_TODAY, approved=set()) is None


class TestHelpers:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (1668.0, "$1.668,00"),
            (200.0, "$200,00"),
            (49450.5, "$49.450,50"),
            (9.0, "$9,00"),
        ],
    )
    def test_amount_uses_spanish_format(self, value: float, expected: str) -> None:
        assert _fmt_amount(value) == expected

    def test_parse_due_accepts_date_and_datetime(self) -> None:
        assert _parse_due("2026-07-20") == date(2026, 7, 20)
        assert _parse_due("2026-07-20T10:30:00Z") == date(2026, 7, 20)

    @pytest.mark.parametrize("value", [None, "", "not-a-date"])
    def test_parse_due_returns_none_on_junk(self, value: str | None) -> None:
        assert _parse_due(value) is None
