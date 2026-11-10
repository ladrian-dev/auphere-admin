"""Spec 043 R1.3 y R2 — los valores de partida y lo que el negocio puede cambiar."""

from __future__ import annotations

import pytest

from nexus_api.db.models import ReservationSettings
from nexus_api.services.reservations.settings import (
    SettingsError,
    apply_defaults,
    apply_patch,
    validate_schedule,
)


def _row(mode: str = "capacity", kind: str | None = "restaurant") -> ReservationSettings:
    row = ReservationSettings()
    apply_defaults(row, mode, kind)
    return row


def test_restaurant_starts_like_the_design() -> None:
    row = _row()
    assert (row.seats, row.stay_minutes, row.max_party, row.walkin_hold) == (64, 90, 10, 6)
    assert row.release_unconfirmed is True
    assert row.schedule is not None and row.schedule["model"] == "shifts"
    assert [s["name"] for s in row.schedule["shifts"]] == ["Comida", "Cena"]


@pytest.mark.parametrize(
    ("kind", "seats", "hold"),
    [("bar", 80, 16), ("classes", 20, 2), ("tours", 16, 0), ("rooms", 120, 0), ("spa", 14, 2)],
)
def test_every_kind_has_its_numbers(kind: str, seats: int, hold: int) -> None:
    row = _row(kind=kind)
    assert (row.seats, row.walkin_hold) == (seats, hold)


def test_services_has_no_capacity() -> None:
    row = _row("services", None)
    assert row.seats is None and row.schedule is None
    assert row.release_unconfirmed is False
    assert row.reminder_enabled is True and row.confirm_enabled is True


def test_capacity_needs_a_kind() -> None:
    with pytest.raises(SettingsError):
        _row("capacity", None)


def test_the_business_cannot_change_the_mode() -> None:
    with pytest.raises(SettingsError) as err:
        apply_patch(_row(), {"mode": "services"})
    assert err.value.field == "mode"


@pytest.mark.parametrize(
    ("patch", "field"),
    [
        ({"waitlist": {"lead_minutes": 90}}, "waitlist.lead_minutes"),
        ({"capacity": {"seats": 0}}, "capacity.seats"),
        ({"capacity": {"walkin_hold": 40}}, "capacity.walkin_hold"),
        ({"capacity": {"max_party": 70}}, "capacity.max_party"),
        ({"capacity": {"stay_minutes": 100}}, "capacity.stay_minutes"),
        ({"confirmation": {"when": "1h"}}, "confirmation.when"),
    ],
)
def test_out_of_range_names_the_field(patch: dict, field: str) -> None:
    with pytest.raises(SettingsError) as err:
        apply_patch(_row(), patch)
    assert err.value.field == field


def test_services_only_confirm_a_day_before() -> None:
    with pytest.raises(SettingsError):
        apply_patch(_row("services", None), {"confirmation": {"when": "3h"}})
    with pytest.raises(SettingsError):
        apply_patch(_row("services", None), {"release_unconfirmed": True})


def test_schedule_validation() -> None:
    ok = validate_schedule(
        {
            "model": "shifts",
            "step_minutes": 30,
            "shifts": [{"name": "Cena", "from": "20:00", "to": "22:00"}],
        }
    )
    assert ok["shifts"][0]["to"] == "22:00"
    with pytest.raises(SettingsError):  # el paso no divide el turno
        validate_schedule(
            {
                "model": "shifts",
                "step_minutes": 60,
                "shifts": [{"name": "C", "from": "20:00", "to": "21:30"}],
            }
        )
    with pytest.raises(SettingsError):  # se pisan
        validate_schedule(
            {
                "model": "shifts",
                "step_minutes": 30,
                "shifts": [
                    {"name": "A", "from": "13:00", "to": "15:00"},
                    {"name": "B", "from": "14:30", "to": "16:00"},
                ],
            }
        )
    assert validate_schedule({"model": "slots", "step_minutes": 60, "from": "12:00", "to": "23:00"})


def test_a_valid_patch_applies() -> None:
    row = _row()
    apply_patch(
        row,
        {
            "waitlist": {"enabled": False, "lead_minutes": 240},
            "confirmation": {"when": "same_day_12"},
            "capacity": {"seats": 70, "walkin_hold": 8},
        },
    )
    assert (row.waitlist_enabled, row.waitlist_lead_minutes) == (False, 240)
    assert row.confirm_when == "same_day_12"
    assert (row.seats, row.walkin_hold, row.stay_minutes) == (70, 8, 90)
