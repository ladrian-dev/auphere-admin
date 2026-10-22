"""Spec 043 CE-002 y R8 — la agenda de un cliente no enseña nada de la vecina.

La agenda de **todo** un negocio es superficie nueva: la persona de un cliente
ve las reservas de todas las personas que reservan en su negocio. La frontera
que no puede cruzar es la del cliente vecino del mismo partner, la más peligrosa
porque todo lo que no sea la RLS del cliente la deja pasar.

El barrido enumera las rutas montadas bajo ``/console/lite/reservas`` (una ruta
nueva entra sola), en los **dos modos** y con las **dos credenciales** (la de la
consola y la del teléfono):

- las ``GET`` sin identificador responden 200 (o ``wrong_mode`` si son del otro
  modo) y no traen ningún nombre, teléfono ni id de la vecina;
- toda ruta con el id de un objeto de la vecina (reserva, persona, servicio,
  bloqueo, entrada, oferta) responde **byte a byte** igual que a un id que no
  existe;
- una persona del partner y la de un cliente sin el módulo reciben 403.

Los barridos genéricos de la consola lite (``test_lite_client_vs_client``,
``test_phone_route_scope``) dejan estas rutas a este archivo: necesitan modo y
rango de fechas.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any

import pytest

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    PartnerTenant,
    Reservation,
    ReservationBlock,
    ReservationOffer,
    ReservationOfferCandidate,
    ReservationWaitlist,
    Tenant,
    TenantPlan,
)
from tests.conftest import (
    add_client_member,
    add_client_phone,
    future_day,
    make_client_access,
    make_reservas,
)
from tests.isolation.test_console_scope import _console_routes

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

PREFIX = "/console/lite/reservas"
NEIGHBOUR = "Vecina con Reservas"
NEIGHBOUR_CONTACT = "Cliente de la Vecina"
NEIGHBOUR_PHONE = "+56977778888"

#: Para cada parámetro de ruta, la clave del objeto de la vecina.
FOREIGN = {
    "booking_id": "booking",
    "staff_id": "staff",
    "service_id": "service",
    "block_id": "block",
    "entry_id": "entry",
    "offer_id": "offer",
}


async def _world(db_session: Any, console_world: dict[str, Any], mode: str) -> dict[str, Any]:
    a = console_world["a"]
    me = await make_reservas(
        db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"], mode=mode
    )
    neighbour = uuid.uuid4()
    db_session.add(
        Tenant(
            id=neighbour,
            name=NEIGHBOUR,
            slug=f"vecina-res-{neighbour.hex[:6]}",
            plan=TenantPlan.PRO,
            partner_id=a["partner_id"],
        )
    )
    await db_session.flush()
    db_session.add(
        PartnerTenant(
            partner_id=a["partner_id"],
            external_client_ref="vecina-res",
            tenant_id=neighbour,
            client_name=NEIGHBOUR,
        )
    )
    await db_session.commit()
    them = await make_reservas(
        db_session, partner_id=a["partner_id"], tenant_id=neighbour, with_access=False
    )
    day = future_day()
    starts = datetime.combine(day, time(15, 0), tzinfo=UTC)
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, neighbour):
        booking = Reservation(
            tenant_id=neighbour,
            mode="services",
            status="confirmed",
            starts_at=starts,
            ends_at=starts + timedelta(minutes=30),
            party_size=1,
            staff_id=them["lucia"],
            service_id=them["corte"],
            service_name="Corte",
            contact_name=NEIGHBOUR_CONTACT,
            contact_phone=NEIGHBOUR_PHONE,
            origin="agent",
            channel="whatsapp",
            created_by_kind="agent",
            created_by_name=NEIGHBOUR,
        )
        block = ReservationBlock(
            tenant_id=neighbour,
            day=day,
            from_time=time(12, 0),
            until_time=time(13, 0),
            label=f"Evento de {NEIGHBOUR}",
        )
        entry = ReservationWaitlist(
            tenant_id=neighbour,
            mode="services",
            status="waiting",
            contact_name=NEIGHBOUR_CONTACT,
            contact_phone=NEIGHBOUR_PHONE,
            service_id=them["corte"],
            joined_by_kind="person",
        )
        session.add_all([booking, block, entry])
        await session.flush()
        offer = ReservationOffer(
            tenant_id=neighbour,
            mode="services",
            status="running",
            starts_at=starts + timedelta(hours=2),
            ends_at=starts + timedelta(hours=2, minutes=30),
            staff_id=them["lucia"],
            service_id=them["corte"],
            window_minutes=5,
            max_candidates=5,
        )
        session.add(offer)
        await session.flush()
        session.add(
            ReservationOfferCandidate(
                tenant_id=neighbour,
                offer_id=offer.id,
                waitlist_id=entry.id,
                position=1,
                status="waiting",
            )
        )
        ids = {
            "booking": booking.id,
            "block": block.id,
            "entry": entry.id,
            "offer": offer.id,
        }
    phone = await add_client_phone(db_session, membership_id=me["member"]["membership_id"])
    return {
        **ids,
        "staff": them["lucia"],
        "service": them["corte"],
        "neighbour": neighbour,
        "me": me,
        "web": me["headers"],
        "phone": phone["headers"],
        "day": day,
    }


def _routes() -> list[tuple[str, str]]:
    return sorted(
        (sorted(r.methods)[0], r.path) for r in _console_routes() if r.path.startswith(PREFIX)
    )


#: Un cuerpo válido por escritura con id: el 404 tiene que ser el de la RLS,
#: no un 422 de validación.
def _body(method: str, path: str, day: Any) -> dict[str, Any] | None:
    if path.endswith("/move"):
        return {"date": day.isoformat(), "time": "10:00"}
    if path.endswith("/cancel"):
        return {"notify": False}
    if path.endswith("/calendar"):
        return {"calendar_id": None}
    if method == "PATCH":
        return {"name": "Otro nombre"}
    return None


def _query(path: str, world: dict[str, Any], mode: str) -> dict[str, str]:
    day = world["day"].isoformat()
    if path.endswith("/bookings") or path.endswith("/occupancy") or path.endswith("/blocks"):
        return {"from": day, "to": day}
    if path.endswith("/slots"):
        q = {"date": day}
        if mode == "services":
            q["service_id"] = str(world["me"]["corte"])
        return q
    return {}


def _clean(text: str, world: dict[str, Any]) -> None:
    assert NEIGHBOUR not in text
    assert NEIGHBOUR_CONTACT not in text
    assert NEIGHBOUR_PHONE not in text
    assert str(world["neighbour"]) not in text
    for key in FOREIGN.values():
        assert str(world[key]) not in text


@pytest.mark.parametrize("credential", ["web", "phone"])
@pytest.mark.parametrize("mode", ["services", "capacity"])
async def test_reservas_never_show_the_neighbour(
    mode: str, credential: str, client, db_session, console_world
) -> None:
    world = await _world(db_session, console_world, mode)
    headers = world[credential]
    probed = 0
    for method, path in _routes():
        params = [seg[1:-1] for seg in path.split("/") if seg.startswith("{")]
        if not params:
            if method != "GET":
                continue
            resp = await client.get(path, headers=headers(), params=_query(path, world, mode))
            ok = resp.status_code == 200 or (
                resp.status_code == 409 and resp.json()["detail"]["code"] == "wrong_mode"
            )
            assert ok, f"{path}: {resp.status_code} {resp.text[:200]}"
            _clean(resp.text, world)
            probed += 1
            continue
        missing = [p for p in params if p not in FOREIGN]
        assert not missing, f"{path}: no foreign object to probe for {missing}"
        foreign_path, ghost_path = path, path
        for p in params:
            foreign_path = foreign_path.replace("{" + p + "}", str(world[FOREIGN[p]]))
            ghost_path = ghost_path.replace("{" + p + "}", str(uuid.uuid4()))
        body = _body(method, path, world["day"])
        foreign = await client.request(method, foreign_path, headers=headers(), json=body)
        ghost = await client.request(method, ghost_path, headers=headers(), json=body)
        assert foreign.status_code == ghost.status_code, (method, path, foreign.text, ghost.text)
        assert foreign.status_code in (404, 409), (method, path, foreign.status_code)
        assert foreign.content == ghost.content, (method, path)
        _clean(foreign.text, world)
        probed += 1
    assert probed >= 25  # el barrido no se queda vacío si cambia el prefijo


async def test_a_partner_member_and_a_client_without_the_module_get_403(
    client, db_session, console_world
) -> None:
    a = console_world["a"]
    world = await _world(db_session, console_world, "services")
    await make_client_access(
        db_session, partner_id=a["partner_id"], tenant_id=world["neighbour"], modules=("panel",)
    )
    no_module = await add_client_member(
        db_session, partner_id=a["partner_id"], tenant_id=world["neighbour"]
    )
    for method, path in _routes():
        concrete = path
        for p, key in FOREIGN.items():
            concrete = concrete.replace("{" + p + "}", str(world[key]))
        body = _body(method, path, world["day"])
        partner = await client.request(method, concrete, headers=a["headers"](), json=body)
        assert partner.status_code == 403, (method, path, partner.status_code)
        outsider = await client.request(method, concrete, headers=no_module["headers"](), json=body)
        assert outsider.status_code == 403, (method, path, outsider.status_code)
