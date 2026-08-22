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
    ReminderConfig,
    _fmt_amount,
    _parse_due,
    _plan_reminders,
    _reminder_for,
    local_today,
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
    """Windows are RANGES, not exact days.

    They used to be equalities (``delta == 3``). Against Muna's real
    portfolio on 2026-08-20 that matched **zero** of 58 accounts with a
    balance, and 55 of them had passed all three windows for good. A stage
    you can only hit on one specific calendar day is a stage that never
    fires.
    """

    @pytest.mark.parametrize(
        ("due", "expected_stage", "expected_template"),
        [
            ("2026-07-23", "T-3", TEMPLATE_PROXIMO),  # 3 days out — window edge
            ("2026-07-22", "T-3", TEMPLATE_PROXIMO),  # 2 days out — was silent before
            ("2026-07-21", "T-3", TEMPLATE_PROXIMO),  # tomorrow — was silent before
            ("2026-07-20", "T0", TEMPLATE_PROXIMO),  # due today
            ("2026-07-13", "T+7", TEMPLATE_VENCIDO),  # exactly 7 days overdue
            ("2026-07-10", "T+7", TEMPLATE_VENCIDO),  # 10 days — was silent before
            ("2026-06-25", "T+7", TEMPLATE_VENCIDO),  # 25 days, still inside the age cap
        ],
    )
    def test_covers_the_whole_window(
        self, due: str, expected_stage: str, expected_template: str
    ) -> None:
        plan = _reminder_for(_account(due_date=due), today=_TODAY, approved=_APPROVED)
        assert plan is not None
        stage, template, _due = plan
        assert (stage, template) == (expected_stage, expected_template)

    @pytest.mark.parametrize(
        "due",
        [
            "2026-07-24",  # 4 days out — too early to chase
            "2026-07-19",  # 1 day overdue — inside the grace gap before T+7
            "2026-07-15",  # 5 days overdue — still inside the gap
        ],
    )
    def test_silent_between_windows(self, due: str) -> None:
        """The gaps are deliberate: 4+ days out is too early, and days 1-6
        overdue are the grace period before the first chase."""
        assert _reminder_for(_account(due_date=due), today=_TODAY, approved=_APPROVED) is None

    def test_age_cap_leaves_ancient_debt_alone(self) -> None:
        """Switching the daily sweep on over a neglected portfolio must not
        fire a year-old debt at someone. Muna had a live account dated
        2025-08-31 — created by the agent itself when it guessed the year."""
        ancient = _account(due_date="2025-07-13")  # ~372 days overdue
        assert _reminder_for(ancient, today=_TODAY, approved=_APPROVED) is None

    def test_age_cap_is_configurable(self) -> None:
        ancient = _account(due_date="2026-06-01")  # 49 days overdue
        assert _reminder_for(ancient, today=_TODAY, approved=_APPROVED) is None
        generous = ReminderConfig({"max_overdue_days": 90})
        assert _reminder_for(ancient, today=_TODAY, approved=_APPROVED, config=generous) is not None


class TestRunPlan:
    def test_orders_by_urgency_and_respects_the_cap(self) -> None:
        """The cap truncates the tail, so ordering decides who gets dropped.
        'Vence hoy' must never lose its slot to a three-week-old debt."""
        accounts = [
            _account(id=1, due_date="2026-07-10"),  # T+7
            _account(id=2, due_date="2026-07-23"),  # T-3
            _account(id=3, due_date="2026-07-20"),  # T0
            _account(id=4, due_date="2026-07-21"),  # T-3, closer
        ]
        plans = _plan_reminders(
            accounts, today=_TODAY, approved=_APPROVED, config=ReminderConfig({})
        )
        assert [p[0]["id"] for p in plans] == [3, 4, 2, 1]
        assert [p[1] for p in plans] == ["T0", "T-3", "T-3", "T+7"]

    def test_skips_ineligible_accounts(self) -> None:
        accounts = [
            _account(id=1, due_date="2026-07-20"),
            _account(id=2, due_date="2026-07-20", status="CANCELLED"),
            _account(id=3, due_date="2026-07-20", client_phone=""),
            _account(id=4, due_date="2026-07-24"),
        ]
        plans = _plan_reminders(
            accounts, today=_TODAY, approved=_APPROVED, config=ReminderConfig({})
        )
        assert [p[0]["id"] for p in plans] == [1]


class TestLocalToday:
    """ "Today" is the business's calendar day, never UTC's.

    Muna is America/Caracas (UTC-4): from 20:00 local onwards, UTC has
    already rolled over. Computing the windows off the UTC date shifted
    every evening run by a full stage.
    """

    def test_evening_in_caracas_is_still_the_same_local_day(self) -> None:
        from datetime import UTC, datetime

        # 2026-08-21 01:00 UTC == 2026-08-20 21:00 in Caracas.
        now = datetime(2026, 8, 21, 1, 0, tzinfo=UTC)
        assert local_today("America/Caracas", now=now) == date(2026, 8, 20)
        assert local_today("UTC", now=now) == date(2026, 8, 21)

    def test_unknown_timezone_falls_back_to_utc(self) -> None:
        from datetime import UTC, datetime

        now = datetime(2026, 8, 21, 1, 0, tzinfo=UTC)
        assert local_today("Mars/Olympus_Mons", now=now) == date(2026, 8, 21)


class TestReminderConfig:
    def test_defaults_are_off_until_a_tenant_opts_in(self) -> None:
        assert ReminderConfig(None).enabled is False
        assert ReminderConfig({}).enabled is False

    def test_reads_and_clamps(self) -> None:
        cfg = ReminderConfig(
            {"enabled": True, "hour_local": 99, "max_overdue_days": 1, "max_per_run": 0}
        )
        assert cfg.enabled is True
        assert cfg.hour_local == 23
        assert cfg.max_overdue_days == 7
        assert cfg.max_per_run == 1

    def test_junk_falls_back_to_defaults(self) -> None:
        cfg = ReminderConfig({"enabled": True, "hour_local": "nueve"})
        assert cfg.hour_local == 9


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
