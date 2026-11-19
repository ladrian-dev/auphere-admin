"""Spec 064, requisito 2 — una «Atendida» se puede corregir durante 7 días.

Lo que el sistema cierra solo como ``done`` deja de ser definitivo: en
Servicios, el negocio puede marcar «No vino» y volver atrás mientras no pasen
7 días desde la hora de fin. En Aforo no: allí ``done`` solo llega después de
que alguien marcara «Llegó».
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from nexus_api.db.models import Reservation, ReservationSettings
from nexus_api.services.reservations.core import CORRECTION_WINDOW, Ctx, allowed_actions
from nexus_api.services.reservations.settings import apply_defaults

NOW = datetime(2026, 11, 18, 15, 0, tzinfo=UTC)


def _ctx(mode: str = "services") -> Ctx:
    settings = ReservationSettings()
    apply_defaults(settings, mode, "restaurant" if mode == "capacity" else None)
    return Ctx(
        tenant_id=uuid.uuid4(),
        settings=settings,
        tz=ZoneInfo("America/Santiago"),
        hours=None,
        currency="CLP",
        business_name="Salón",
    )


def _res(
    status: str, *, ended_ago: timedelta, mode: str = "services", origin: str = "person"
) -> Reservation:
    ends = NOW - ended_ago
    return Reservation(
        id=uuid.uuid4(),
        mode=mode,
        status=status,
        origin=origin,
        starts_at=ends - timedelta(minutes=30),
        ends_at=ends,
        contact_phone="+56911112222",
    )


def test_the_window_is_seven_days() -> None:
    assert timedelta(days=7) == CORRECTION_WINDOW


@pytest.mark.parametrize(
    ("ended_ago", "offered"),
    [
        (timedelta(hours=1), True),
        (timedelta(days=1), True),
        (timedelta(days=7) - timedelta(minutes=1), True),
        (timedelta(days=7) + timedelta(minutes=1), False),
        (timedelta(days=30), False),
    ],
)
def test_a_closed_booking_can_be_marked_noshow_for_seven_days(
    ended_ago: timedelta, offered: bool
) -> None:
    allowed = allowed_actions(_ctx(), _res("done", ended_ago=ended_ago), NOW)
    assert ("noshow" in allowed) is offered
    assert "undo" not in allowed


@pytest.mark.parametrize(
    ("ended_ago", "offered"),
    [(timedelta(days=1), True), (timedelta(days=6), True), (timedelta(days=8), False)],
)
def test_a_late_noshow_can_be_undone_for_seven_days(ended_ago: timedelta, offered: bool) -> None:
    allowed = allowed_actions(_ctx(), _res("noshow", ended_ago=ended_ago), NOW)
    assert ("undo" in allowed) is offered


def test_capacity_closed_bookings_are_not_corrected() -> None:
    ctx = _ctx("capacity")
    assert (
        allowed_actions(ctx, _res("done", ended_ago=timedelta(hours=1), mode="capacity"), NOW) == []
    )
    walkin = _res("done", ended_ago=timedelta(hours=1), mode="capacity", origin="walkin")
    assert allowed_actions(ctx, walkin, NOW) == []


def test_a_cancelled_booking_offers_nothing() -> None:
    assert allowed_actions(_ctx(), _res("cancelled", ended_ago=timedelta(hours=1)), NOW) == []


def test_today_keeps_working_as_before() -> None:
    ctx = _ctx()
    # Abierta, hoy y ya empezada: «No vino», como siempre.
    started = Reservation(
        id=uuid.uuid4(),
        mode="services",
        status="confirmed",
        origin="person",
        starts_at=NOW - timedelta(minutes=10),
        ends_at=NOW + timedelta(minutes=20),
    )
    assert "noshow" in allowed_actions(ctx, started, NOW)
    # «No vino» de hoy, antes de su hora de fin: «Deshacer», como siempre.
    early = Reservation(
        id=uuid.uuid4(),
        mode="services",
        status="noshow",
        origin="person",
        starts_at=NOW - timedelta(minutes=10),
        ends_at=NOW + timedelta(minutes=20),
    )
    assert "undo" in allowed_actions(ctx, early, NOW)
