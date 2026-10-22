"""Spec 045 R4 — el saldo responde «hasta cuándo».

``balance_horizon`` es pura: los días del mes que quedan (hoy incluido) en la
zona del negocio y la fecha local en que se acaba el saldo al ritmo de los
últimos 7 días.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from nexus_api.services.lite_home import LiteBalance, balance_horizon

TZ = "America/Santiago"
# 2026-10-22 13:00 UTC = 10:00 en Santiago (UTC-3).
NOW = datetime(2026, 10, 22, 13, 0, tzinfo=UTC)


def _b(**kw: object) -> LiteBalance:
    base: dict[str, object] = {
        "assigned": True,
        "remaining_cents": 3013,
        "cap_cents": 5000,
        "days_left": 11.4,
    }
    base.update(kw)
    return LiteBalance(**base)  # type: ignore[arg-type]


def test_month_days_left_counts_today() -> None:
    assert balance_horizon(_b(), tz_name=TZ, now=NOW)[0] == 10  # 22..31


def test_runs_out_on_is_today_plus_whole_days() -> None:
    assert balance_horizon(_b(), tz_name=TZ, now=NOW)[1] == date(2026, 11, 2)


def test_the_business_day_not_the_utc_day() -> None:
    # 02:00 UTC del 1 de noviembre aún es 31 de octubre en Santiago.
    late = datetime(2026, 11, 1, 2, 0, tzinfo=UTC)
    month_days, runs_out = balance_horizon(_b(days_left=0.5), tz_name=TZ, now=late)
    assert month_days == 1
    assert runs_out == date(2026, 10, 31)


def test_no_spend_no_date() -> None:
    assert balance_horizon(_b(days_left=None), tz_name=TZ, now=NOW) == (10, None)


def test_unassigned_no_date() -> None:
    assert balance_horizon(_b(assigned=False, days_left=3.0), tz_name=TZ, now=NOW)[1] is None


def test_out_of_balance_runs_out_today() -> None:
    assert balance_horizon(_b(remaining_cents=0, days_left=0.0), tz_name=TZ, now=NOW)[1] == date(
        2026, 10, 22
    )
