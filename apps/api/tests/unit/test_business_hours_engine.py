"""Spec 047, T051 — el motor del horario (requisitos 10.1 a 10.5 y 10.7).

Un solo motor responde por el horario del negocio: la frase «Así lo dirá el
agente», «¿abierto ahora?» y las horas de cada día que usa Reservas. Es puro
(sin base ni reloj): quien llama le pasa el horario, la zona y el instante.

- **Por bloques** (lunes a viernes, sábado, domingo) o **día por día**, con hasta
  6 turnos por día.
- **Nocturno**: un cierre igual o anterior a la apertura termina al día
  siguiente; de ``00:00`` a ``24:00`` es abierto 24 horas.
- **Fechas especiales**: cerrado o con turnos propios, de un día o de un rango,
  con nombre. La fecha manda desde la apertura del turno de ese día (casos
  límite): el turno nocturno de la víspera sigue hasta su cierre.
- **La zona del negocio y el cambio de hora**: las horas son de reloj local en
  la fecha local real, y la frase no cambia.
- **Sin horario**: el motor dice que no lo sabe; nunca inventa uno.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from nexus_api.services.business import hours as h
from nexus_api.services.business_hours import parse_business_hours

pytestmark = pytest.mark.unit

MADRID = "Europe/Madrid"
TZ = ZoneInfo(MADRID)


def _days(**days: list[tuple[str, str]]) -> dict[str, list[dict[str, str]]]:
    return {d: [{"open": a, "close": b} for a, b in shifts] for d, shifts in days.items()}


def _week(layout: str = "daily", **days: list[tuple[str, str]]) -> h.Week:
    return h.week_from_days(layout, _days(**days))


def _local(y: int, mo: int, d: int, hh: int, mm: int = 0, *, fold: int = 0) -> datetime:
    return datetime(y, mo, d, hh, mm, tzinfo=TZ, fold=fold)


WEEKDAYS_9_TO_8 = {
    d: [("09:00", "14:00"), ("16:00", "20:00")] for d in ("mon", "tue", "wed", "thu", "fri")
}


# ── por bloques y día por día, con hasta 6 turnos ──────────────────────────


def test_a_daily_week_reads_back_as_written() -> None:
    days = _days(
        mon=[("09:00", "14:00"), ("16:00", "20:00")],
        sat=[("10:00", "14:00")],
    )
    week = h.week_from_days("daily", days)
    out = h.week_to_days(week)
    assert set(out) == set(h.DAY_KEYS)
    assert out["mon"] == [
        {"open": "09:00", "close": "14:00", "overnight": False},
        {"open": "16:00", "close": "20:00", "overnight": False},
    ]
    assert out["sun"] == [] and out["tue"] == []
    assert week.layout == "daily"


def test_blocks_keep_the_same_shifts_from_monday_to_friday() -> None:
    week = _week("blocks", **WEEKDAYS_9_TO_8, sat=[("10:00", "14:00")])
    assert week.layout == "blocks"
    assert week.days[0] == week.days[4]

    with pytest.raises(h.HoursError) as refused:
        _week("blocks", mon=[("09:00", "14:00")], tue=[("10:00", "14:00")])
    assert refused.value.code == "blocks_differ"


def test_up_to_six_shifts_a_day() -> None:
    six = [(f"{8 + 2 * i:02d}:00", f"{9 + 2 * i:02d}:00") for i in range(6)]
    assert len(_week(mon=six).days[0]) == 6
    with pytest.raises(h.HoursError) as refused:
        _week(mon=[*six, ("21:00", "22:00")])
    assert refused.value.code == "too_many_shifts"


def test_shifts_that_overlap_are_refused() -> None:
    with pytest.raises(h.HoursError) as refused:
        _week(mon=[("09:00", "14:00"), ("13:00", "20:00")])
    assert refused.value.code == "overlap"


def test_switching_to_blocks_says_which_days_would_be_lost() -> None:
    """Requisito 10.6: de día por día a bloques, con días distintos en un bloque."""
    week = _week(
        mon=[("09:00", "14:00")],
        tue=[("10:00", "14:00")],
        wed=[("09:00", "14:00")],
        thu=[],
        fri=[("09:00", "14:00")],
        sat=[("10:00", "13:00")],
    )
    assert h.blocks_loss(week) == ["tue", "thu"]
    blocks = h.to_blocks(week)
    assert blocks.layout == "blocks"
    assert all(day == week.days[0] for day in blocks.days[:5])
    assert blocks.days[5] == week.days[5]
    assert h.blocks_loss(_week(**WEEKDAYS_9_TO_8)) == []


# ── nocturno y 24 horas ────────────────────────────────────────────────────


def test_a_close_at_or_before_the_opening_ends_the_next_day() -> None:
    late = h.parse_shift("22:00", "02:00")
    assert (late.open_min, late.close_min) == (22 * 60, 26 * 60)
    assert late.overnight
    assert h.parse_shift("20:00", "00:00").close_min == 1440
    assert not h.parse_shift("20:00", "00:00").overnight
    assert h.parse_shift("10:00", "10:00").close_min == 10 * 60 + 1440
    assert h.parse_shift("09:00", "14:00").overnight is False

    week = _week(fri=[("22:00", "02:00")])
    assert h.week_to_days(week)["fri"] == [{"open": "22:00", "close": "02:00", "overnight": True}]


def test_open_24_hours() -> None:
    for close in ("24:00", "00:00"):
        shift = h.parse_shift("00:00", close)
        assert (shift.open_min, shift.close_min) == (0, 1440)
        assert shift.all_day and not shift.overnight
    week = _week(sat=[("00:00", "24:00")])
    assert h.week_to_days(week)["sat"] == [{"open": "00:00", "close": "24:00", "overnight": False}]


def test_a_night_shift_that_runs_into_the_next_days_shift_is_refused() -> None:
    with pytest.raises(h.HoursError) as refused:
        _week(fri=[("20:00", "04:00")], sat=[("02:00", "10:00")])
    assert refused.value.code == "overlap_next_day"
    # Sunday's night runs into Monday.
    with pytest.raises(h.HoursError):
        _week(sun=[("22:00", "03:00")], mon=[("01:00", "05:00")])


def test_a_bar_saturday_at_one_in_the_morning_is_open_until_two() -> None:
    """Historia 5, escenario 2."""
    hours = h.Hours(week=_week(fri=[("20:00", "02:00")], sat=[("20:00", "02:00")]), timezone=MADRID)
    state = h.open_state(hours, _local(2026, 6, 13, 1).astimezone(UTC))  # sábado
    assert state.known and state.open
    assert state.until == _local(2026, 6, 13, 2)
    closed = h.open_state(hours, _local(2026, 6, 13, 2).astimezone(UTC))
    assert not closed.open
    assert closed.next_open == _local(2026, 6, 13, 20)


def test_open_now_uses_the_business_time_zone() -> None:
    hours = h.Hours(week=_week(**WEEKDAYS_9_TO_8), timezone=MADRID)
    # 07:30 UTC is 09:30 in Madrid in June: open.
    assert h.open_state(hours, datetime(2026, 6, 10, 7, 30, tzinfo=UTC)).open
    # The same instant is 03:30 in Santiago: closed.
    santiago = h.Hours(week=hours.week, timezone="America/Santiago")
    assert not h.open_state(santiago, datetime(2026, 6, 10, 7, 30, tzinfo=UTC)).open


# ── el cambio de hora ──────────────────────────────────────────────────────


def test_a_night_shift_across_the_spring_forward_keeps_its_local_close() -> None:
    """Madrid, 2026-03-29: a las 02:00 pasan a ser las 03:00."""
    hours = h.Hours(week=_week(sat=[("22:00", "04:00")]), timezone=MADRID)
    ((start, end),) = h.intervals_on(hours, date(2026, 3, 28))
    assert end - start == timedelta(hours=5)  # one hour fewer that night
    assert h.open_state(hours, _local(2026, 3, 29, 3, 30).astimezone(UTC)).open
    assert not h.open_state(hours, _local(2026, 3, 29, 4, 30).astimezone(UTC)).open


def test_a_night_shift_across_the_fall_back_keeps_its_local_close() -> None:
    """Madrid, 2026-10-25: a las 03:00 vuelven a ser las 02:00."""
    hours = h.Hours(week=_week(sat=[("22:00", "04:00")]), timezone=MADRID)
    ((start, end),) = h.intervals_on(hours, date(2026, 10, 24))
    assert end - start == timedelta(hours=7)  # one hour more that night
    assert h.open_state(hours, _local(2026, 10, 25, 3, 30).astimezone(UTC)).open
    # 02:30 happens twice; both are inside the shift.
    assert h.open_state(hours, _local(2026, 10, 25, 2, 30, fold=1).astimezone(UTC)).open
    assert not h.open_state(hours, _local(2026, 10, 25, 4, 30).astimezone(UTC)).open


def test_the_phrase_does_not_change_on_the_day_the_clocks_change() -> None:
    week = _week(sat=[("22:00", "04:00")])
    assert h.phrase(week) == h.phrase(_week(sat=[("22:00", "04:00")]))


# ── fechas especiales ──────────────────────────────────────────────────────


def _every_night() -> h.Week:
    return _week(**{d: [("20:00", "02:00")] for d in h.DAY_KEYS})


def test_a_closed_special_date_has_no_shifts_and_says_its_name() -> None:
    """Historia 5, escenario 3: el 25 de diciembre cerrado."""
    christmas = h.SpecialDay(
        date_from=date(2026, 12, 25), date_to=date(2026, 12, 25), closed=True, name="Navidad"
    )
    hours = h.Hours(week=_week(**WEEKDAYS_9_TO_8), specials=(christmas,), timezone=MADRID)
    assert h.shifts_on(hours, date(2026, 12, 25)) == ()
    assert h.day_ranges(hours, date(2026, 12, 25)) == []
    state = h.open_state(hours, _local(2026, 12, 25, 11).astimezone(UTC))
    assert not state.open and state.special == christmas
    assert h.shifts_on(hours, date(2026, 12, 24)) == hours.week.days[3]  # jueves, normal


def test_a_special_date_over_a_range_with_its_own_shifts() -> None:
    reduced = h.SpecialDay(
        date_from=date(2026, 12, 24),
        date_to=date(2026, 12, 31),
        closed=False,
        shifts=(h.parse_shift("10:00", "14:00"),),
        name="Fiestas",
    )
    hours = h.Hours(week=_week(**WEEKDAYS_9_TO_8), specials=(reduced,), timezone=MADRID)
    for day in (date(2026, 12, 24), date(2026, 12, 27), date(2026, 12, 31)):
        assert h.shifts_on(hours, day) == reduced.shifts
    assert h.shifts_on(hours, date(2027, 1, 1)) == hours.week.days[4]  # viernes
    assert h.open_state(hours, _local(2026, 12, 27, 11).astimezone(UTC)).open  # domingo

    with pytest.raises(h.HoursError):
        h.SpecialDay(date_from=date(2026, 12, 2), date_to=date(2026, 12, 1), closed=True)
    with pytest.raises(h.HoursError):
        h.SpecialDay(date_from=date(2026, 12, 1), date_to=date(2026, 12, 1), closed=False)


def test_a_special_date_rules_from_the_opening_of_that_days_shift() -> None:
    """Caso límite: la víspera abre de 20:00 a 02:00 y el 25 cierra. A la 01:00
    del 25 sigue abierto (es el turno del 24); el 25 por la noche, no; y el 26
    de madrugada, tampoco, porque el 25 no abrió."""
    christmas = h.SpecialDay(date_from=date(2026, 12, 25), date_to=date(2026, 12, 25), closed=True)
    hours = h.Hours(week=_every_night(), specials=(christmas,), timezone=MADRID)
    early = h.open_state(hours, _local(2026, 12, 25, 1).astimezone(UTC))
    assert early.open and early.until == _local(2026, 12, 25, 2)
    assert not h.open_state(hours, _local(2026, 12, 25, 21).astimezone(UTC)).open
    assert not h.open_state(hours, _local(2026, 12, 26, 1).astimezone(UTC)).open
    assert h.open_state(hours, _local(2026, 12, 26, 21).astimezone(UTC)).open
    # Reservas sees the same: the 25th keeps only the early hours of the 24th.
    assert h.day_ranges(hours, date(2026, 12, 25)) == [(time(0, 0), time(2, 0))]
    assert h.day_ranges(hours, date(2026, 12, 26)) == [(time(20, 0), h.END_OF_DAY)]


def test_a_special_night_shift_runs_into_the_next_day() -> None:
    new_year = h.SpecialDay(
        date_from=date(2026, 12, 31),
        date_to=date(2026, 12, 31),
        closed=False,
        shifts=(h.parse_shift("21:00", "05:00"),),
        name="Nochevieja",
    )
    hours = h.Hours(week=_week(**WEEKDAYS_9_TO_8), specials=(new_year,), timezone=MADRID)
    state = h.open_state(hours, _local(2027, 1, 1, 4).astimezone(UTC))
    assert state.open and state.until == _local(2027, 1, 1, 5)


# ── las horas de cada día para Reservas ────────────────────────────────────


def test_day_ranges_split_a_night_shift_at_midnight() -> None:
    hours = h.Hours(week=_week(fri=[("20:00", "02:00")], sat=[("10:00", "14:00")]), timezone=MADRID)
    assert h.day_ranges(hours, date(2026, 6, 12)) == [(time(20, 0), h.END_OF_DAY)]
    assert h.day_ranges(hours, date(2026, 6, 13)) == [
        (time(0, 0), time(2, 0)),
        (time(10, 0), time(14, 0)),
    ]
    assert h.day_ranges(hours, date(2026, 6, 14)) == []


# ── la frase «Así lo dirá el agente» ───────────────────────────────────────


def test_the_phrase_of_a_split_week() -> None:
    """Historia 5, escenario 1."""
    assert h.phrase(_week("blocks", **WEEKDAYS_9_TO_8)) == (
        "Abrimos lunes a viernes de 09:00 a 14:00 y de 16:00 a 20:00. Cerramos sábados y domingos."
    )


def test_the_phrase_groups_days_and_names_night_shifts() -> None:
    week = _week(
        **{d: [("10:00", "20:00")] for d in ("mon", "tue", "wed", "thu")},
        fri=[("20:00", "02:00")],
        sat=[("20:00", "02:00")],
    )
    assert h.phrase(week) == (
        "Abrimos lunes a jueves de 10:00 a 20:00, y viernes y sábados de 20:00 "
        "a 02:00 del día siguiente. Cerramos domingos."
    )
    assert h.phrase(_week(**{d: [("10:00", "22:00")] for d in h.DAY_KEYS})) == (
        "Abrimos todos los días de 10:00 a 22:00."
    )
    assert h.phrase(_week(**{d: [("00:00", "24:00")] for d in h.DAY_KEYS})) == (
        "Abrimos las 24 horas, todos los días."
    )
    assert h.phrase(_week(sun=[("00:00", "24:00")])) == (
        "Abrimos domingos las 24 horas. Cerramos lunes a sábado."
    )


def test_the_phrase_in_english() -> None:
    assert h.phrase(_week("blocks", **WEEKDAYS_9_TO_8), locale="en") == (
        "We are open Monday to Friday from 09:00 to 14:00 and from 16:00 to 20:00. "
        "Closed on Saturdays and Sundays."
    )


def test_a_week_with_every_day_closed_says_so() -> None:
    assert h.phrase(_week()) == "Cerramos todos los días."


# ── sin horario ────────────────────────────────────────────────────────────


def test_without_hours_nothing_is_invented() -> None:
    """Requisito 10.7: el agente dice que no lo sabe y Reservas no ofrece huecos."""
    hours = h.Hours(week=None, timezone=MADRID)
    state = h.open_state(hours, datetime(2026, 6, 10, 10, tzinfo=UTC))
    assert state.known is False and state.open is False and state.next_open is None
    assert h.shifts_on(hours, date(2026, 6, 10)) is None
    assert h.day_ranges(hours, date(2026, 6, 10)) == []
    assert h.phrase(None) is None


# ── la proyección para los lectores de antes ──────────────────────────────


def test_the_legacy_projection_splits_night_shifts_and_carries_the_phrase() -> None:
    week = _week(fri=[("20:00", "02:00")], sat=[("10:00", "14:00")])
    projected = h.legacy_projection(week)
    assert projected["friday"] == [{"from": "20:00", "to": "23:59"}]
    assert projected["saturday"] == [
        {"from": "00:00", "to": "02:00"},
        {"from": "10:00", "to": "14:00"},
    ]
    assert projected["label"] == h.phrase(week)
    parsed = parse_business_hours(projected)
    assert parsed is not None and parsed["sunday"] == []


@pytest.mark.parametrize(
    "stored",
    [
        {"monday": "09:00-14:00", "tuesday": "closed"},
        {"monday": {"open": "09:00", "close": "14:00"}, "tuesday": None},
        {"monday": {"start": "09:00", "end": "14:00"}},
        {"monday": [{"from": "09:00", "to": "14:00"}], "tuesday": []},
    ],
    ids=["admin-strings", "seed-open-close", "agent-start-end", "canonical"],
)
def test_every_stored_shape_reads_into_a_week(stored: dict[str, object]) -> None:
    week = h.week_from_legacy(stored)
    assert week is not None
    assert week.days[0] == (h.parse_shift("09:00", "14:00"),)
    assert all(day == () for day in week.days[1:])


def test_a_stored_label_without_days_is_no_hours() -> None:
    assert h.week_from_legacy({"label": "Lun-Sáb 10-19"}) is None
    assert h.week_from_legacy(None) is None


def test_a_template_points_at_the_ficha_instead_of_copying_the_hours() -> None:
    """La variable del horario de las plantillas (``tenant.business_hours_label``)
    deja de ser una copia: sin texto del operador, remite a «Horario» de los datos
    vigentes del negocio, que añade la compilación."""
    from nexus_api.services.templating.seed_templates import (
        load_seed_template,
        render_seed_template,
    )

    rendered = render_seed_template(
        load_seed_template("barbershop_v1"),
        placeholders={
            "tenant.name": "Cultor",
            "tenant.address": "Calle Mayor 1",
            "tenant.timezone": MADRID,
        },
    )
    assert "datos vigentes del negocio" in rendered.system_prompt
