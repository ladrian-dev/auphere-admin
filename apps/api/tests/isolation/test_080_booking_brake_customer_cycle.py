"""Garantía 8 — el freno cree también a las reservas **del cliente de la
conversación** hechas en este ciclo, y a ninguna otra (spec 080, requisito 1).

El caso que lo trajo (Jemma, 23-nov): una persona del negocio reservó desde la
agenda —sin conversación— para el cliente que estaba atendiendo, devolvió la
conversación y el «gracias» siguiente se frenó porque «no había ninguna reserva
en esta conversación».

Lo que se barre:

- la reserva hecha a mano para **este** cliente, creada o movida en el ciclo, respalda;
- también la adelantada al aceptar una oferta de la lista de espera, que se
  mueve con ``waitlist_accepted`` y sin ``moved`` (revisión antes de producción, BE-1);
- la de **otro** cliente final del mismo negocio no, ni siquiera viva y reciente;
- desde otro negocio, nada;
- cancelada, o creada antes del ciclo sin moverse después, no;
- sin cliente en la conversación, el paso nuevo no aplica.

El cliente sale de la fila de la conversación (servidor), nunca de un argumento.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.booking_brake import conversation_backed

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Conversation, Reservation, ReservationEvent
from tests.integration._turn_world import RecordingPipeline, conversation_of, make_world

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def _conversation(world: Any, user: str) -> Conversation:
    from nexus_worker.runtime.dispatcher import process_inbound

    await process_inbound(world.event("hola", user=user), pipeline=RecordingPipeline())
    conv = await conversation_of(world, user)
    assert conv.customer_id is not None and conv.attended_at is not None
    return conv


async def _by_hand(
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID | None,
    *,
    status: str = "confirmed",
    events: tuple[tuple[str, datetime | None], ...] = (("created", None),),
) -> uuid.UUID:
    """Una reserva como la crea la consola: sin conversación, a nombre de una
    persona del negocio, enlazada al cliente por su teléfono."""
    starts = datetime.now(UTC).replace(microsecond=0) + timedelta(days=5)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        res = Reservation(
            tenant_id=tenant_id,
            # Aforo: sin servicio ni persona que crear (como la prueba 056).
            mode="capacity",
            status=status,
            starts_at=starts,
            ends_at=starts + timedelta(hours=1),
            party_size=2,
            customer_id=customer_id,
            conversation_id=None,
            origin="person",
            channel="phone",
            created_by_kind="person",
            version=1,
        )
        s.add(res)
        await s.flush()
        for kind, at in events:
            event = ReservationEvent(
                tenant_id=tenant_id,
                reservation_id=res.id,
                kind=kind,
                actor_kind="person",
                data={},
            )
            if at is not None:
                event.created_at = at
            s.add(event)
        await s.commit()
        return res.id


async def _set(tenant_id: uuid.UUID, conversation_id: uuid.UUID, **values: Any) -> None:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        await s.execute(
            sa.update(Conversation).where(Conversation.id == conversation_id).values(**values)
        )
        await s.commit()


async def test_a_booking_made_by_hand_for_this_customer_in_this_cycle_backs(
    db_session, tenants_ab
) -> None:
    a, b = tenants_ab["a"], tenants_ab["b"]
    world = await make_world(db_session, tenant_id=a)
    asked = await _conversation(world, "+34600008001")
    assert not await conversation_backed(a, asked.id), "control: sin reserva no respalda"

    await _by_hand(a, asked.customer_id)

    assert await conversation_backed(a, asked.id)
    assert not await conversation_backed(b, asked.id), "desde otro negocio no existe"


async def test_another_customers_booking_never_backs(db_session, tenants_ab) -> None:
    a = tenants_ab["a"]
    world = await make_world(db_session, tenant_id=a)
    asked = await _conversation(world, "+34600008002")
    other = await _conversation(world, "+34600008003")

    await _by_hand(a, other.customer_id)

    assert not await conversation_backed(a, asked.id), "la cita del vecino respaldó"
    assert await conversation_backed(a, other.id), "control: la del vecino es suya"


async def test_a_cancelled_one_does_not_back(db_session, tenants_ab) -> None:
    a = tenants_ab["a"]
    world = await make_world(db_session, tenant_id=a)
    asked = await _conversation(world, "+34600008004")

    await _by_hand(a, asked.customer_id, status="cancelled")

    assert not await conversation_backed(a, asked.id)


async def test_only_this_cycle_counts(db_session, tenants_ab) -> None:
    a = tenants_ab["a"]
    world = await make_world(db_session, tenant_id=a)
    asked = await _conversation(world, "+34600008005")
    long_ago = datetime.now(UTC) - timedelta(days=10)

    # Creada antes del ciclo y sin moverse después: no respalda «quedó reservada».
    await _by_hand(a, asked.customer_id, events=(("created", long_ago),))
    assert not await conversation_backed(a, asked.id)

    # Movida en este ciclo: sí.
    moved = await _by_hand(a, asked.customer_id, events=(("created", long_ago), ("moved", None)))
    assert await conversation_backed(a, asked.id)

    # Tras resolver y reabrir, el corte manda: lo de antes del corte ya no cuenta.
    await _set(a, asked.id, context_from=datetime.now(UTC) + timedelta(seconds=1))
    assert not await conversation_backed(a, asked.id), f"{moved} es de antes del corte"


async def test_a_move_by_accepting_a_waitlist_offer_in_this_cycle_backs(
    db_session, tenants_ab
) -> None:
    """BE-1: aceptar una oferta de la lista de espera con una reserva viva la
    adelanta con ``move_booking(event="waitlist_accepted")``: en su historial no
    hay ``moved``. Ese adelanto respalda «te la he adelantado» igual que una movida."""
    a, b = tenants_ab["a"], tenants_ab["b"]
    world = await make_world(db_session, tenant_id=a)
    asked = await _conversation(world, "+34600008020")
    long_ago = datetime.now(UTC) - timedelta(days=10)

    await _by_hand(
        a, asked.customer_id, events=(("created", long_ago), ("waitlist_accepted", None))
    )

    assert await conversation_backed(a, asked.id), "el adelanto por lista de espera no respaldó"
    assert not await conversation_backed(b, asked.id), "desde otro negocio no existe"


async def test_a_booking_without_a_customer_backs_nobody(db_session, tenants_ab) -> None:
    """Una reserva sin teléfono (sin cliente) no es de nadie: no respalda a ninguna
    conversación. Una conversación siempre tiene cliente (``customer_id`` no nulo)."""
    a = tenants_ab["a"]
    world = await make_world(db_session, tenant_id=a)
    asked = await _conversation(world, "+34600008006")

    await _by_hand(a, None)

    assert not await conversation_backed(a, asked.id)
    assert not await conversation_backed(a, None)


async def test_the_real_console_booking_backs_this_customer_only(
    db_session, console_world, client
) -> None:
    """Por el camino de verdad: la persona del negocio reserva en la agenda de la
    consola (``POST /console/lite/reservas/bookings``) con el teléfono del cliente,
    como el 23-nov. La API escribe el evento ``created`` y enlaza la reserva al
    cliente por su teléfono; el freno la ve para esa conversación y no para la del
    vecino."""
    from tests.conftest import future_day, make_reservas

    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    world = await make_world(db_session, tenant_id=w["tenant_id"])
    asked = await _conversation(world, "+56911112222")
    neighbour = await _conversation(world, "+56933334444")

    r = await client.post(
        "/console/lite/reservas/bookings",
        headers=shop["headers"](),
        json={
            "date": future_day().isoformat(),
            "time": "15:00",
            "staff_id": str(shop["lucia"]),
            "service_id": str(shop["corte"]),
            "contact": {"name": "Cliente", "phone": "+56911112222"},
        },
    )
    assert r.status_code == 201, r.text

    assert await conversation_backed(w["tenant_id"], asked.id)
    assert not await conversation_backed(w["tenant_id"], neighbour.id)
