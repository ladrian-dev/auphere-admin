"""Spec 056, T008 — un solo juego de reglas para horario y servicios (requisitos 5.1 y 5.2).

La ficha del partner y los Ajustes de Reservas aceptan y rechazan **los mismos**
valores. Las reglas viven en ``services/business/rules.py`` y su espejo de la
consola en ``apps/console/src/lib/business-rules.ts``
(``apps/console/src/lib/__tests__/business-rules.test.ts`` prueba los mismos
casos). Aquí se fijan los valores y los chequeos, y que las constantes salen de
los modelos y no de una copia.
"""

from __future__ import annotations

import pytest

from nexus_api.db.models import ReservationService
from nexus_api.db.models import business as business_models
from nexus_api.db.models import reservation as reservation_models
from nexus_api.services.business import hours, rules, services_catalog

# ── las constantes ──────────────────────────────────────────────────────────


def test_the_values_are_the_spec_ones() -> None:
    assert rules.MAX_SHIFTS_PER_DAY == 6
    assert rules.TIME_STEP == 5
    assert (rules.DURATION_MIN, rules.DURATION_MAX, rules.DURATION_STEP) == (5, 480, 5)
    assert rules.PRICE_KINDS == ("none", "free", "amount")
    assert rules.AMOUNT_MAX_MINOR == 10**12
    assert rules.CATEGORY_MAX == 40
    assert (rules.NAME_MIN, rules.NAME_MAX) == (1, 120)
    assert rules.WEEK_DAYS == hours.DAY_KEYS


def test_model_constants_are_reexported_not_copied() -> None:
    assert rules.MAX_SHIFTS_PER_DAY is business_models.MAX_SHIFTS_PER_DAY
    assert rules.MINUTES_PER_DAY is business_models.MINUTES_PER_DAY
    assert rules.PRICE_KINDS is reservation_models.PRICE_KINDS


def test_the_service_limits_match_the_columns_and_the_catalog() -> None:
    columns = ReservationService.__table__.c
    assert columns.category.type.length == rules.CATEGORY_MAX  # type: ignore[attr-defined]
    assert columns.name.type.length == rules.NAME_MAX  # type: ignore[attr-defined]
    # El catálogo de la ficha lee los mismos límites de aquí, no de una copia.
    assert services_catalog.CATEGORY_MAX is rules.CATEGORY_MAX
    assert services_catalog.NAME_MAX is rules.NAME_MAX
    assert (
        services_catalog.DURATION_MIN,
        services_catalog.DURATION_MAX,
        services_catalog.DURATION_STEP,
    ) == (rules.DURATION_MIN, rules.DURATION_MAX, rules.DURATION_STEP)


# ── las horas ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "closing", "minutes"),
    [("00:00", False, 0), ("09:05", False, 545), ("23:55", False, 1435), ("24:00", True, 1440)],
)
def test_a_time_on_the_five_minute_step(raw: str, closing: bool, minutes: int) -> None:
    assert rules.time_minutes(raw, closing=closing) == minutes


@pytest.mark.parametrize("raw", ["09:07", "12:01", "23:59"])
def test_a_time_off_the_step_is_bad_step(raw: str) -> None:
    with pytest.raises(rules.RuleError) as err:
        rules.time_minutes(raw)
    assert err.value.code == "bad_step"


@pytest.mark.parametrize("raw", ["9:00", "25:00", "12:60", "ab:cd", "", "24:05"])
def test_a_time_that_is_not_hh_mm_is_invalid_time(raw: str) -> None:
    with pytest.raises(rules.RuleError) as err:
        rules.time_minutes(raw, closing=True)
    assert err.value.code == "invalid_time"


def test_24_00_only_closes() -> None:
    with pytest.raises(rules.RuleError) as err:
        rules.time_minutes("24:00")
    assert err.value.code == "invalid_time"


def test_on_step_marks_what_to_review() -> None:
    # «Revísalo» (5.5): lo guardado antes de la regla, con minutos sueltos.
    assert rules.on_step(540)
    assert not rules.on_step(541)


# ── los turnos ──────────────────────────────────────────────────────────────


def test_a_closing_at_or_before_the_opening_is_the_next_day() -> None:
    assert rules.shift_minutes("20:00", "02:00") == (1200, 1560)
    assert rules.shift_minutes("09:00", "00:00") == (540, 1440)
    assert rules.shift_minutes("00:00", "24:00") == (0, 1440)
    assert rules.shift_minutes("00:00", "00:00") == (0, 1440)
    assert rules.shift_minutes("09:00", "13:30") == (540, 810)


def test_from_zero_to_six_shifts_a_day() -> None:
    assert rules.check_day([]) == []
    six = [(f"{h:02d}:00", f"{h:02d}:30") for h in range(8, 20, 2)]
    assert len(rules.check_day(six)) == 6
    seven = [*six, ("21:00", "21:30")]
    with pytest.raises(rules.RuleError) as err:
        rules.check_day(seven, day="mon")
    assert (err.value.code, err.value.day) == ("too_many_shifts", "mon")


def test_the_shifts_of_a_day_come_back_in_order() -> None:
    assert rules.check_day([("16:00", "20:00"), ("09:00", "13:00")]) == [(540, 780), (960, 1200)]


