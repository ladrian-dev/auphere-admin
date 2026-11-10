"""Spec 043 — ``reservation-offers-cron`` y las ofertas de la lista (T017, Historia 6).

Servicios: el hueco de una cita cancelada se ofrece de uno en uno, 5 min cada
uno, hasta 5; al vencer el plazo, el cron pasa al siguiente y, sin nadie más,
cierra la oferta vacía. Quien acepta tarde se queda el hueco si sigue libre; si
ya es de otro, sigue en la lista. «Detener» devuelve a la lista a quien
esperaba respuesta.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.streams.reservation_offers_cron import process_tenant as advance_offers

from nexus_api.db.models import (
    ReservationOffer,
    ReservationOfferCandidate,
    ReservationWaitlist,
)
from nexus_api.services.reservations import core, waitlist
from tests.conftest import future_day, make_reservas
from tests.integration.reservas._worker import book, outbox, scoped

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def salon(db_session, console_world) -> dict[str, Any]:
    w = console_world["a"]
    return await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])


async def _waiting_people(salon, n: int) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """``n`` personas en la lista para un Corte con cualquiera, cada una en su
    transacción (el orden de llegada es el de la lista)."""
    tid = salon["tenant_id"]
    out: list[tuple[uuid.UUID, uuid.UUID]] = []
    for i in range(n):
        async with scoped(tid) as s:
            ctx = await core.load_ctx(s, tid)
            assert ctx is not None
            phone = f"+5698000000{i}"
            cust = await core.contact_customer(s, ctx, phone, f"Persona {i}")
            assert cust is not None
            entry = await waitlist.join(
                s,
                ctx,
                waitlist.NewEntry(
                    contact_name=f"Persona {i}",
                    contact_phone=phone,
                    joined_by_kind="person",
                    customer_id=cust,
                    service_id=salon["corte"],
                ),
            )
            out.append((entry.id, cust))
    return out


async def _cancel_and_offer(salon, now: datetime, *, service: str = "corte") -> uuid.UUID:
    tid = salon["tenant_id"]
    rid = await book(
        tid,
        day=future_day(3),
        at="12:00",
        phone="+56955556666",
        name="Carla",
        staff=salon["marcos"],
        service=salon[service],
    )
    async with scoped(tid) as s:
        ctx = await core.load_ctx(s, tid)
        assert ctx is not None
        res = await core.get_booking(s, rid)
        await core.cancel_booking(
            s, ctx, res, by="business", actor=core.Actor("person", "V"), now=now, notify=False
        )
        offer = await waitlist.open_after_cancel(s, ctx, res, now)
        assert offer is not None
        return offer.id


async def _advance(tid, now) -> int:
    async with scoped(tid) as s:
        return await advance_offers(s, tid, now)


async def _state(tid, offer_id) -> tuple[str, list[tuple[uuid.UUID, str]]]:
    async with scoped(tid) as s:
        offer = await s.get(ReservationOffer, offer_id)
        assert offer is not None
        cands = (
            await s.execute(
                sa.select(ReservationOfferCandidate.waitlist_id, ReservationOfferCandidate.status)
                .where(ReservationOfferCandidate.offer_id == offer_id)
                .order_by(ReservationOfferCandidate.position)
            )
        ).all()
        return offer.status, [(w, st) for w, st in cands]


async def _entry_status(tid, entry_id) -> str:
    async with scoped(tid) as s:
        entry = await s.get(ReservationWaitlist, entry_id)
        assert entry is not None
        return entry.status


async def test_services_offer_goes_one_by_one_five_minutes_each_up_to_five(salon) -> None:
    tid = salon["tenant_id"]
    people = await _waiting_people(salon, 6)
    t0 = datetime.now(UTC)
    offer_id = await _cancel_and_offer(salon, t0)

    status, cands = await _state(tid, offer_id)
    assert status == "running"
    assert [w for w, _ in cands] == [e for e, _ in people[:5]]  # hasta 5
    assert [st for _, st in cands] == ["waiting", "queued", "queued", "queued", "queued"]

    assert await _advance(tid, t0 + timedelta(minutes=4)) == 0  # aún en plazo
    assert (await _state(tid, offer_id))[1][0][1] == "waiting"

    for i in range(1, 5):
        await _advance(tid, t0 + timedelta(minutes=5 * i, seconds=1))
        _, cands = await _state(tid, offer_id)
        assert cands[i - 1][1] == "noreply"
        assert cands[i][1] == "waiting"
        assert await _entry_status(tid, people[i - 1][0]) == "waiting"  # vuelve a la lista
        assert await _entry_status(tid, people[i][0]) == "offered"

    await _advance(tid, t0 + timedelta(minutes=25, seconds=1))
    status, cands = await _state(tid, offer_id)
    assert status == "empty"
    assert [st for _, st in cands] == ["noreply"] * 5
    offers_sent = sorted(r.waitlist_id for r in await outbox(tid) if r.kind == "offer")
    assert offers_sent == sorted(e for e, _ in people[:5])


async def test_a_late_yes_wins_when_the_slot_is_still_free(salon) -> None:
    tid = salon["tenant_id"]
    people = await _waiting_people(salon, 2)
    t0 = datetime.now(UTC)
    offer_id = await _cancel_and_offer(salon, t0)
    await _advance(tid, t0 + timedelta(minutes=5, seconds=1))  # la primera no contestó

    async with scoped(tid) as s:
        ctx = await core.load_ctx(s, tid)
        assert ctx is not None
        result = await waitlist.answer(
            s, ctx, customer_id=people[0][1], accept=True, now=t0 + timedelta(minutes=6)
        )
    assert result.result == "booked"
    status, cands = await _state(tid, offer_id)
    assert status == "filled"
    assert cands == [(people[0][0], "late_won"), (people[1][0], "skipped")]
    assert await _entry_status(tid, people[1][0]) == "waiting"


async def test_a_late_yes_when_taken_stays_in_the_list(salon) -> None:
    tid = salon["tenant_id"]
    people = await _waiting_people(salon, 2)
    t0 = datetime.now(UTC)
    offer_id = await _cancel_and_offer(salon, t0)
    await _advance(tid, t0 + timedelta(minutes=5, seconds=1))
    async with scoped(tid) as s:
        ctx = await core.load_ctx(s, tid)
        assert ctx is not None
        won = await waitlist.answer(
            s, ctx, customer_id=people[1][1], accept=True, now=t0 + timedelta(minutes=6)
        )
    assert won.result == "booked"
    async with scoped(tid) as s:
        ctx = await core.load_ctx(s, tid)
        assert ctx is not None
        late = await waitlist.answer(
            s, ctx, customer_id=people[0][1], accept=True, now=t0 + timedelta(minutes=7)
        )
    assert late.result == "late_taken"
    assert await _entry_status(tid, people[0][0]) == "waiting"
    assert "offer_lost" in {r.kind for r in await outbox(tid)}
    status, cands = await _state(tid, offer_id)
    assert status == "filled"
    assert cands == [(people[0][0], "late_taken"), (people[1][0], "accepted")]


async def test_stop_returns_whoever_was_waiting_to_the_list(salon) -> None:
    tid = salon["tenant_id"]
    people = await _waiting_people(salon, 2)
    t0 = datetime.now(UTC)
    offer_id = await _cancel_and_offer(salon, t0)
    async with scoped(tid) as s:
        offer = await s.get(ReservationOffer, offer_id)
        assert offer is not None
        await waitlist.stop(s, offer, t0 + timedelta(minutes=1))
    status, cands = await _state(tid, offer_id)
    assert status == "stopped"
    assert [st for _, st in cands] == ["stopped", "stopped"]
    assert await _entry_status(tid, people[0][0]) == "waiting"
    # Una oferta detenida no la mueve el cron.
    await _advance(tid, t0 + timedelta(minutes=10))
    assert (await _state(tid, offer_id))[0] == "stopped"


async def test_no_offer_closer_than_the_lead_time(salon) -> None:
    """La antelación mínima (2 h por defecto) también corta el avance: si al
    vencer un plazo ya no hay tiempo, la oferta se cierra sin escribir a nadie más."""
    tid = salon["tenant_id"]
    people = await _waiting_people(salon, 2)
    t0 = datetime.now(UTC)
    offer_id = await _cancel_and_offer(salon, t0)
    async with scoped(tid) as s:
        offer = await s.get(ReservationOffer, offer_id)
        assert offer is not None
        starts_at = offer.starts_at
    await _advance(tid, starts_at - timedelta(minutes=90))
    status, cands = await _state(tid, offer_id)
    assert status == "empty"
    assert cands == [(people[0][0], "noreply"), (people[1][0], "skipped")]
    assert len([r for r in await outbox(tid) if r.kind == "offer"]) == 1


async def test_who_takes_a_longer_slot_gets_the_service_they_asked_for(salon) -> None:
    """Se cancela un Color (90 min) y en la lista espera alguien para un Corte
    (30 min): le cabe, se le ofrece y, al aceptar, su reserva es un Corte."""
    tid = salon["tenant_id"]
    people = await _waiting_people(salon, 1)
    t0 = datetime.now(UTC)
    await _cancel_and_offer(salon, t0, service="color")
    async with scoped(tid) as s:
        ctx = await core.load_ctx(s, tid)
        assert ctx is not None
        result = await waitlist.answer(
            s, ctx, customer_id=people[0][1], accept=True, now=t0 + timedelta(minutes=1)
        )
        assert result.result == "booked"
        assert result.booking is not None
        assert result.booking.service_id == salon["corte"]
        assert result.booking.service_name == "Corte"
        assert result.booking.ends_at - result.booking.starts_at == timedelta(minutes=30)
