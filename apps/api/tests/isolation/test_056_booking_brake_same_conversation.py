"""Garantía 8 — el freno de citas solo cree a la conversación del turno
(spec 056, T015 · requisito 1.1).

Lo que respalda una respuesta de un turno anterior (``booking_brake.conversation_backed``)
se lee en la sesión del cliente (RLS) y filtrado por **esa** conversación:

- una reserva viva de **otra** conversación del mismo cliente no la respalda;
- una reserva viva de **otro** cliente tampoco, ni pidiéndola por su id: desde
  la sesión de un cliente, la conversación del vecino no existe;
- una reserva cancelada no respalda, ni un ``reservas.create`` con ``ok`` de un
  turno viejo (la agenda manda: pudo cancelarse después).

Los controles positivos (la conversación con su reserva viva, el éxito de un
calendario conectado) demuestran que la lectura sí ve lo que debe.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from nexus_worker.persistence.messages import persist_outbound_message
from nexus_worker.runtime.booking_brake import conversation_backed, load_conversation_backing

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Reservation
from tests.integration._turn_world import (
    RecordingPipeline,
    conversation_of,
    make_world,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

BRIEF = {"id": "7f0c", "date": "2026-11-13", "start": "10:00", "end": "10:30"}


async def _conversation(world: Any, user: str) -> uuid.UUID:
    from nexus_worker.runtime.dispatcher import process_inbound

    await process_inbound(world.event("hola", user=user), pipeline=RecordingPipeline())
    return (await conversation_of(world, user)).id


async def _reservation(tenant_id: uuid.UUID, conversation_id: uuid.UUID, status: str) -> None:
    starts = datetime.now(UTC).replace(microsecond=0) + timedelta(days=3)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        s.add(
            Reservation(
                tenant_id=tenant_id,
                mode="capacity",
                status=status,
                starts_at=starts,
                ends_at=starts + timedelta(hours=1),
                party_size=2,
                conversation_id=conversation_id,
                origin="agent",
                channel="whatsapp",
                created_by_kind="agent",
                version=1,
            )
        )


async def _outbound(tenant_id: uuid.UUID, conversation_id: uuid.UUID, calls: list[Any]) -> None:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        await persist_outbound_message(
            s,
            conversation_id=conversation_id,
            content="Listo.",
            intent="book",
            model=None,
            tool_calls=calls,
            actor_kind="agent",
        )


def _ok(tool: str, **result: Any) -> dict[str, Any]:
    return {"tool": tool, "status": "ok", "result": result}


async def test_only_this_conversation_backs_a_claim(db_session, tenants_ab) -> None:
    a, b = tenants_ab["a"], tenants_ab["b"]
    world_a = await make_world(db_session, tenant_id=a)
    world_b = await make_world(db_session, tenant_id=b)
    asked = await _conversation(world_a, "+34600000001")
    sibling = await _conversation(world_a, "+34600000002")
    neighbour = await _conversation(world_b, "+34600000003")

    # La hermana (mismo cliente) y la vecina (otro cliente) tienen su cita viva y
    # el éxito de un calendario conectado.
    for tenant, conversation in ((a, sibling), (b, neighbour)):
        await _reservation(tenant, conversation, "confirmed")
        await _outbound(
            tenant, conversation, [_ok("GOOGLECALENDAR_CREATE_EVENT", data={"id": "e"})]
        )
    # La conversación del turno: una cita cancelada y un ``ok`` viejo de Reservas.
    await _reservation(a, asked, "cancelled")
    await _outbound(a, asked, [_ok("reservas.create", booking=BRIEF, refused=None)])

    assert not await conversation_backed(a, asked), "lo de la hermana o lo cancelado respaldó"
    assert await conversation_backed(a, sibling), "control: la lectura ve lo que debe"
    assert not await conversation_backed(a, neighbour), "desde A, la vecina existe"
    assert not await conversation_backed(b, asked)
    assert not await conversation_backed(b, sibling)
    assert await conversation_backed(b, neighbour)

    async with get_sessionmaker()() as s, tenant_scoped_session(s, a):
        assert not await load_conversation_backing(s, neighbour, None)
        assert not await load_conversation_backing(s, asked, None)
        assert await load_conversation_backing(s, sibling, None)


async def test_a_live_reservation_of_the_conversation_backs_it_and_only_from_its_client(
    db_session, tenants_ab
) -> None:
    a, b = tenants_ab["a"], tenants_ab["b"]
    world_a = await make_world(db_session, tenant_id=a)
    asked = await _conversation(world_a, "+34600000004")
    await _reservation(a, asked, "pending")

    assert await conversation_backed(a, asked)
    assert not await conversation_backed(b, asked), "otro cliente, mismo id: no respalda"
    assert not await conversation_backed(a, uuid.uuid4())
    assert not await conversation_backed(a, None)
