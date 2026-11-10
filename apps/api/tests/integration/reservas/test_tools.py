"""Spec 043 R6 — lo que el agente puede y no puede reservar.

Las reglas son las de la consola, más las del agente: antelación mínima y
máxima y el máximo por grupo (lo que pasa de ahí lo escala a una persona).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import customer_context, tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import ClientPushEvent, Customer, Reservation
from tests.conftest import future_day, make_reservas

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _registry() -> Any:
    from nexus_mcp import build_default_registry
    from nexus_mcp.registry import reset_default_registry

    reset_default_registry()
    return build_default_registry()


async def _world(db_session: Any, console_world: dict[str, Any], **kw: Any) -> dict[str, Any]:
    w = console_world["a"]
    shop = await make_reservas(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], **kw
    )
    ana = Customer(tenant_id=w["tenant_id"], identifier="56911110000", name="Ana", preferences={})
    db_session.add(ana)
    await db_session.commit()
    return {**shop, "ana": ana.id, "registry": _registry()}


async def _create(world: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    with tenant_context(world["tenant_id"]), customer_context(world["ana"]):
        env = await world["registry"].dispatch(
            "reservas.create", args, whitelist=["reservas.create"]
        )
    return dict(env["result"])


async def test_capacity_refuses_a_group_above_the_max(db_session, console_world) -> None:
    world = await _world(db_session, console_world, mode="capacity")
    out = await _create(
        world,
        {
            "date": future_day().isoformat(),
            "time": "13:00",
            "party_size": 14,
            "idempotency_key": "g14",
        },
    )
    assert out["refused"] == "too_large"
    assert out["booking"] is None


async def test_the_agent_respects_notice_and_horizon(db_session, console_world) -> None:
    world = await _world(db_session, console_world, mode="capacity")
    soon = datetime.now(ZoneInfo("America/Santiago")) + timedelta(minutes=20)
    near = await _create(
        world,
        {
            "date": soon.date().isoformat(),
            "time": soon.replace(minute=0 if soon.minute < 30 else 30).strftime("%H:%M"),
            "party_size": 2,
            "idempotency_key": "soon",
        },
    )
    assert near["refused"] in ("too_soon", "slot_taken")
    far = await _create(
        world,
        {
            "date": future_day(90).isoformat(),
            "time": "13:00",
            "party_size": 2,
            "idempotency_key": "far",
        },
    )
    assert far["refused"] == "too_far"


async def test_hours_missing_and_closed(db_session, console_world) -> None:
    world = await _world(db_session, console_world, hours=None)
    out = await _create(
        world,
        {
            "date": future_day().isoformat(),
            "time": "10:00",
            "service_id": str(world["corte"]),
            "idempotency_key": "x",
        },
    )
    assert out["refused"] == "hours_missing"
    with tenant_context(world["tenant_id"]), customer_context(world["ana"]):
        env = await world["registry"].dispatch(
            "reservas.find_slots",
            {"date": future_day().isoformat(), "service_id": str(world["corte"])},
            whitelist=["reservas.find_slots"],
        )
    assert env["result"]["closed"] is True
    assert env["result"]["why_closed"] == "hours_missing"


async def test_a_booking_is_pending_idempotent_and_tells_the_business(
    db_session, console_world
) -> None:
    world = await _world(db_session, console_world)
    args = {
        "date": future_day().isoformat(),
        "time": "10:00",
        "service_id": str(world["corte"]),
        "idempotency_key": "conv:1:reserva",
        "note": "Prefiere a Lucía",
    }
    first = await _create(world, args)
    again = await _create(world, args)
    assert first["booking"]["status"] == "pending"  # pide confirmación por defecto
    assert again["idempotent_replay"] is True
    assert again["booking"]["id"] == first["booking"]["id"]
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, world["tenant_id"]):
        rows = (await session.execute(sa.select(Reservation))).scalars().all()
        assert len(rows) == 1
        r = rows[0]
        assert (r.origin, r.channel, r.created_by_kind) == ("agent", "whatsapp", "agent")
        assert r.customer_id == world["ana"]
        assert r.contact_phone == "+56911110000"
        assert r.note == "Prefiere a Lucía"
        pushes = (
            (
                await session.execute(
                    sa.select(ClientPushEvent).where(
                        ClientPushEvent.kind == "reservas.agent_change"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert [p.reservation_id for p in pushes] == [r.id]


async def test_find_slots_only_offers_real_times(db_session, console_world) -> None:
    world = await _world(db_session, console_world)
    day = future_day()
    await _create(
        world,
        {
            "date": day.isoformat(),
            "time": "10:00",
            "service_id": str(world["corte"]),
            "staff_id": str(world["lucia"]),
            "idempotency_key": "a",
        },
    )
    with tenant_context(world["tenant_id"]), customer_context(world["ana"]):
        env = await world["registry"].dispatch(
            "reservas.find_slots",
            {
                "date": day.isoformat(),
                "service_id": str(world["corte"]),
                "staff_id": str(world["lucia"]),
            },
            whitelist=["reservas.find_slots"],
        )
    times = [s["time"] for s in env["result"]["slots"]]
    assert "10:00" not in times and "10:30" in times
    assert "14:00" not in times  # la pausa de Lucía
