"""Ajustes de Reservas — spec 043 (Requisitos 1.3 y 2).

Los valores de partida por modo y, en Aforo, por tipo de negocio (la tabla del
diseño, ``data-model.md``), y la validación de lo que el negocio cambia. Puro.
"""

from __future__ import annotations

from datetime import time
from itertools import pairwise
from typing import Any, Final

from nexus_api.db.models.reservation import CAPACITY_KINDS, CONFIRM_WHEN, ReservationSettings


class SettingsError(ValueError):
    """Un ajuste fuera de rango: la API responde 422 con el campo."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


LEAD_MINUTES: Final = (60, 120, 240, 1440)
SLOT_STEPS: Final = (15, 30, 60)
SCHEDULE_STEPS: Final = (15, 30, 60, 90, 120)

KIND_DEFAULTS: Final[dict[str, dict[str, Any]]] = {
    "restaurant": {
        "seats": 64,
        "stay_minutes": 90,
        "max_party": 10,
        "walkin_hold": 6,
        "schedule": {
            "model": "shifts",
            "step_minutes": 30,
            "shifts": [
                {"name": "Comida", "from": "13:00", "to": "15:00"},
                {"name": "Cena", "from": "20:00", "to": "22:00"},
            ],
        },
    },
    "bar": {
        "seats": 80,
        "stay_minutes": 120,
        "max_party": 12,
        "walkin_hold": 16,
        "schedule": {"model": "slots", "step_minutes": 60, "from": "12:00", "to": "23:00"},
    },
    "classes": {
        "seats": 20,
        "stay_minutes": 60,
        "max_party": 2,
        "walkin_hold": 2,
        "schedule": {
            "model": "shifts",
            "step_minutes": 60,
            "shifts": [
                {"name": "Mañana", "from": "07:00", "to": "10:00"},
                {"name": "Tarde", "from": "17:00", "to": "21:00"},
            ],
        },
    },
    "tours": {
        "seats": 16,
        "stay_minutes": 120,
        "max_party": 8,
        "walkin_hold": 0,
        "schedule": {"model": "slots", "step_minutes": 120, "from": "10:00", "to": "18:00"},
    },
    "rooms": {
        "seats": 120,
        "stay_minutes": 120,
        "max_party": 40,
        "walkin_hold": 0,
        "schedule": {"model": "slots", "step_minutes": 120, "from": "10:00", "to": "22:00"},
    },
    "spa": {
        "seats": 14,
        "stay_minutes": 90,
        "max_party": 4,
        "walkin_hold": 2,
        "schedule": {"model": "slots", "step_minutes": 60, "from": "10:00", "to": "21:00"},
    },
}


def apply_defaults(row: ReservationSettings, mode: str, capacity_kind: str | None) -> None:
    """La primera activación: los valores de partida del modo y del tipo."""
    row.mode = mode
    row.capacity_kind = capacity_kind if mode == "capacity" else None
    row.slot_step_minutes = 30
    row.waitlist_enabled = True
    row.waitlist_lead_minutes = 120
    row.agent_min_notice_minutes = 60
    row.agent_max_days_ahead = 60
    row.reminder_enabled = True
    row.confirm_enabled = True
    row.confirm_when = "24h"
    if mode == "capacity":
        if capacity_kind not in CAPACITY_KINDS:
            raise SettingsError("capacity_kind", "required with capacity")
        d = KIND_DEFAULTS[capacity_kind]
        row.release_unconfirmed = True
        row.seats = d["seats"]
        row.stay_minutes = d["stay_minutes"]
        row.max_party = d["max_party"]
        row.walkin_hold = d["walkin_hold"]
        row.schedule = dict(d["schedule"])
    else:
        row.release_unconfirmed = False
        row.seats = row.stay_minutes = row.max_party = row.walkin_hold = None
        row.schedule = None


def _hhmm(field: str, raw: Any) -> time:
    try:
        h, m = str(raw).split(":")
        return time(int(h), int(m))
    except (ValueError, TypeError) as exc:
        raise SettingsError(field, "expected HH:MM") from exc


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def validate_schedule(raw: Any) -> dict[str, Any]:
    """Turnos o franjas: ``from``/``to`` son la primera y la última llegada; el
    paso divide cada tramo; los turnos no se pisan."""
    if not isinstance(raw, dict):
        raise SettingsError("capacity.schedule", "expected an object")
    step = raw.get("step_minutes")
    if step not in SCHEDULE_STEPS:
        raise SettingsError("capacity.schedule.step_minutes", f"one of {SCHEDULE_STEPS}")
    model = raw.get("model")
    if model == "slots":
        a = _hhmm("capacity.schedule.from", raw.get("from"))
        b = _hhmm("capacity.schedule.to", raw.get("to"))
        if b < a or (_minutes(b) - _minutes(a)) % int(step) != 0:
            raise SettingsError("capacity.schedule", "to must follow from by whole steps")
        return {"model": "slots", "step_minutes": step, "from": raw["from"], "to": raw["to"]}
    if model != "shifts":
        raise SettingsError("capacity.schedule.model", "shifts or slots")
    shifts = raw.get("shifts")
    if not isinstance(shifts, list) or not 1 <= len(shifts) <= 6:
        raise SettingsError("capacity.schedule.shifts", "between 1 and 6 shifts")
    clean: list[dict[str, str]] = []
    spans: list[tuple[int, int]] = []
    for i, s in enumerate(shifts):
        if not isinstance(s, dict):
            raise SettingsError(f"capacity.schedule.shifts[{i}]", "expected an object")
        name = str(s.get("name") or "").strip()
        if not 1 <= len(name) <= 40:
            raise SettingsError(f"capacity.schedule.shifts[{i}].name", "1 to 40 characters")
        a = _hhmm(f"capacity.schedule.shifts[{i}].from", s.get("from"))
        b = _hhmm(f"capacity.schedule.shifts[{i}].to", s.get("to"))
        if b < a or (_minutes(b) - _minutes(a)) % int(step) != 0:
            raise SettingsError(f"capacity.schedule.shifts[{i}]", "to must follow from by steps")
        spans.append((_minutes(a), _minutes(b)))
        clean.append({"name": name, "from": a.strftime("%H:%M"), "to": b.strftime("%H:%M")})
    ordered = sorted(spans)
    for (_a0, a1), (b0, _b1) in pairwise(ordered):
        if b0 <= a1:
            raise SettingsError("capacity.schedule.shifts", "shifts overlap")
    return {"model": "shifts", "step_minutes": step, "shifts": clean}


def apply_patch(row: ReservationSettings, patch: dict[str, Any]) -> None:
    """Lo que el negocio cambia. ``mode`` y ``capacity_kind`` no: son del admin."""
    if "mode" in patch or "capacity_kind" in patch:
        raise SettingsError("mode", "the mode is chosen by Auphere")
    if "waitlist" in patch:
        w = patch["waitlist"] or {}
        if "enabled" in w:
            row.waitlist_enabled = bool(w["enabled"])
        if "lead_minutes" in w:
            if w["lead_minutes"] not in LEAD_MINUTES:
                raise SettingsError("waitlist.lead_minutes", f"one of {LEAD_MINUTES}")
            row.waitlist_lead_minutes = int(w["lead_minutes"])
    if "agent" in patch:
        a = patch["agent"] or {}
        if "min_notice_minutes" in a:
            v = int(a["min_notice_minutes"])
            if not 0 <= v <= 1440:
                raise SettingsError("agent.min_notice_minutes", "0 to 1440")
            row.agent_min_notice_minutes = v
        if "max_days_ahead" in a:
            v = int(a["max_days_ahead"])
            if not 1 <= v <= 365:
                raise SettingsError("agent.max_days_ahead", "1 to 365")
            row.agent_max_days_ahead = v
    if "confirmation" in patch:
        c = patch["confirmation"] or {}
        if "enabled" in c:
            row.confirm_enabled = bool(c["enabled"])
        if "when" in c:
            if c["when"] not in CONFIRM_WHEN:
                raise SettingsError("confirmation.when", f"one of {CONFIRM_WHEN}")
            if row.mode == "services" and c["when"] != "24h":
                raise SettingsError("confirmation.when", "services confirm 24h before")
            row.confirm_when = str(c["when"])
    if "reminder_enabled" in patch:
        row.reminder_enabled = bool(patch["reminder_enabled"])
    if "release_unconfirmed" in patch:
        if row.mode != "capacity" and patch["release_unconfirmed"]:
            raise SettingsError("release_unconfirmed", "only in capacity mode")
        row.release_unconfirmed = bool(patch["release_unconfirmed"])
    if "slot_step_minutes" in patch:
        if patch["slot_step_minutes"] not in SLOT_STEPS:
            raise SettingsError("slot_step_minutes", f"one of {SLOT_STEPS}")
        row.slot_step_minutes = int(patch["slot_step_minutes"])
    if "capacity" in patch and patch["capacity"] is not None:
        if row.mode != "capacity":
            raise SettingsError("capacity", "only in capacity mode")
        _apply_capacity(row, patch["capacity"])


def _apply_capacity(row: ReservationSettings, c: dict[str, Any]) -> None:
    seats = int(c.get("seats", row.seats or 0))
    stay = int(c.get("stay_minutes", row.stay_minutes or 0))
    max_party = int(c.get("max_party", row.max_party or 0))
    hold = int(c.get("walkin_hold", row.walkin_hold or 0))
    if seats < 1:
        raise SettingsError("capacity.seats", "at least 1")
    if not 30 <= stay <= 480 or stay % 15:
        raise SettingsError("capacity.stay_minutes", "30 to 480, in 15-minute steps")
    if not 1 <= max_party <= seats:
        raise SettingsError("capacity.max_party", "1 to seats")
    if not 0 <= hold <= seats // 2:
        raise SettingsError("capacity.walkin_hold", "0 to half the seats")
    row.seats, row.stay_minutes, row.max_party, row.walkin_hold = seats, stay, max_party, hold
    if "schedule" in c:
        row.schedule = validate_schedule(c["schedule"])


__all__ = [
    "KIND_DEFAULTS",
    "LEAD_MINUTES",
    "SettingsError",
    "apply_defaults",
    "apply_patch",
    "validate_schedule",
]
