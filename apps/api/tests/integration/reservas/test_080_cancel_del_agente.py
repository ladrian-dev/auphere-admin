"""Spec 080, requisito 4 — lo que cancela el agente queda a su nombre.

Crear y mover ya quedaban a nombre del agente; cancelar quedaba a nombre del
cliente, y el informe del piloto (spec 083) no podía contar lo que hizo el agente.
La decisión sigue siendo del cliente (``by``): de eso dependen los avisos.
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import customer_context, tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Customer, Reservation, ReservationEvent
from tests.conftest import future_day, make_reservas

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _registry() -> Any:
    from nexus_mcp import build_default_registry
    from nexus_mcp.registry import reset_default_registry

    reset_default_registry()
    return build_default_registry()


async def test_the_agent_cancels_in_its_own_name_and_the_customer_decided(
    db_session, console_world
) -> None:
    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    ana = Customer(tenant_id=w["tenant_id"], identifier="56911110000", name="Ana", preferences={})
    db_session.add(ana)
    await db_session.commit()
    registry = _registry()

    with tenant_context(w["tenant_id"]), customer_context(ana.id):
        made = await registry.dispatch(
            "reservas.create",
            {
                "date": future_day().isoformat(),
                "time": "10:00",
                "service_id": str(shop["corte"]),
                "staff_id": str(shop["lucia"]),
                "idempotency_key": "k",
            },
            whitelist=["reservas.create"],
        )
        booking_id = made["result"]["booking"]["id"]
        gone = await registry.dispatch(
            "reservas.cancel", {"booking_id": booking_id}, whitelist=["reservas.cancel"]
        )
    assert gone["status"] == "ok", gone

    async with get_sessionmaker()() as s, tenant_scoped_session(s, w["tenant_id"]):
        res = await s.get(Reservation, booking_id)
        assert res is not None and res.status == "cancelled"
        assert res.cancelled_by == "customer", "la decisión sigue siendo del cliente"
        [event] = (
            await s.execute(
                sa.select(ReservationEvent).where(
                    ReservationEvent.reservation_id == res.id,
                    ReservationEvent.kind == "cancelled",
                )
            )
        ).scalars()
        assert event.actor_kind == "agent"
        assert event.data["by"] == "customer"
        assert event.data["notified"] is False, "la pidió el cliente: no se le avisa"
