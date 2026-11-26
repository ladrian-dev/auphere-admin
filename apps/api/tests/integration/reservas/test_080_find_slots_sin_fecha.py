"""Spec 080, requisito 3 — buscar disponibilidad sin fecha.

Lo que lo trajo (Jemma, 23-nov): el cliente no dijo día y el agente buscó
«mañana» directamente, a las 13:24, con huecos esa misma tarde. Sin fecha, la
herramienta devuelve lo primero libre desde ahora, cruzando días, con la fecha y
el día de la semana de cada horario: el modelo ya no adivina el día.

El reloj va fijado como en ``test_064_notice.py``. Santiago; Lucía con pausa de
14 a 15, Marcos sin pausa; el negocio abre de 9 a 21 (``make_reservas``).
"""

from __future__ import annotations

import time as clock
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from nexus_api.core.tenant_context import customer_context, tenant_context
from nexus_api.db.models import Customer, ReservationService, ReservationSettings
from tests.conftest import OPEN_EVERY_DAY, future_day, make_reservas

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

TZ = ZoneInfo("America/Santiago")
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _registry() -> Any:
    from nexus_mcp import build_default_registry
    from nexus_mcp.registry import reset_default_registry

    reset_default_registry()
    return build_default_registry()


def _clock(monkeypatch: pytest.MonkeyPatch, day: date, at: time) -> datetime:
    now = datetime.combine(day, at, tzinfo=TZ)
    monkeypatch.setattr("nexus_mcp.servers.reservas.tools._now", lambda: now)
    return now


async def _world(
    db_session: Any, console_world: dict[str, Any], *, notice: int = 0, ahead: int = 60, **kw: Any
) -> dict[str, Any]:
    w = console_world["a"]
    shop = await make_reservas(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], **kw
    )
    settings = await db_session.get(ReservationSettings, w["tenant_id"])
    settings.agent_min_notice_minutes = notice
    settings.agent_max_days_ahead = ahead
    ana = Customer(tenant_id=w["tenant_id"], identifier="56911110000", name="Ana", preferences={})
    db_session.add(ana)
    await db_session.commit()
    return {**shop, "ana": ana.id, "registry": _registry()}


