"""Spec 004 · R2.1, R2.2 — the pool renews every seven days, on the partner's day.

Pure functions, no database. The anchor is ``partners.created_at``, which
already exists and never moves — no new column, and therefore no second piece
of state to keep in sync with the first.

Why not a global Monday: it concentrates every partner's renewal into one tick,
and it gives a partner who signs up on Friday a first "week" of two days.
Anthropic anchors per account ("a fixed reset schedule assigned to your
account") for the same reasons.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from nexus_api.metering.wallet import next_period_end

pytestmark = [pytest.mark.asyncio]


async def test_the_period_is_seven_days_long() -> None:
    anchor = datetime(2026, 9, 2, 14, 30, tzinfo=UTC)  # a Wednesday
    now = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)

    end = next_period_end(anchor=anchor, now=now)

    assert end > now
    assert (end - anchor).days % 7 == 0, "the boundary must land on a multiple of 7 days"


async def test_two_partners_created_on_different_days_renew_on_different_days() -> None:
    now = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    a = next_period_end(anchor=datetime(2026, 9, 2, 0, 0, tzinfo=UTC), now=now)
    b = next_period_end(anchor=datetime(2026, 9, 5, 0, 0, tzinfo=UTC), now=now)

    assert a != b, "there is no global Monday: each partner has its own day"


async def test_a_friday_signup_gets_a_whole_first_week() -> None:
    """The case a global Monday would shortchange."""
    friday = datetime(2026, 9, 4, 18, 0, tzinfo=UTC)

    end = next_period_end(anchor=friday, now=friday)

    assert end - friday == timedelta(days=7)


async def test_the_boundary_is_in_the_future_even_long_after_the_anchor() -> None:
    """A partner created a year ago still gets its next boundary, not a past one."""
    anchor = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    now = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)

    end = next_period_end(anchor=anchor, now=now)

    assert end > now
    assert (end - now) <= timedelta(days=7)


async def test_exactly_on_the_boundary_moves_to_the_next_one() -> None:
    """Never returns "now": a boundary that equals the clock expires instantly
    and the renewal loop would fire twice."""
    anchor = datetime(2026, 9, 2, 0, 0, tzinfo=UTC)
    now = anchor + timedelta(days=14)

    end = next_period_end(anchor=anchor, now=now)

    assert end == now + timedelta(days=7)


async def test_a_naive_anchor_is_treated_as_utc() -> None:
    """``created_at`` comes back naive from some drivers; a crash here would
    take down the renewal cron for every partner at once."""
    naive = datetime(2026, 9, 2, 0, 0)
    now = datetime(2026, 9, 3, 0, 0, tzinfo=UTC)

    end = next_period_end(anchor=naive, now=now)

    assert end.tzinfo is not None
    assert end > now
