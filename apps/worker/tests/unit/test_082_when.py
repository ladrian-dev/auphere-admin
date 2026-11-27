"""El siguiente disparo de una rutina — spec 082, T007 (requisitos 3.2, 3.4,
3.5, 3.7 y 3.8).

Función pura, sin base de datos: dada la periodicidad, la hora local y la zona
del negocio, devuelve las próximas ejecuciones en absoluto.

Lo que de verdad se prueba aquí es el cambio de hora. Una rutina diaria a las
nueve de la mañana no es la misma hora UTC en enero que en julio, y los dos
días raros del año —el que a una hora local no le toca existir y el que le toca
dos veces— son los que producen informes duplicados o informes que no salen.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from nexus_api.services.schedules.when import next_runs

MADRID = "Europe/Madrid"
SANTIAGO = "America/Santiago"


def _at(y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=UTC)


def _local(moment: datetime, tz: str) -> datetime:
    return moment.astimezone(ZoneInfo(tz))


# ── las cuatro periodicidades ───────────────────────────────────────────────


def test_daily_gives_the_same_local_hour_every_day() -> None:
    runs = next_runs(
        cadence="daily",
        local_time=time(9, 0),
        timezone=MADRID,
        after=_at(2026, 6, 10, 12, 0),
        count=3,
    )
    assert len(runs) == 3
    assert [_local(r, MADRID).date() for r in runs] == [
        date(2026, 6, 11),
        date(2026, 6, 12),
        date(2026, 6, 13),
    ]
    assert {(_local(r, MADRID).hour, _local(r, MADRID).minute) for r in runs} == {(9, 0)}


def test_daily_today_still_counts_if_the_hour_has_not_passed() -> None:
    runs = next_runs(
        cadence="daily",
        local_time=time(23, 0),
        timezone=MADRID,
        after=_at(2026, 6, 10, 12, 0),
        count=1,
    )
    assert _local(runs[0], MADRID).date() == date(2026, 6, 10)


def test_weekly_follows_its_days_with_monday_as_zero() -> None:
    """Lunes 0 y domingo 6, la convención de ``datetime.weekday()``. La maqueta
    numera al revés porque es JavaScript, y es la consola la que traduce."""
    runs = next_runs(
        cadence="weekly",
        local_time=time(8, 0),
        timezone=MADRID,
        weekdays=[0, 3],
        after=_at(2026, 6, 10, 12, 0),  # miércoles
        count=3,
    )
    locals_ = [_local(r, MADRID) for r in runs]
    assert [d.weekday() for d in locals_] == [3, 0, 3]
    assert [d.date() for d in locals_] == [date(2026, 6, 11), date(2026, 6, 15), date(2026, 6, 18)]


def test_weekly_without_days_gives_nothing() -> None:
    assert (
        next_runs(
            cadence="weekly",
            local_time=time(8, 0),
            timezone=MADRID,
            weekdays=[],
            after=_at(2026, 6, 10, 12, 0),
        )
        == []
    )


def test_monthly_runs_on_its_day_every_month() -> None:
    runs = next_runs(
        cadence="monthly",
        local_time=time(7, 30),
        timezone=MADRID,
        day_of_month=28,
        after=_at(2026, 6, 10, 12, 0),
        count=3,
    )
    assert [_local(r, MADRID).date() for r in runs] == [
        date(2026, 6, 28),
        date(2026, 7, 28),
        date(2026, 8, 28),
    ]


def test_monthly_on_the_28th_exists_in_february() -> None:
    runs = next_runs(
        cadence="monthly",
        local_time=time(7, 30),
        timezone=MADRID,
        day_of_month=28,
        after=_at(2027, 1, 30, 12, 0),
        count=1,
    )
    assert _local(runs[0], MADRID).date() == date(2027, 2, 28)


def test_once_gives_one_run_and_then_nothing() -> None:
    runs = next_runs(
        cadence="once",
        local_time=time(8, 0),
        timezone=MADRID,
        run_date=date(2026, 6, 25),
        after=_at(2026, 6, 10, 12, 0),
        count=3,
    )
    assert len(runs) == 1
    assert _local(runs[0], MADRID).date() == date(2026, 6, 25)


def test_once_in_the_past_gives_nothing() -> None:
    assert (
        next_runs(
            cadence="once",
            local_time=time(8, 0),
            timezone=MADRID,
            run_date=date(2026, 6, 1),
            after=_at(2026, 6, 10, 12, 0),
        )
        == []
    )


# ── el cambio de hora ───────────────────────────────────────────────────────


def test_the_same_local_hour_is_a_different_utc_hour_across_the_year() -> None:
    """Las nueve de Santiago en julio y en enero no son la misma hora UTC. Si
    esto se guardara en UTC, la rutina se correría una hora en cada cambio."""
    winter = next_runs(
        cadence="daily",
        local_time=time(9, 0),
        timezone=SANTIAGO,
        after=_at(2026, 7, 10, 0, 0),
        count=1,
    )[0]
    summer = next_runs(
        cadence="daily",
        local_time=time(9, 0),
        timezone=SANTIAGO,
        after=_at(2027, 1, 10, 0, 0),
        count=1,
    )[0]
    assert winter.hour != summer.hour
    assert _local(winter, SANTIAGO).hour == _local(summer, SANTIAGO).hour == 9


def test_an_hour_that_does_not_exist_runs_at_the_first_one_that_does() -> None:
    """El 28 de marzo de 2027 en Madrid el reloj salta de las 02:00 a las 03:00.
    Las 02:30 no existen ese día, y la rutina no se puede perder."""
    runs = next_runs(
        cadence="daily",
        local_time=time(2, 30),
        timezone=MADRID,
        after=_at(2027, 3, 27, 12, 0),
        count=2,
    )
    first = _local(runs[0], MADRID)
    assert first.date() == date(2027, 3, 28)
    assert (first.hour, first.minute) == (3, 0)
    # El día siguiente vuelve a su hora de siempre.
    second = _local(runs[1], MADRID)
    assert (second.date(), second.hour, second.minute) == (date(2027, 3, 29), 2, 30)


def test_an_hour_that_happens_twice_runs_once() -> None:
    """El 25 de octubre de 2026 en Madrid las 02:30 ocurren dos veces. Una
    ejecución, no dos, y la primera de las dos."""
    runs = next_runs(
        cadence="daily",
        local_time=time(2, 30),
        timezone=MADRID,
        after=_at(2026, 10, 24, 12, 0),
        count=2,
    )
    that_day = [r for r in runs if _local(r, MADRID).date() == date(2026, 10, 25)]
    assert len(that_day) == 1
    # La primera de las dos: la de la hora de verano, con desfase +02:00.
    assert that_day[0].astimezone(ZoneInfo(MADRID)).utcoffset() == timedelta(hours=2)


def test_changing_the_business_timezone_moves_the_next_run() -> None:
    """Requisito 3.7: la zona vive en la ficha del cliente, no en la rutina."""
    before = next_runs(
        cadence="daily",
        local_time=time(9, 0),
        timezone=MADRID,
        after=_at(2026, 6, 10, 12, 0),
        count=1,
    )[0]
    after_change = next_runs(
        cadence="daily",
        local_time=time(9, 0),
        timezone=SANTIAGO,
        after=_at(2026, 6, 10, 12, 0),
        count=1,
    )[0]
    assert before != after_change


# ── bordes ──────────────────────────────────────────────────────────────────


def test_a_run_exactly_at_the_cut_does_not_repeat() -> None:
    """``after`` es estricto: la que ya salió no vuelve a salir."""
    first = next_runs(
        cadence="daily",
        local_time=time(9, 0),
        timezone=MADRID,
        after=_at(2026, 6, 10, 0, 0),
        count=1,
    )[0]
    again = next_runs(
        cadence="daily",
        local_time=time(9, 0),
        timezone=MADRID,
        after=first,
        count=1,
    )[0]
    assert again > first


def test_an_unknown_timezone_is_refused_rather_than_guessed() -> None:
    with pytest.raises(ValueError):
        next_runs(
            cadence="daily",
            local_time=time(9, 0),
            timezone="Mars/Olympus",
            after=_at(2026, 6, 10, 12, 0),
        )


def test_an_unknown_cadence_is_refused() -> None:
    with pytest.raises(ValueError):
        next_runs(
            cadence="cron",
            local_time=time(9, 0),
            timezone=MADRID,
            after=_at(2026, 6, 10, 12, 0),
        )
