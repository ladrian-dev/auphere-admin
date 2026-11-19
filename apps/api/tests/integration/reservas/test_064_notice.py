"""Spec 064, requisito 1 — la antelación del agente la decide el negocio.

El reloj va fijado a las 13:09 de un día futuro en Santiago. Con una hora de
antelación, el agente no puede dar nada antes de las 14:09: lo libre de ahí
para atrás sale en ``too_soon``, no desaparece. Una persona del negocio reserva
cualquier hora futura.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from nexus_api.core.tenant_context import customer_context, tenant_context
from nexus_api.db.models import Customer, ReservationSettings
from tests.conftest import future_day, make_reservas

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BASE = "/console/lite/reservas"
TZ = ZoneInfo("America/Santiago")


def _registry() -> Any:
    from nexus_mcp import build_default_registry
    from nexus_mcp.registry import reset_default_registry

    reset_default_registry()
    return build_default_registry()


@pytest.fixture
def at_1309(monkeypatch: pytest.MonkeyPatch) -> datetime:
    """Las 13:09 locales de un día futuro, para la herramienta y para la API."""
    now = datetime.combine(future_day(), time(13, 9), tzinfo=TZ)
    monkeypatch.setattr("nexus_mcp.servers.reservas.tools._now", lambda: now)
    monkeypatch.setattr("nexus_api.api.console.lite.reservas._now", lambda: now)
    return now


async def _world(
    db_session: Any, console_world: dict[str, Any], *, notice: int, **kw: Any
) -> dict[str, Any]:
    w = console_world["a"]
    shop = await make_reservas(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], **kw
    )
    settings = await db_session.get(ReservationSettings, w["tenant_id"])
    settings.agent_min_notice_minutes = notice
    ana = Customer(tenant_id=w["tenant_id"], identifier="56911110000", name="Ana", preferences={})
    db_session.add(ana)
    await db_session.commit()
    return {**shop, "ana": ana.id, "registry": _registry()}


async def _tool(world: dict[str, Any], name: str, args: dict[str, Any]) -> dict[str, Any]:
    with tenant_context(world["tenant_id"]), customer_context(world["ana"]):
        env = await world["registry"].dispatch(name, args, whitelist=[name])
    return dict(env["result"])


async def test_what_the_notice_leaves_out_is_said_apart(db_session, console_world, at_1309) -> None:
    world = await _world(db_session, console_world, notice=60)
    out = await _tool(
        world,
        "reservas.find_slots",
        {"date": at_1309.date().isoformat(), "service_id": str(world["corte"])},
    )
    times = [s["time"] for s in out["slots"]]
    assert out["too_soon"] == ["13:30", "14:00"]
    assert times[0] == "14:30"
    assert not set(times) & set(out["too_soon"])
    # Lo que ya empezó no sale en ninguna de las dos.
    assert "13:00" not in times and "13:00" not in out["too_soon"]


async def test_without_notice_the_next_time_is_offered(db_session, console_world, at_1309) -> None:
    world = await _world(db_session, console_world, notice=0)
    out = await _tool(
        world,
        "reservas.find_slots",
        {"date": at_1309.date().isoformat(), "service_id": str(world["corte"])},
    )
    assert out["too_soon"] == []
    assert out["slots"][0]["time"] == "13:30"


async def test_another_day_has_nothing_too_soon(db_session, console_world, at_1309) -> None:
    world = await _world(db_session, console_world, notice=60)
    out = await _tool(
        world,
        "reservas.find_slots",
        {"date": future_day(5).isoformat(), "service_id": str(world["corte"])},
    )
    assert out["too_soon"] == []
    assert out["slots"]


async def test_capacity_says_it_too(db_session, console_world, at_1309) -> None:
    world = await _world(db_session, console_world, notice=60, mode="capacity")
    out = await _tool(
        world, "reservas.find_slots", {"date": at_1309.date().isoformat(), "party_size": 2}
    )
    times = [s["time"] for s in out["slots"]]
    assert out["too_soon"] == ["13:30", "14:00"]
    assert times[0] == "14:30"
    assert all(s["left"] is not None for s in out["slots"])


async def test_the_agent_cannot_book_inside_the_notice(db_session, console_world, at_1309) -> None:
    world = await _world(db_session, console_world, notice=60)
    out = await _tool(
        world,
        "reservas.create",
        {
            "date": at_1309.date().isoformat(),
            "time": "13:30",
            "service_id": str(world["corte"]),
            "idempotency_key": "pronto",
        },
    )
    assert out["refused"] == "too_soon"
    assert out["booking"] is None


async def test_the_agent_books_the_next_time_without_notice(
    db_session, console_world, at_1309
) -> None:
    world = await _world(db_session, console_world, notice=0)
    out = await _tool(
        world,
        "reservas.create",
        {
            "date": at_1309.date().isoformat(),
            "time": "13:30",
            "service_id": str(world["corte"]),
            "idempotency_key": "ya",
        },
    )
    assert out["refused"] is None, out
    assert out["booking"] is not None


async def test_a_person_is_not_held_by_the_notice(
    client, db_session, console_world, at_1309
) -> None:
    world = await _world(db_session, console_world, notice=60)
    r = await client.post(
        f"{BASE}/bookings",
        headers=world["headers"](),
        json={
            "date": at_1309.date().isoformat(),
            "time": "13:30",
            "staff_id": str(world["lucia"]),
            "service_id": str(world["corte"]),
            "contact": {"name": "Ana Pérez", "phone": "+56911112222"},
        },
    )
    assert r.status_code == 201, r.text


async def test_the_api_takes_only_the_seven_values(client, db_session, console_world) -> None:
    world = await _world(db_session, console_world, notice=60)
    h = world["headers"]
    bad = await client.patch(
        f"{BASE}/settings", headers=h(), json={"agent": {"min_notice_minutes": 45}}
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["detail"]["field"] == "agent.min_notice_minutes"
    ok = await client.patch(
        f"{BASE}/settings", headers=h(), json={"agent": {"min_notice_minutes": 0}}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["agent"]["min_notice_minutes"] == 0
