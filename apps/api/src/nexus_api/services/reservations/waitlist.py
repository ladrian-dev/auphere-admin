"""Reservas — la lista de espera y las ofertas de un hueco (spec 043, Historia 6).

Como el diseño:

- **Servicios**: al cancelarse una cita, si el negocio lo pide (o el agente, al
  cancelar el cliente), el hueco se ofrece **de uno en uno, 5 min cada uno,
  hasta 5** a quien encaja: mismo profesional o cualquiera, un servicio que cabe
  en el hueco y, si ya tiene cita, que sea posterior. El hueco queda retenido
  mientras se ofrece (``core._busy_of_staff`` lo cuenta).
- **Aforo**: cuando se libera sitio en una franja, a quien quepa, por orden,
  **15 min** cada uno; una sola oferta abierta por franja.
- En los dos, **solo si falta al menos la antelación mínima** (2 h por defecto).
- Quien acepta tarde se queda el hueco si sigue libre; si ya es de otro, sigue
  en la lista. Un hueco que deja libre quien acepta **no** abre otra oferta.

El cliente final responde por WhatsApp; el agente llama a
``reservas.answer_offer`` y aquí se resuelve **la oferta abierta de esa persona**.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    Reservation,
    ReservationOffer,
    ReservationOfferCandidate,
    ReservationService,
    ReservationStaff,
    ReservationWaitlist,
)
from nexus_api.services.reservations import engine
from nexus_api.services.reservations.core import (
    SYSTEM,
    Actor,
    Ctx,
    NewBooking,
    ReservationError,
    add_event,
    capacity_day,
    create_booking,
    enqueue_message,
    move_booking,
    notify_business,
)

SERVICES_WINDOW_MIN = 5
CAPACITY_WINDOW_MIN = 15
MAX_CANDIDATES = 5


def _lead(ctx: Ctx) -> timedelta:
    return timedelta(minutes=ctx.settings.waitlist_lead_minutes)


# ── entradas ────────────────────────────────────────────────────────────────


@dataclass
class NewEntry:
    contact_name: str | None
    contact_phone: str | None
    joined_by_kind: str  # agent | person | in_person
    joined_by_name: str | None = None
    customer_id: uuid.UUID | None = None
    party_size: int = 1
    desired_day: date | None = None
    desired_time: time | None = None
    desired_until: date | None = None
    service_id: uuid.UUID | None = None
    staff_id: uuid.UUID | None = None
    reservation_id: uuid.UUID | None = None


async def join(session: AsyncSession, ctx: Ctx, entry: NewEntry) -> ReservationWaitlist:
    if not ctx.settings.waitlist_enabled:
        raise ReservationError(409, "waitlist_off")
    if ctx.mode == "capacity" and (entry.desired_day is None or entry.desired_time is None):
        raise ReservationError(422, "desired_slot_required")
    if ctx.mode == "services" and entry.service_id is None:
        raise ReservationError(422, "service_required")
    # Un id que no es del negocio (de la vecina o inventado) es el 404 de
    # siempre, no la violación de la FK compuesta (un 500).
    if entry.service_id is not None:
        svc = await session.get(ReservationService, entry.service_id)
        if svc is None or svc.archived_at is not None:
            raise ReservationError(404, "not_found")
    if entry.staff_id is not None:
        staff = await session.get(ReservationStaff, entry.staff_id)
        if staff is None or staff.archived_at is not None:
            raise ReservationError(404, "not_found")
    row = ReservationWaitlist(
        tenant_id=ctx.tenant_id,
        mode=ctx.mode,
        status="waiting",
        customer_id=entry.customer_id,
        contact_name=entry.contact_name,
        contact_phone=entry.contact_phone,
        party_size=max(1, entry.party_size),
        desired_day=entry.desired_day,
        desired_time=entry.desired_time,
        desired_until=entry.desired_until,
        service_id=entry.service_id,
        staff_id=entry.staff_id,
        reservation_id=entry.reservation_id,
        joined_by_kind=entry.joined_by_kind,
        joined_by_name=entry.joined_by_name,
    )
    session.add(row)
    await session.flush()
    return row


async def remove(session: AsyncSession, entry: ReservationWaitlist) -> None:
    entry.status = "removed"
    await session.execute(
        sa.update(ReservationOfferCandidate)
        .where(
            ReservationOfferCandidate.waitlist_id == entry.id,
            ReservationOfferCandidate.status.in_(("queued", "waiting")),
        )
        .values(status="stopped")
    )
    await session.flush()


async def expire(session: AsyncSession, ctx: Ctx, now: datetime) -> int:
    """Caducan las entradas cuya fecha ya pasó (R7.5)."""
    today = ctx.today(now)
    result = await session.execute(
        sa.update(ReservationWaitlist)
        .where(
            ReservationWaitlist.status == "waiting",
            sa.or_(
                ReservationWaitlist.desired_until < today,
                sa.and_(
                    ReservationWaitlist.desired_until.is_(None),
                    ReservationWaitlist.desired_day < today,
                ),
            ),
        )
        .values(status="expired")
    )
    return int(getattr(result, "rowcount", 0) or 0)


# ── candidatos ──────────────────────────────────────────────────────────────


async def services_candidates(
    session: AsyncSession, ctx: Ctx, *, start: datetime, end: datetime, staff_id: uuid.UUID
) -> list[ReservationWaitlist]:
    day = ctx.local(start).date()
    duration = int((end - start).total_seconds() // 60)
    later = (
        sa.select(Reservation.id)
        .where(Reservation.id == ReservationWaitlist.reservation_id, Reservation.starts_at > start)
        .exists()
    )
    rows = await session.execute(
        sa.select(ReservationWaitlist)
        .join(ReservationService, ReservationService.id == ReservationWaitlist.service_id)
        .where(
            ReservationWaitlist.mode == "services",
            ReservationWaitlist.status == "waiting",
            ReservationService.duration_minutes <= duration,
            sa.or_(
                ReservationWaitlist.staff_id.is_(None), ReservationWaitlist.staff_id == staff_id
            ),
            sa.or_(ReservationWaitlist.reservation_id.is_(None), later),
            sa.or_(
                ReservationWaitlist.desired_day.is_(None), ReservationWaitlist.desired_day == day
            ),
            sa.or_(
                ReservationWaitlist.desired_until.is_(None),
                ReservationWaitlist.desired_until >= day,
            ),
        )
        .order_by(ReservationWaitlist.created_at)
        .limit(MAX_CANDIDATES)
    )
    return list(rows.scalars())


async def capacity_candidates(
    session: AsyncSession, ctx: Ctx, *, at: datetime, now: datetime
) -> list[ReservationWaitlist]:
    local = ctx.local(at)
    rows = await session.execute(
        sa.select(ReservationWaitlist)
        .where(
            ReservationWaitlist.mode == "capacity",
            ReservationWaitlist.status == "waiting",
            ReservationWaitlist.desired_day == local.date(),
            ReservationWaitlist.desired_time == local.time().replace(tzinfo=None),
        )
        .order_by(ReservationWaitlist.created_at)
    )
    entries = list(rows.scalars())
    if not entries:
        return []
    cap = await capacity_day(session, ctx, local.date())
    fits = [
        e
        for e in entries
        if engine.capacity_fit(
            cap.slots, cap.blocked, cap.people, cap.rules, at, e.party_size, now=now
        ).fits
    ]
    return fits[:MAX_CANDIDATES]


# ── abrir una oferta ────────────────────────────────────────────────────────


@dataclass
class Preview:
    can_offer: bool
    candidates: int
    why_not: str | None  # waitlist_off | too_soon | nobody_fits | not_services


async def cancel_preview(
    session: AsyncSession, ctx: Ctx, res: Reservation, now: datetime
) -> Preview:
    if res.mode != "services":
        return Preview(False, 0, "not_services")
    if not ctx.settings.waitlist_enabled:
        return Preview(False, 0, "waitlist_off")
    if res.starts_at - now < _lead(ctx):
        return Preview(False, 0, "too_soon")
    assert res.staff_id is not None
    found = await services_candidates(
        session, ctx, start=res.starts_at, end=res.ends_at, staff_id=res.staff_id
    )
    found = [e for e in found if e.reservation_id != res.id]
    if not found:
        return Preview(False, 0, "nobody_fits")
    return Preview(True, len(found), None)


async def _send(
    session: AsyncSession,
    ctx: Ctx,
    offer: ReservationOffer,
    cand: ReservationOfferCandidate,
    now: datetime,
) -> None:
    cand.status = "waiting"
    cand.sent_at = now
    cand.deadline_at = now + timedelta(minutes=offer.window_minutes)
    entry = await session.get(ReservationWaitlist, cand.waitlist_id)
    if entry is not None:
        entry.status = "offered"
    await enqueue_message(
        session,
        tenant_id=ctx.tenant_id,
        kind="offer",
        dedupe_key=f"offer:{offer.id}:{cand.waitlist_id}",
        offer_id=offer.id,
        waitlist_id=cand.waitlist_id,
    )


async def _open(
    session: AsyncSession,
    ctx: Ctx,
    *,
    start: datetime,
    end: datetime,
    entries: list[ReservationWaitlist],
    now: datetime,
    staff_id: uuid.UUID | None = None,
    service_id: uuid.UUID | None = None,
    seats: int | None = None,
    source: Reservation | None = None,
) -> ReservationOffer | None:
    if not entries or start - now < _lead(ctx):
        return None
    running = await session.scalar(
        sa.select(ReservationOffer.id).where(
            ReservationOffer.status == "running",
            ReservationOffer.starts_at == start,
            ReservationOffer.staff_id.is_(None)
            if staff_id is None
            else ReservationOffer.staff_id == staff_id,
        )
    )
    if running is not None:
        return None
    offer = ReservationOffer(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        mode=ctx.mode,
        status="running",
        starts_at=start,
        ends_at=end,
        staff_id=staff_id,
        service_id=service_id,
        seats=seats,
        source_reservation_id=source.id if source else None,
        cancelled_by_name=(source.contact_name if source else None),
        window_minutes=SERVICES_WINDOW_MIN if ctx.mode == "services" else CAPACITY_WINDOW_MIN,
        max_candidates=MAX_CANDIDATES,
    )
    session.add(offer)
    await session.flush()
    cands = [
        ReservationOfferCandidate(
            tenant_id=ctx.tenant_id, offer_id=offer.id, waitlist_id=e.id, position=i + 1
        )
        for i, e in enumerate(entries[:MAX_CANDIDATES])
    ]
    session.add_all(cands)
    await session.flush()
    await _send(session, ctx, offer, cands[0], now)
    await session.flush()
    return offer


async def open_after_cancel(
    session: AsyncSession, ctx: Ctx, res: Reservation, now: datetime
) -> ReservationOffer | None:
    """El hueco de una cita cancelada, a la lista (Servicios)."""
    if res.mode != "services" or not ctx.settings.waitlist_enabled or res.staff_id is None:
        return None
    entries = [
        e
        for e in await services_candidates(
            session, ctx, start=res.starts_at, end=res.ends_at, staff_id=res.staff_id
        )
        if e.reservation_id != res.id
    ]
    return await _open(
        session,
        ctx,
        start=res.starts_at,
        end=res.ends_at,
        entries=entries,
        now=now,
        staff_id=res.staff_id,
        service_id=res.service_id,
        source=res,
    )


async def open_capacity(
    session: AsyncSession, ctx: Ctx, *, day: date, now: datetime
) -> list[ReservationOffer]:
    """Aforo: en cada franja del día con alguien esperando que ya cabe, una
    oferta (si no hay otra abierta)."""
    if ctx.mode != "capacity" or not ctx.settings.waitlist_enabled:
        return []
    cap = await capacity_day(session, ctx, day)
    opened: list[ReservationOffer] = []
    for slot in cap.slots:
        if slot.at - now < _lead(ctx):
            continue
        entries = await capacity_candidates(session, ctx, at=slot.at, now=now)
        if not entries:
            continue
        offer = await _open(
            session,
            ctx,
            start=slot.at,
            end=slot.at + cap.rules.stay,
            entries=entries,
            now=now,
            seats=entries[0].party_size,
        )
        if offer is not None:
            opened.append(offer)
    return opened


async def offer_manual(
    session: AsyncSession, ctx: Ctx, entry: ReservationWaitlist, now: datetime
) -> ReservationOffer:
    """«Ofrecer» a mano (Aforo): solo si cabe y no hay otra abierta."""
    if ctx.mode != "capacity" or entry.status != "waiting":
        raise ReservationError(409, "invalid_transition", status=entry.status)
    assert entry.desired_day is not None and entry.desired_time is not None
    at = ctx.at(entry.desired_day, entry.desired_time)
    cap = await capacity_day(session, ctx, entry.desired_day)
    fit = engine.capacity_fit(
        cap.slots, cap.blocked, cap.people, cap.rules, at, entry.party_size, now=now
    )
    if not fit.fits:
        raise ReservationError(409, "slot_taken", why=fit.why, first_fit=None)
    offer = await _open(
        session,
        ctx,
        start=at,
        end=at + cap.rules.stay,
        entries=[entry],
        now=now,
        seats=entry.party_size,
    )
    if offer is None:
        raise ReservationError(409, "invalid_transition", status="offer_running")
    return offer


async def stop(session: AsyncSession, offer: ReservationOffer, now: datetime) -> None:
    if offer.status != "running":
        return
    offer.status = "stopped"
    offer.closed_at = now
    cands = await _candidates(session, offer.id)
    for c in cands:
        if c.status in ("queued", "waiting"):
            if c.status == "waiting":
                await _back_to_waiting(session, c.waitlist_id)
            c.status = "stopped"
    await session.flush()


# ── avanzar ─────────────────────────────────────────────────────────────────


async def _candidates(
    session: AsyncSession, offer_id: uuid.UUID
) -> list[ReservationOfferCandidate]:
    rows = await session.execute(
        sa.select(ReservationOfferCandidate)
        .where(ReservationOfferCandidate.offer_id == offer_id)
        .order_by(ReservationOfferCandidate.position)
    )
    return list(rows.scalars())


async def _back_to_waiting(session: AsyncSession, entry_id: uuid.UUID) -> None:
    entry = await session.get(ReservationWaitlist, entry_id)
    if entry is not None and entry.status == "offered":
        entry.status = "waiting"


async def _next(session: AsyncSession, ctx: Ctx, offer: ReservationOffer, now: datetime) -> None:
    """Escribe al siguiente que encaja, o cierra la oferta vacía."""
    for c in await _candidates(session, offer.id):
        if c.status != "queued":
            continue
        if offer.starts_at - now < _lead(ctx):
            break
        entry = await session.get(ReservationWaitlist, c.waitlist_id)
        if entry is None or entry.status != "waiting":
            c.status = "skipped"
            continue
        if offer.mode == "capacity":
            cap = await capacity_day(session, ctx, ctx.local(offer.starts_at).date())
            if not engine.capacity_fit(
                cap.slots,
                cap.blocked,
                cap.people,
                cap.rules,
                offer.starts_at,
                entry.party_size,
                now=now,
            ).fits:
                c.status = "skipped"
                continue
        await _send(session, ctx, offer, c, now)
        return
    for c in await _candidates(session, offer.id):
        if c.status == "queued":
            c.status = "skipped"
    offer.status = "empty"
    offer.closed_at = now


async def advance(session: AsyncSession, ctx: Ctx, now: datetime) -> int:
    """Vence plazos y pasa al siguiente (el cron, cada 15 s)."""
    offers = list(
        (
            await session.execute(
                sa.select(ReservationOffer)
                .where(ReservationOffer.status == "running")
                .with_for_update(skip_locked=True)
            )
        ).scalars()
    )
    moved = 0
    for offer in offers:
        waiting = [c for c in await _candidates(session, offer.id) if c.status == "waiting"]
        due = [c for c in waiting if c.deadline_at is not None and c.deadline_at <= now]
        for c in due:
            c.status = "noreply"
            await _back_to_waiting(session, c.waitlist_id)
            moved += 1
        if not waiting or due:
            await _next(session, ctx, offer, now)
    await session.flush()
    return moved


# ── responder ───────────────────────────────────────────────────────────────


@dataclass
class Answer:
    result: str  # booked | late_taken | declined | no_offer
    booking: Reservation | None = None


async def answer(
    session: AsyncSession,
    ctx: Ctx,
    *,
    customer_id: uuid.UUID,
    accept: bool,
    now: datetime,
    conversation_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
    actor: Actor = SYSTEM,
) -> Answer:
    row = (
        await session.execute(
            sa.select(ReservationOfferCandidate, ReservationOffer, ReservationWaitlist)
            .join(ReservationOffer, ReservationOffer.id == ReservationOfferCandidate.offer_id)
            .join(
                ReservationWaitlist, ReservationWaitlist.id == ReservationOfferCandidate.waitlist_id
            )
            .where(
                ReservationWaitlist.customer_id == customer_id,
                ReservationOfferCandidate.status.in_(("waiting", "noreply")),
                ReservationOfferCandidate.sent_at.is_not(None),
                ReservationOffer.starts_at > now,
            )
            .order_by(ReservationOfferCandidate.sent_at.desc())
            .limit(1)
            .with_for_update()
        )
    ).first()
    if row is None:
        return Answer("no_offer")
    cand, offer, entry = row
    late = cand.status == "noreply"
    cand.answered_at = now
    if not accept:
        cand.status = "noreply"
        entry.status = "waiting"
        if offer.status == "running" and not late:
            await _next(session, ctx, offer, now)
        await session.flush()
        return Answer("declined")
    if offer.status == "filled":
        cand.status = "late_taken"
        entry.status = "waiting"
        await enqueue_message(
            session,
            tenant_id=ctx.tenant_id,
            kind="offer_lost",
            dedupe_key=f"offer_lost:{offer.id}:{entry.id}",
            offer_id=offer.id,
            waitlist_id=entry.id,
        )
        await session.flush()
        return Answer("late_taken")
    previous = offer.status
    # Se suelta la retención antes de reservar: el hueco es para esta persona.
    offer.status = "filled"
    await session.flush()
    try:
        booking = await _book(session, ctx, offer, entry, now, conversation_id, agent_id, actor)
    except ReservationError:
        offer.status = previous
        cand.status = "late_taken"
        entry.status = "waiting"
        await session.flush()
        return Answer("late_taken")
    cand.status = "late_won" if late else "accepted"
    offer.filled_reservation_id = booking.id
    offer.closed_at = now
    entry.status = "accepted"
    for other in await _candidates(session, offer.id):
        if other.waitlist_id != entry.id and other.status in ("queued", "waiting"):
            if other.status == "waiting":
                await _back_to_waiting(session, other.waitlist_id)
            other.status = "skipped"
    await enqueue_message(
        session,
        tenant_id=ctx.tenant_id,
        kind="offer_won",
        dedupe_key=f"offer_won:{offer.id}",
        reservation_id=booking.id,
        offer_id=offer.id,
    )
    await notify_business(
        session, booking, "reservas.waitlist_accepted", f"reservas.waitlist_accepted:{offer.id}"
    )
    await session.flush()
    return Answer("booked", booking)


async def _book(
    session: AsyncSession,
    ctx: Ctx,
    offer: ReservationOffer,
    entry: ReservationWaitlist,
    now: datetime,
    conversation_id: uuid.UUID | None,
    agent_id: uuid.UUID | None,
    actor: Actor,
) -> Reservation:
    local = ctx.local(offer.starts_at)
    if entry.reservation_id is not None:
        current = await session.get(Reservation, entry.reservation_id)
        if current is not None and current.status in ("pending", "confirmed"):
            moved = await move_booking(
                session,
                ctx,
                current,
                day=local.date(),
                at=local.time().replace(tzinfo=None),
                staff_id=offer.staff_id,
                party_size=None,
                notify=False,
                actor=actor,
                now=now,
                event="waitlist_accepted",
            )
            moved.status = "confirmed"
            moved.wants_earlier = False
            return moved
    req = NewBooking(
        day=local.date(),
        at=local.time().replace(tzinfo=None),
        origin="waitlist",
        channel="whatsapp",
        contact_name=entry.contact_name,
        contact_phone=entry.contact_phone,
        party_size=entry.party_size,
        staff_id=offer.staff_id,
        # Lo que la persona pidió (cabe en el hueco: ``services_candidates``),
        # no el servicio de la cita que se canceló.
        service_id=entry.service_id or offer.service_id,
        customer_id=entry.customer_id,
        conversation_id=conversation_id,
        agent_id=agent_id,
        status="confirmed",
        notify=False,
    )
    booking, _ = await create_booking(session, ctx, req, actor=actor, now=now)
    add_event(session, booking, "waitlist_accepted", actor, {})
    return booking


__all__ = [
    "Answer",
    "NewEntry",
    "Preview",
    "advance",
    "answer",
    "cancel_preview",
    "capacity_candidates",
    "expire",
    "join",
    "offer_manual",
    "open_after_cancel",
    "open_capacity",
    "remove",
    "services_candidates",
    "stop",
]