async def _find(world: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    with tenant_context(world["tenant_id"]), customer_context(world["ana"]):
        env = await world["registry"].dispatch(
            "reservas.find_slots", args, whitelist=["reservas.find_slots"]
        )
    assert env["status"] == "ok", env
    return dict(env["result"])


def _when(slot: dict[str, Any]) -> tuple[str, str]:
    return slot["date"], slot["time"]


async def test_without_a_date_the_first_time_is_today(
    db_session, console_world, monkeypatch
) -> None:
    day = future_day()
    _clock(monkeypatch, day, time(13, 24))
    world = await _world(db_session, console_world)

    out = await _find(world, {"service_id": str(world["corte"])})

    assert out["date"] is None and out["closed"] is False
    assert out["searched_from"] == day.isoformat()
    slots = out["slots"]
    assert 1 <= len(slots) <= 6
    assert _when(slots[0]) == (day.isoformat(), "13:30"), slots[0]
    assert slots[0]["weekday"] == WEEKDAYS[day.weekday()]
    assert [_when(s) for s in slots] == sorted(_when(s) for s in slots), "en orden"
    assert {s["date"] for s in slots} == {day.isoformat()}, "hoy tiene de sobra"


async def test_with_nothing_left_today_it_goes_on_to_the_next_open_day(
    db_session, console_world, monkeypatch
) -> None:
    day = future_day()
    tomorrow, after = day + timedelta(days=1), day + timedelta(days=2)
    hours = {d: v for d, v in OPEN_EVERY_DAY.items() if d != WEEKDAYS[tomorrow.weekday()]}
    _clock(monkeypatch, day, time(22, 0))  # el negocio cerró a las 21
    world = await _world(db_session, console_world, hours=hours)

    out = await _find(world, {"service_id": str(world["corte"])})

    assert out["slots"], out
    assert _when(out["slots"][0]) == (after.isoformat(), "09:00"), "salta el día cerrado"
    assert out["slots"][0]["weekday"] == WEEKDAYS[after.weekday()]


async def test_at_most_six_and_only_the_person_asked_for(
    db_session, console_world, monkeypatch
) -> None:
    day = future_day()
    _clock(monkeypatch, day, time(9, 0))
    world = await _world(db_session, console_world)

    out = await _find(world, {"service_id": str(world["corte"]), "staff_id": str(world["lucia"])})

    assert len(out["slots"]) == 6
    assert all([p["name"] for p in s["staff"]] == ["Lucía"] for s in out["slots"])


async def test_the_notice_still_holds_and_says_the_day(
    db_session, console_world, monkeypatch
) -> None:
    day = future_day()
    _clock(monkeypatch, day, time(13, 24))
    world = await _world(db_session, console_world, notice=60)

    out = await _find(world, {"service_id": str(world["corte"])})

    assert _when(out["slots"][0]) == (day.isoformat(), "14:30"), out["slots"][0]
    assert f"{day.isoformat()} 13:30" in out["too_soon"]
    assert f"{day.isoformat()} 14:00" in out["too_soon"]


async def test_nothing_in_the_window_is_said_not_invented(
    db_session, console_world, monkeypatch
) -> None:
    day = future_day()
    _clock(monkeypatch, day, time(22, 0))
    world = await _world(db_session, console_world, ahead=0)

    out = await _find(world, {"service_id": str(world["corte"])})

    assert out["slots"] == []
    assert out["closed"] is False
    assert out["why_closed"] == "none_in_window"


async def test_an_unknown_service_is_refused_like_with_a_date(
    db_session, console_world, monkeypatch
) -> None:
    _clock(monkeypatch, future_day(), time(10, 0))
    world = await _world(db_session, console_world)

    out = await _find(world, {"service_name": "masaje tailandés"})

    assert out["refused"] == "unknown_service"
    assert out["slots"] == []


async def test_capacity_without_a_date_brings_the_places_left(
    db_session, console_world, monkeypatch
) -> None:
    day = future_day()
    _clock(monkeypatch, day, time(19, 10))
    world = await _world(db_session, console_world, mode="capacity")

    out = await _find(world, {"party_size": 2})

    assert out["slots"], out
    assert _when(out["slots"][0]) == (day.isoformat(), "19:30")
    assert all(s["left"] is not None for s in out["slots"])
    assert len(out["slots"]) == 6 and out["slots"][-1]["date"] != day.isoformat()


async def test_with_a_date_nothing_changes(db_session, console_world, monkeypatch) -> None:
    day = future_day()
    _clock(monkeypatch, day, time(9, 0))
    world = await _world(db_session, console_world)

    out = await _find(world, {"date": day.isoformat(), "service_id": str(world["corte"])})

    assert out["date"] == day.isoformat()
    assert "searched_from" not in out and "searched_to" not in out
    assert all(set(s) == {"time", "staff", "left"} for s in out["slots"]), out["slots"][0]


async def test_the_worst_case_scans_the_whole_window_fast(
    db_session, console_world, monkeypatch
) -> None:
    """Nada cabe en ningún día: un servicio de 8 h con Lucía, cuyos tramos son de
    5 y 6 h. Recorre los 60 días con lecturas de verdad. Plan: menos de 1,5 s."""
    day = future_day()
    _clock(monkeypatch, day, time(9, 0))
    world = await _world(db_session, console_world)
    long = ReservationService(
        tenant_id=world["tenant_id"],
        name="Maratón",
        duration_minutes=480,
        price_minor=1,
        currency="CLP",
    )
    db_session.add(long)
    await db_session.commit()

    started = clock.perf_counter()
    out = await _find(world, {"service_id": str(long.id), "staff_id": str(world["lucia"])})
    took = clock.perf_counter() - started

    assert out["why_closed"] == "none_in_window"
    assert out["searched_to"] == (day + timedelta(days=60)).isoformat()
    assert took < 1.5, f"{took:.2f} s"
