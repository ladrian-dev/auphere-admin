"""Spec 043 R4 — el motor de disponibilidad, puro.

Lo usan por igual la API, las herramientas del agente y el worker: si aquí dice
que cabe, cabe en todas partes. Los casos salen del diseño («Reservas
Aforo.dc.html», ``fits``/``presIn``) y de la consola Servicios (``freeSlots``).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from nexus_api.services.reservations.engine import (
    CapacityRules,
    Occupant,
    capacity_fit,
    day_slots,
    first_fit,
    presence,
    services_slots,
)

TZ = ZoneInfo("America/Santiago")
DAY = date(2026, 10, 23)  # viernes
RESTAURANT = {
    "model": "shifts",
    "step_minutes": 30,
    "shifts": [
        {"name": "Comida", "from": "13:00", "to": "15:00"},
        {"name": "Cena", "from": "20:00", "to": "22:00"},
    ],
}
OPEN = [(time(12, 0), time(23, 30))]
RULES = CapacityRules(seats=64, hold=6, stay=timedelta(minutes=90), max_party=10)


def at(h: int, m: int = 0, d: date = DAY) -> datetime:
    return datetime.combine(d, time(h, m), tzinfo=TZ)


def occ(h: int, m: int, size: int, status: str = "confirmed", stay: int = 90) -> Occupant:
    start = at(h, m)
    return Occupant(start=start, end=start + timedelta(minutes=stay), size=size, status=status)


EARLY = at(9)  # «ahora» antes de todo


# ── franjas ─────────────────────────────────────────────────────────────────


def test_shift_slots_include_the_last_arrival() -> None:
    slots = day_slots(RESTAURANT, DAY, TZ, OPEN)
    assert [(s.at.strftime("%H:%M"), s.shift) for s in slots] == [
        ("13:00", "Comida"),
        ("13:30", "Comida"),
        ("14:00", "Comida"),
        ("14:30", "Comida"),
        ("15:00", "Comida"),
        ("20:00", "Cena"),
        ("20:30", "Cena"),
        ("21:00", "Cena"),
        ("21:30", "Cena"),
        ("22:00", "Cena"),
    ]


def test_slot_model_runs_from_a_to_b() -> None:
    bar = {"model": "slots", "step_minutes": 60, "from": "12:00", "to": "15:00"}
    slots = day_slots(bar, DAY, TZ, OPEN)
    assert [s.at.strftime("%H:%M") for s in slots] == ["12:00", "13:00", "14:00", "15:00"]
    assert all(s.shift is None for s in slots)


def test_a_closed_day_has_no_slots() -> None:
    assert day_slots(RESTAURANT, DAY, TZ, []) == []


def test_slots_outside_business_hours_are_dropped() -> None:
    lunch_only = [(time(12, 0), time(16, 0))]
    assert [s.at.strftime("%H:%M") for s in day_slots(RESTAURANT, DAY, TZ, lunch_only)] == [
        "13:00",
        "13:30",
        "14:00",
        "14:30",
        "15:00",
    ]


# ── presencia y cabida ──────────────────────────────────────────────────────


def test_presence_counts_who_is_inside() -> None:
    people = [occ(20, 0, 30), occ(21, 0, 20), occ(19, 0, 99, status="cancelled")]
    assert presence(people, at(21, 0)) == 50  # los de las 20:00 siguen dentro
    assert presence(people, at(21, 30)) == 20  # a las 21:30 los de las 20:00 salieron
    assert presence(people, at(20, 0)) == 30


def test_noshow_and_cancelled_free_the_place() -> None:
    people = [occ(20, 0, 30, status="noshow"), occ(20, 0, 10, status="cancelled")]
    assert presence(people, at(20, 30)) == 0


def test_hold_is_kept_for_walkins() -> None:
    slots = day_slots(RESTAURANT, DAY, TZ, OPEN)
    people = [occ(20, 0, 30), occ(21, 0, 20)]
    booking = capacity_fit(slots, set(), people, RULES, at(21, 0), 10, now=EARLY)
    assert booking.fits is False
    assert booking.why == "full"
    assert booking.left == 8  # 64 - 6 - 50
    walkin = capacity_fit(slots, set(), people, RULES, at(21, 0), 10, now=EARLY, walkin=True)
    assert walkin.fits is True  # 64 - 50 = 14


def test_the_whole_stay_must_fit() -> None:
    slots = day_slots(RESTAURANT, DAY, TZ, OPEN)
    # A las 20:30 hay sitio, pero a las 21:30 llega un grupo grande.
    people = [occ(21, 30, 55)]
    fit = capacity_fit(slots, set(), people, RULES, at(20, 30), 5, now=EARLY)
    assert fit.fits is False
    assert fit.left == 3  # en 21:30: 64 - 6 - 55


def test_blocked_and_past_and_closed() -> None:
    slots = day_slots(RESTAURANT, DAY, TZ, OPEN)
    blocked = {at(21, 0)}
    assert capacity_fit(slots, blocked, [], RULES, at(21, 0), 2, now=EARLY).why == "blocked"
    assert capacity_fit(slots, blocked, [], RULES, at(20, 30), 2, now=EARLY).why == "block_overlap"
    assert capacity_fit(slots, set(), [], RULES, at(13, 0), 2, now=at(14, 0)).why == "past"
    assert capacity_fit(slots, set(), [], RULES, at(17, 0), 2, now=EARLY).why == "closed"


def test_excluding_a_booking_when_moving_it() -> None:
    slots = day_slots(RESTAURANT, DAY, TZ, OPEN)
    mine = Occupant(start=at(20, 0), end=at(21, 30), size=50, status="confirmed", id="mine")
    assert capacity_fit(slots, set(), [mine], RULES, at(20, 0), 50, now=EARLY).fits is False
    assert (
        capacity_fit(slots, set(), [mine], RULES, at(20, 0), 50, now=EARLY, exclude="mine").fits
        is True
    )


def test_first_fit_finds_the_next_slot_with_room() -> None:
    slots = day_slots(RESTAURANT, DAY, TZ, OPEN)
    people = [occ(20, 0, 50)]  # dentro hasta las 21:30
    found = first_fit(slots, set(), people, RULES, 10, now=EARLY, after=at(20, 0))
    assert found is not None and found.strftime("%H:%M") == "21:30"
    assert first_fit(slots, set(), people, RULES, 60, now=EARLY, after=at(20, 0)) is None


# ── Servicios ───────────────────────────────────────────────────────────────


def _hhmm(xs: list[datetime]) -> list[str]:
    return [x.strftime("%H:%M") for x in xs]


def test_slots_fit_inside_both_the_business_and_the_person() -> None:
    lucia = [(time(9, 0), time(14, 0)), (time(15, 0), time(19, 0))]
    business = [(time(10, 0), time(19, 0))]
    got = services_slots(
        day=DAY,
        tz=TZ,
        business=business,
        staff=lucia,
        duration=timedelta(minutes=45),
        step=timedelta(minutes=30),
        busy=[],
        not_before=EARLY,
    )
    assert _hhmm(got)[:3] == ["10:00", "10:30", "11:00"]
    assert "13:00" in _hhmm(got)  # 13:00 a 13:45 cabe antes de la pausa
    assert "13:30" not in _hhmm(got)  # 13:30 a 14:15 pisa la pausa
    assert _hhmm(got)[-1] == "18:00"


def test_busy_time_is_never_offered() -> None:
    got = services_slots(
        day=DAY,
        tz=TZ,
        business=[(time(9, 0), time(12, 0))],
        staff=[(time(9, 0), time(12, 0))],
        duration=timedelta(minutes=45),
        step=timedelta(minutes=30),
        busy=[(at(10, 0), at(10, 45))],
        not_before=EARLY,
    )
    assert _hhmm(got) == ["09:00", "11:00"]


def test_nothing_before_the_notice() -> None:
    got = services_slots(
        day=DAY,
        tz=TZ,
        business=[(time(9, 0), time(12, 0))],
        staff=[(time(9, 0), time(12, 0))],
        duration=timedelta(minutes=30),
        step=timedelta(minutes=30),
        busy=[],
        not_before=at(10, 10),
    )
    assert _hhmm(got) == ["10:30", "11:00", "11:30"]


def test_closed_days_give_nothing() -> None:
    assert (
        services_slots(
            day=DAY,
            tz=TZ,
            business=[],
            staff=[(time(9, 0), time(12, 0))],
            duration=timedelta(minutes=30),
            step=timedelta(minutes=30),
            busy=[],
            not_before=EARLY,
        )
        == []
    )
