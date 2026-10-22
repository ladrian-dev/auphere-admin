"""Spec 043 R6 y CE-003 — garantía 8: el agente solo toca las reservas de la
persona con la que habla.

Dos clientes finales del mismo negocio son filas legítimas del mismo tenant: la
RLS no los separa. Lo hace el turno (``current_customer_or_refuse``), y que
**ninguna** herramienta ``reservas.*`` acepte un cliente como argumento.

- el esquema de cada herramienta no tiene ningún campo de cliente (barrido);
- la reserva de Ana no existe para el turno de Bruno: ni se lista, ni se mueve,
  ni se cancela, ni se confirma, ni sirve para apuntarse a la lista;
- la oferta de Ana no la acepta Bruno;
- sin persona en el turno, no se reserva; sin el módulo, ninguna herramienta.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import customer_context, tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import ClientAccess, Customer, Reservation
from tests.conftest import future_day, make_reservas

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

CUSTOMER_AXIS = {
    "customer",
    "customer_id",
    "customer_email",
    "customer_phone",
    "client_id",
    "patient_id",
    "debtor_id",
    "phone",
    "contact",
    "contact_phone",
    "name",
}


def _registry() -> Any:
    from nexus_mcp import build_default_registry
    from nexus_mcp.registry import reset_default_registry

    reset_default_registry()
    return build_default_registry()


def test_no_reservas_tool_takes_a_customer() -> None:
    registry = _registry()
    tools = [
        d for d in registry.get_tool_definitions(registry.names()) if d.name.startswith("reservas.")
    ]
    assert len(tools) == 9
    for tool in tools:
        props = set((tool.parameters or {}).get("properties", {}))
        assert not props & CUSTOMER_AXIS, (tool.name, props & CUSTOMER_AXIS)


async def _call(
    registry: Any,
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID | None,
    name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    with tenant_context(tenant_id), customer_context(customer_id):
        env = await registry.dispatch(name, args, whitelist=[name])
    return dict(env["result"])


@pytest.fixture
async def shop(db_session, console_world) -> dict[str, Any]:
    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    ana = Customer(tenant_id=w["tenant_id"], identifier="56911110000", name="Ana", preferences={})
    bruno = Customer(
        tenant_id=w["tenant_id"], identifier="56922220000", name="Bruno", preferences={}
    )
    db_session.add_all([ana, bruno])
    await db_session.commit()
    return {**shop, "ana": ana.id, "bruno": bruno.id, "registry": _registry()}


async def _ana_books(shop: dict[str, Any], at: str = "10:00") -> str:
    out = await _call(
        shop["registry"],
        shop["tenant_id"],
        shop["ana"],
        "reservas.create",
        {
            "date": future_day().isoformat(),
            "time": at,
            "service_id": str(shop["corte"]),
            "staff_id": str(shop["lucia"]),
            "idempotency_key": f"ana:{at}",
        },
    )
    assert out["booking"] is not None, out
    return str(out["booking"]["id"])


async def test_another_persons_booking_does_not_exist_for_this_turn(shop) -> None:
    from nexus_mcp.base import ToolError

    booking = await _ana_books(shop)
    r, tid, bruno = shop["registry"], shop["tenant_id"], shop["bruno"]

    assert (await _call(r, tid, bruno, "reservas.list_mine", {}))["bookings"] == []
    day = future_day().isoformat()
    for name, args in (
        ("reservas.reschedule", {"booking_id": booking, "date": day, "time": "11:00"}),
        ("reservas.cancel", {"booking_id": booking}),
        ("reservas.confirm_attendance", {"attending": False, "booking_id": booking}),
        ("reservas.join_waitlist", {"service_id": str(shop["corte"]), "booking_id": booking}),
    ):
        with pytest.raises(ToolError, match="not found for this customer"):
            await _call(r, tid, bruno, name, args)

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tid):
        row = await session.get(Reservation, uuid.UUID(booking))
        assert row is not None and row.status == "pending" and row.customer_id == shop["ana"]
        assert row.version == 1  # nadie la tocó


async def test_the_same_idempotency_key_never_hands_over_another_persons_booking(shop) -> None:
    """/cso CSO-001: el modelo elige la clave y no conoce el id de la
    conversación, así que dos personas pueden mandar la misma («sabado-2100»).
    La segunda no recibe la reserva de la primera: la clave es de cada persona."""
    r, tid = shop["registry"], shop["tenant_id"]
    day = future_day().isoformat()

    def args(at: str) -> dict[str, Any]:
        return {
            "date": day,
            "time": at,
            "service_id": str(shop["corte"]),
            "staff_id": str(shop["lucia"]),
            "idempotency_key": "sabado-2100",
        }

    ana = await _call(r, tid, shop["ana"], "reservas.create", args("10:00"))
    bruno = await _call(r, tid, shop["bruno"], "reservas.create", args("11:00"))
    assert bruno["booking"] is not None and bruno["idempotent_replay"] is False
    assert bruno["booking"]["id"] != ana["booking"]["id"]
    assert bruno["booking"]["start"] == "11:00"
    # Repetir la misma llamada de Bruno sigue siendo idempotente, para él.
    again = await _call(r, tid, shop["bruno"], "reservas.create", args("11:00"))
    assert again["idempotent_replay"] is True
    assert again["booking"]["id"] == bruno["booking"]["id"]

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tid):
        owners = {
            str(rid): cid
            for rid, cid in (
                await session.execute(sa.select(Reservation.id, Reservation.customer_id))
            ).all()
        }
    assert owners == {ana["booking"]["id"]: shop["ana"], bruno["booking"]["id"]: shop["bruno"]}


async def test_core_refuses_a_key_that_belongs_to_another_person(shop) -> None:
    """Defensa en el dominio: aunque una clave llegue igual, ``create_booking``
    no devuelve la reserva de otra persona."""
    from datetime import UTC, datetime, time

    from nexus_api.services.reservations import core

    await _ana_books(shop)
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, shop["tenant_id"]):
        ctx = await core.load_ctx(session, shop["tenant_id"])
        assert ctx is not None
        key = await session.scalar(sa.select(Reservation.idempotency_key))
        with pytest.raises(core.ReservationError) as err:
            await core.create_booking(
                session,
                ctx,
                core.NewBooking(
                    day=future_day(),
                    at=time(12, 0),
                    origin="agent",
                    channel="whatsapp",
                    contact_name="Bruno",
                    contact_phone=None,
                    service_id=shop["corte"],
                    staff_id=shop["lucia"],
                    idempotency_key=key,
                    customer_id=shop["bruno"],
                    as_agent=True,
                ),
                actor=core.Actor("agent", "Agente"),
                now=datetime.now(UTC),
            )
        assert err.value.code == "idempotency_conflict"


async def test_an_offer_is_only_answered_by_its_person(shop) -> None:
    """La oferta de Ana: Bruno no tiene ninguna abierta, aunque responda «sí»."""
    from nexus_api.services.reservations import waitlist
    from nexus_api.services.reservations.core import load_ctx

    tid = shop["tenant_id"]
    # Carla cancela su cita; Ana estaba en la lista y recibe la oferta.
    carla_booking = await _ana_books(shop, "16:00")  # una cita que se libera
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tid):
        ctx = await load_ctx(session, tid)
        assert ctx is not None
        await waitlist.join(
            session,
            ctx,
            waitlist.NewEntry(
                contact_name="Ana",
                contact_phone="+56911110000",
                joined_by_kind="agent",
                customer_id=shop["ana"],
                service_id=shop["corte"],
            ),
        )
        res = await session.get(Reservation, uuid.UUID(carla_booking))
        assert res is not None
        res.customer_id = None  # que la cancelada no sea de Ana
        res.status = "cancelled"
        await session.flush()
        from datetime import UTC, datetime

        offer = await waitlist.open_after_cancel(session, ctx, res, datetime.now(UTC))
        assert offer is not None

    bruno = await _call(
        shop["registry"], tid, shop["bruno"], "reservas.answer_offer", {"accept": True}
    )
    assert bruno["result"] == "no_offer"
    ana = await _call(shop["registry"], tid, shop["ana"], "reservas.answer_offer", {"accept": True})
    assert ana["result"] == "booked"


async def test_without_a_person_the_agent_cannot_book(shop) -> None:
    from nexus_mcp.base import ToolError

    with pytest.raises(ToolError, match="no hay cliente resuelto"):
        await _call(
            shop["registry"],
            shop["tenant_id"],
            None,
            "reservas.create",
            {
                "date": future_day().isoformat(),
                "time": "10:00",
                "service_id": str(shop["corte"]),
                "idempotency_key": "nadie",
            },
        )
    assert (await _call(shop["registry"], shop["tenant_id"], None, "reservas.list_mine", {}))[
        "bookings"
    ] == []


async def test_without_the_module_no_tool_works(shop, db_session) -> None:
    from nexus_mcp.base import ToolError

    await db_session.execute(
        sa.update(ClientAccess)
        .where(ClientAccess.tenant_id == shop["tenant_id"])
        .values(modules=["panel"])
    )
    await db_session.commit()
    with pytest.raises(ToolError, match="Reservas no está activo"):
        await _call(shop["registry"], shop["tenant_id"], shop["ana"], "reservas.services", {})