def test_two_shifts_of_the_same_day_do_not_overlap() -> None:
    with pytest.raises(rules.RuleError) as err:
        rules.check_day([("09:00", "14:00"), ("13:00", "18:00")], day="tue")
    assert (err.value.code, err.value.day) == ("overlap", "tue")
    # Tocarse no es solaparse.
    assert rules.check_day([("09:00", "14:00"), ("14:00", "18:00")]) == [(540, 840), (840, 1080)]


def test_a_bad_step_says_its_day() -> None:
    with pytest.raises(rules.RuleError) as err:
        rules.check_day([("09:00", "13:03")], day="wed")
    assert (err.value.code, err.value.field, err.value.day) == ("bad_step", "close", "wed")


def test_a_night_shift_does_not_run_into_the_next_day() -> None:
    week = {"fri": [("22:00", "03:00")], "sat": [("02:00", "08:00")]}
    with pytest.raises(rules.RuleError) as err:
        rules.check_week(week)
    assert (err.value.code, err.value.day) == ("overlap_next_day", "fri")
    # Sunday's night shift reaches Monday.
    with pytest.raises(rules.RuleError) as err:
        rules.check_week({"sun": [("23:00", "01:00")], "mon": [("00:30", "09:00")]})
    assert (err.value.code, err.value.day) == ("overlap_next_day", "sun")
    # Que empiece cuando el otro cierra, sí.
    ok = rules.check_week({"fri": [("22:00", "03:00")], "sat": [("03:00", "08:00")]})
    assert ok["fri"] == [(1320, 1620)]
    assert ok["sat"] == [(180, 480)]
    assert ok["mon"] == []


def test_a_week_only_has_its_seven_days() -> None:
    with pytest.raises(rules.RuleError) as err:
        rules.check_week({"funday": [("09:00", "10:00")]})
    assert (err.value.code, err.value.day) == ("invalid_day", "funday")


def test_the_week_rules_agree_with_the_hours_engine() -> None:
    """Lo que acepta ``rules`` lo acepta el motor del horario, y al revés."""
    days = {"mon": [("09:00", "14:00"), ("16:00", "20:00")], "sat": [("22:00", "03:00")]}
    checked = rules.check_week(days)
    week = hours.week_from_days(
        "daily", {d: [{"open": o, "close": c} for o, c in s] for d, s in days.items()}
    )
    for i, key in enumerate(hours.DAY_KEYS):
        assert [(s.open_min, s.close_min) for s in week.days[i]] == checked[key]


# ── los servicios ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("minutes", [5, 30, 45, 475, 480])
def test_a_duration_from_5_to_480_in_steps_of_5(minutes: int) -> None:
    assert rules.check_duration(minutes) == minutes
    assert rules.duration_ok(minutes)


@pytest.mark.parametrize("minutes", [0, 4, 7, 485, 500, -5])
def test_any_other_duration_is_bad_duration(minutes: int) -> None:
    assert not rules.duration_ok(minutes)
    with pytest.raises(rules.RuleError) as err:
        rules.check_duration(minutes)
    assert (err.value.code, err.value.field) == ("bad_duration", "duration_min")


def test_a_price_is_none_free_or_an_amount() -> None:
    assert rules.check_price("none", None) is None
    assert rules.check_price("free", None) is None
    # «Gratis» no guarda importe (CHECK de ``reservation_services``).
    assert rules.check_price("free", 500) is None
    assert rules.check_price("amount", 0) == 0
    assert rules.check_price("amount", 1550) == 1550
    assert rules.check_price("amount", 10**12) == 10**12


@pytest.mark.parametrize(
    ("kind", "amount", "code"),
    [
        ("gift", None, "price_invalid"),
        ("amount", None, "price_amount_required"),
        ("amount", -1, "price_invalid"),
        ("amount", 10**12 + 1, "amount_too_large"),
    ],
)
def test_a_wrong_price_says_why(kind: str, amount: int | None, code: str) -> None:
    with pytest.raises(rules.RuleError) as err:
        rules.check_price(kind, amount)
    assert (err.value.code, err.value.field) == (code, "price")


def test_a_category_takes_up_to_40_characters() -> None:
    assert rules.check_category(None) is None
    assert rules.check_category("   ") is None
    assert rules.check_category("  Corte   y  barba ") == "Corte y barba"
    assert rules.check_category("x" * 40) == "x" * 40
    with pytest.raises(rules.RuleError) as err:
        rules.check_category("x" * 41)
    assert (err.value.code, err.value.field) == ("category_too_long", "category")


def test_the_category_rule_is_the_catalog_one() -> None:
    for value in (None, "", "  Corte   y  barba ", "x" * 40):
        assert rules.check_category(value) == services_catalog.clean_category(value)


def test_a_name_from_1_to_120_characters() -> None:
    assert rules.check_name("  Corte   de pelo ") == "Corte de pelo"
    assert rules.check_name("x" * 120) == "x" * 120
    with pytest.raises(rules.RuleError) as err:
        rules.check_name("   ")
    assert (err.value.code, err.value.field) == ("name_required", "name")
    with pytest.raises(rules.RuleError) as err:
        rules.check_name("x" * 121)
    assert (err.value.code, err.value.field) == ("name_too_long", "name")


def test_a_rule_error_is_a_value_error_with_its_code() -> None:
    err = rules.RuleError("bad_step", "open", day="mon")
    assert isinstance(err, ValueError)
    assert (err.code, err.field, err.day) == ("bad_step", "open", "mon")
