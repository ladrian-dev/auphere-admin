"""Spec 043 CE-001 — dos a la vez no se quedan la misma hora.

Hoy ``booking.create_appointment`` no revalida: dos turnos simultáneos pueden
reservar la misma hora. Aquí, peticiones lanzadas a la vez contra el mismo
hueco (por la API y por la herramienta del agente) dejan **una** reserva en
Servicios y **nunca** pasan del aforo en Aforo. El candado de transacción y la
revalidación son la garantía (no hay ``EXCLUDE`` en la base).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import customer_context, tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Customer, Reservation
from tests.conftest import future_day, make_reservas

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BASE = "/console/lite/reservas"
N = 6


async def _live(tenant_id: uuid.UUID) -> list[Reservation]:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        rows = await session.execute(
            sa.select(Reservation).where(Reservation.status.in_(("pending", "confirmed")))
        )
        return list(rows.scalars())


async def test_services_api_race_leaves_one_booking(client, db_session, console_world) -> None:
    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    day = future_day()

    async def attempt(i: int) -> int:
        r = await client.post(
            f"{BASE}/bookings",
            headers=shop["headers"](),
            json={
                "date": day.isoformat(),
                "time": "10:00",
                "staff_id": str(shop["lucia"]),
                "service_id": str(shop["color"]),
                "contact": {"name": f"Cliente {i}", "phone": None},
            },
        )
        return r.status_code

    codes = await asyncio.gather(*(attempt(i) for i in range(N)))
    assert sorted(codes) == [201] + [409] * (N - 1)
    assert len(await _live(w["tenant_id"])) == 1


async def test_capacity_api_race_never_overbooks(client, db_session, console_world) -> None:
    w = console_world["a"]
    resto = await make_reservas(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], mode="capacity"
    )
    day = future_day()

    async def attempt(i: int) -> int:
        r = await client.post(
            f"{BASE}/bookings",
            headers=resto["headers"](),
            json={
                "date": day.isoformat(),
                "time": "13:00",
                "party_size": 20,
                "contact": {"name": f"Grupo {i}", "phone": None},
            },
        )
        return r.status_code

    codes = await asyncio.gather(*(attempt(i) for i in range(N)))
    # Aforo 64 - 6 guardadas = 58: caben dos grupos de 20, nunca tres.
    assert codes.count(201) == 2
    assert sum(r.party_size for r in await _live(w["tenant_id"])) == 40


async def test_agent_race_through_the_tool_leaves_one_booking(db_session, console_world) -> None:
    from nexus_mcp import build_default_registry
    from nexus_mcp.registry import reset_default_registry

    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    customers: list[uuid.UUID] = []
    for i in range(N):
        c = Customer(tenant_id=w["tenant_id"], identifier=f"5691000{i:04d}", preferences={})
        db_session.add(c)
        await db_session.flush()
        customers.append(c.id)
    await db_session.commit()
    reset_default_registry()
    registry = build_default_registry()
    day = future_day()

    async def attempt(customer_id: uuid.UUID) -> dict[str, Any]:
        with tenant_context(w["tenant_id"]), customer_context(customer_id):
            env = await registry.dispatch(
                "reservas.create",
                {
                    "date": day.isoformat(),
                    "time": "16:00",
                    "service_id": str(shop["color"]),
                    "staff_id": str(shop["marcos"]),
                    "idempotency_key": f"race:{customer_id}",
                },
                whitelist=["reservas.create"],
            )
        return dict(env["result"])

    results = await asyncio.gather(*(attempt(c) for c in customers))
    booked = [r for r in results if r.get("booking")]
    refused = [r for r in results if r.get("refused")]
    assert len(booked) == 1
    assert {r["refused"] for r in refused} == {"slot_taken"}
    assert len(await _live(w["tenant_id"])) == 1


async def test_a_write_on_a_stale_read_does_not_undo_a_cancellation(
    db_session, console_world
) -> None:
    """La API leyó la reserva sin confirmar y, entre la lectura y la escritura,
    el cron la liberó. Confirmar después no la resucita (el aforo ya se ofreció):
    la escritura relee la fila bajo candado y la transición ya no vale."""
    from datetime import UTC, datetime

    from nexus_api.services.reservations import core
    from tests.integration.reservas._worker import book, reservation, set_status

    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    rid = await book(
        w["tenant_id"],
        day=future_day(),
        at="10:00",
        status="pending",
        staff=shop["lucia"],
        service=shop["corte"],
    )
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        ctx = await core.load_ctx(session, w["tenant_id"])
        assert ctx is not None
        stale = await core.get_booking(session, rid)
        assert stale.status == "pending"
        await set_status(w["tenant_id"], rid, "cancelled")  # otra transacción, ya confirmada
        with pytest.raises(core.ReservationError) as err:
            await core.transition(
                session,
                ctx,
                stale,
                "confirm",
                actor=core.Actor("person", "Valeria"),
                now=datetime.now(UTC),
            )
        assert err.value.code == "invalid_transition"
    assert (await reservation(w["tenant_id"], rid)).status == "cancelled"
