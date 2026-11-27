"""Spec 082, requisito 5.5 — el nombre del contacto sigue a su perfil de WhatsApp.

Reglas (data-model.md, ``customers.preferences``):

1. Un entrante con un nombre de perfil distinto del último guardado lo guarda en
   ``preferences.profile_name``.
2. En ese caso, salvo ``preferences.name_by == "person"``, el nombre pasa a ser
   el del perfil.
3. Un contacto nuevo sin nombre toma el del perfil.
4. Los contactos de antes, sin ``profile_name``, comparan con su nombre.

``name_by: "person"`` lo pone una persona del equipo: un alta desde Reservas
con el nombre escrito, o el nombre de la agenda del teléfono del negocio que
rellena un contacto sin nombre. El agente no marca.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.persistence.messages import upsert_customer
from nexus_worker.runtime.dispatcher import accept_inbound

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Customer
from nexus_api.services.reservations import core
from tests.conftest import future_day, make_reservas

from ._turn_world import conversation_of, make_world

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

USER = "+34600111333"


async def _customer(tenant_id: uuid.UUID, customer_id: uuid.UUID) -> Customer:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tenant_id):
        row = await s.get(Customer, customer_id)
        assert row is not None
        s.expunge(row)
        return row


async def _by_identifier(tenant_id: uuid.UUID, identifier: str) -> Customer:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tenant_id):
        row = await s.scalar(sa.select(Customer).where(Customer.identifier == identifier))
        assert row is not None
        s.expunge(row)
        return row


async def _upsert(tenant_id: uuid.UUID, **kw: Any) -> Customer:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tenant_id):
        row = await upsert_customer(s, **kw)
        s.expunge(row)
        return row


async def _write(tenant_id: uuid.UUID, customer_id: uuid.UUID, **values: Any) -> None:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tenant_id):
        await s.execute(sa.update(Customer).where(Customer.id == customer_id).values(**values))


async def test_a_new_profile_name_renames_the_contact(db_session) -> None:
    """Por el despachador, como llega un mensaje de WhatsApp."""
    world = await make_world(db_session)
    await accept_inbound(world.event("hola", user=USER, customer_name="Ana"))
    conv = await conversation_of(world, USER)
    first = await _customer(world.tenant_id, conv.customer_id)
    assert first.name == "Ana"
    assert first.preferences.get("profile_name") == "Ana"

    await accept_inbound(world.event("soy yo otra vez", user=USER, customer_name="Ana Ruiz"))
    renamed = await _customer(world.tenant_id, conv.customer_id)
    assert renamed.name == "Ana Ruiz"
    assert renamed.preferences.get("profile_name") == "Ana Ruiz"
    assert "name_by" not in renamed.preferences


async def test_a_contact_from_before_follows_its_profile(db_session) -> None:
    """Sin ``profile_name`` guardado, se compara con el nombre: gana el perfil."""
    world = await make_world(db_session)
    legacy = await _upsert(world.tenant_id, identifier=USER, name="Anita")
    await _write(world.tenant_id, legacy.id, preferences={})

    same = await _upsert(world.tenant_id, identifier=USER, profile_name="Anita")
    assert same.name == "Anita"

    changed = await _upsert(world.tenant_id, identifier=USER, profile_name="Ana Ruiz")
    assert changed.id == legacy.id
    assert changed.name == "Ana Ruiz"


async def test_a_name_written_by_a_person_is_never_overwritten(db_session) -> None:
    world = await make_world(db_session)
    c = await _upsert(world.tenant_id, identifier=USER)
    await _write(
        world.tenant_id,
        c.id,
        name="Ana (la del lunes)",
        preferences={"name_by": "person", "profile_name": "Ana"},
    )

    await accept_inbound(world.event("hola", user=USER, customer_name="Ana Ruiz"))
    kept = await _customer(world.tenant_id, c.id)
    assert kept.name == "Ana (la del lunes)"
    assert kept.preferences["name_by"] == "person"
    # El perfil se apunta igual: es el último que mandó WhatsApp.
    assert kept.preferences["profile_name"] == "Ana Ruiz"


async def test_the_business_agenda_fills_a_nameless_contact_as_a_person(db_session) -> None:
    """La agenda del teléfono del negocio (coexistencia) la escribió una persona."""
    world = await make_world(db_session)
    nameless = await _upsert(world.tenant_id, identifier=USER)
    assert nameless.name is None

    filled = await _upsert(world.tenant_id, identifier=USER, name="Ana peluquería")
    assert filled.name == "Ana peluquería"
    assert filled.preferences.get("name_by") == "person"

    after = await _upsert(world.tenant_id, identifier=USER, profile_name="Ana Ruiz")
    assert after.name == "Ana peluquería"


async def test_a_contact_created_from_reservas_with_a_name_is_marked(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    made = await client.post(
        "/console/lite/reservas/bookings",
        headers=shop["headers"](),
        json={
            "date": future_day().isoformat(),
            "time": "10:00",
            "staff_id": str(shop["lucia"]),
            "service_id": str(shop["corte"]),
            "contact": {"name": "Marta Gil", "phone": "+56922223333"},
        },
    )
    assert made.status_code == 201, made.text

    marta = await _by_identifier(w["tenant_id"], "56922223333")
    assert marta.name == "Marta Gil"
    assert marta.preferences.get("name_by") == "person"


async def test_the_agent_does_not_mark_the_name(db_session, console_world) -> None:
    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, w["tenant_id"]):
        ctx = await core.load_ctx(s, w["tenant_id"])
        assert ctx is not None
        await core.create_booking(
            s,
            ctx,
            core.NewBooking(
                day=future_day(),
                at=time(11, 0),
                origin="agent",
                channel="whatsapp",
                contact_name="Pedro",
                contact_phone="+56933334444",
                staff_id=shop["lucia"],
                service_id=shop["corte"],
                notify=False,
            ),
            actor=core.Actor("agent", "Recepción"),
            now=datetime.now(UTC),
        )

    pedro = await _by_identifier(w["tenant_id"], "56933334444")
    assert pedro.name == "Pedro"
    assert "name_by" not in pedro.preferences
