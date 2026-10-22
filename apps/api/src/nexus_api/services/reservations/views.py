"""Reservas — lo que se lee (spec 043): la forma ``Booking`` del contrato, el
listado, la ocupación por franja y el resumen del Panel y de la app.

La forma sale de aquí y de ningún otro sitio: la API web y la de la app son la
misma ruta, y ``allowed`` (las acciones válidas ahora) lo calcula el servidor
para que ninguna pantalla reescriba las reglas.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    Conversation,
    Reservation,
    ReservationEvent,
    ReservationService,
    ReservationStaff,
    ReservationWaitlist,
)
from nexus_api.db.models.reservation import LIVE_STATUSES
from nexus_api.services.reservations import engine
from nexus_api.services.reservations.core import (
    Ctx,
    active_staff,
    allowed_actions,
    capacity_day,
    late_minutes,
    staff_ranges,
)

MAX_ITEMS = 1000


def _hm(t: datetime) -> str:
    return t.strftime("%H:%M")


async def _names(
    session: AsyncSession, rows: Sequence[Reservation]
) -> tuple[dict[uuid.UUID, str], dict[uuid.UUID, ReservationService]]:
    staff_ids = {r.staff_id for r in rows if r.staff_id}
    service_ids = {r.service_id for r in rows if r.service_id}
    staff: dict[uuid.UUID, str] = {}
    services: dict[uuid.UUID, ReservationService] = {}
    if staff_ids:
        for sid, name in (
            await session.execute(
                sa.select(ReservationStaff.id, ReservationStaff.name).where(
                    ReservationStaff.id.in_(staff_ids)
                )
            )
        ).all():
            staff[sid] = str(name)
    if service_ids:
        for svc in (
            await session.execute(
                sa.select(ReservationService).where(ReservationService.id.in_(service_ids))
            )
        ).scalars():
            services[svc.id] = svc
    return staff, services


async def _visible_conversations(
    session: AsyncSession, rows: Sequence[Reservation]
) -> dict[uuid.UUID, uuid.UUID]:
    """Para cada contacto, su conversación más reciente que la Bandeja enseña
    (spec 045): nunca un id que la Bandeja respondería con 404."""
    customers = {r.customer_id for r in rows if r.customer_id}
    if not customers:
        return {}
    ranked = (
        sa.select(
            Conversation.customer_id,
            Conversation.id,
            sa.func.row_number()
            .over(
                partition_by=Conversation.customer_id,
                order_by=Conversation.last_message_at.desc().nulls_last(),
            )
            .label("rn"),
        )
        .where(Conversation.customer_id.in_(customers), Conversation.attended_at.is_not(None))
        .subquery()
    )
    rows_ = await session.execute(
        sa.select(ranked.c.customer_id, ranked.c.id).where(ranked.c.rn == 1)
    )
    return {cid: conv for cid, conv in rows_.all()}


def booking_out(
    ctx: Ctx,
    r: Reservation,
    *,
    now: datetime,
    staff: dict[uuid.UUID, str],
    services: dict[uuid.UUID, ReservationService],
    conversations: dict[uuid.UUID, uuid.UUID],
) -> dict[str, Any]:
    start, end = ctx.local(r.starts_at), ctx.local(r.ends_at)
    svc = services.get(r.service_id) if r.service_id else None
    return {
        "id": r.id,
        "mode": r.mode,
        "status": r.status,
        "starts_at": r.starts_at,
        "ends_at": r.ends_at,
        "local": {"date": start.date().isoformat(), "start": _hm(start), "end": _hm(end)},
        "party_size": r.party_size,
        "staff": {"id": r.staff_id, "name": staff.get(r.staff_id, "—")} if r.staff_id else None,
        "service": {
            "id": r.service_id,
            "name": r.service_name or (svc.name if svc else "—"),
            "duration_minutes": int((r.ends_at - r.starts_at).total_seconds() // 60),
        }
        if r.service_id
        else None,
        "price": {"amount_minor": r.price_minor, "currency": r.currency or ctx.currency}
        if r.mode == "services" and r.price_minor is not None
        else None,
        "contact": {
            "name": r.contact_name,
            "phone": r.contact_phone,
            "conversation_id": conversations.get(r.customer_id) if r.customer_id else None,
        },
        "origin": r.origin,
        "channel": r.channel,
        "created_by": {"kind": r.created_by_kind, "name": r.created_by_name},
        "created_at": r.created_at,
        "note": r.note,
        "arrived_at": r.arrived_at,
        "cancelled": {"at": r.cancelled_at, "by": r.cancelled_by, "cause": r.cancel_cause}
        if r.status == "cancelled"
        else None,
        "wants_earlier": r.wants_earlier,
        "any_staff": r.any_staff,
        "late_minutes": late_minutes(r, now),
        "clash": None,
        "allowed": allowed_actions(ctx, r, now),
        "version": r.version,
    }


async def bookings_out(
    session: AsyncSession, ctx: Ctx, rows: Sequence[Reservation], *, now: datetime, with_inbox: bool
) -> list[dict[str, Any]]:
    staff, services = await _names(session, rows)
    conversations = await _visible_conversations(session, rows) if with_inbox else {}
    out = [
        booking_out(ctx, r, now=now, staff=staff, services=services, conversations=conversations)
        for r in rows
    ]
    from nexus_api.services.reservations.calendar import clashes_for

    clashes = await clashes_for(session, ctx, rows)
    for item in out:
        item["clash"] = clashes.get(item["id"])
    return out


async def events_out(session: AsyncSession, booking_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = await session.execute(
        sa.select(ReservationEvent)
        .where(ReservationEvent.reservation_id == booking_id)
        .order_by(ReservationEvent.created_at, ReservationEvent.id)
    )
    return [
        {
            "kind": e.kind,
            "at": e.created_at,
            "actor": {"kind": e.actor_kind, "name": e.actor_name},
            "data": e.data or {},
        }
        for e in rows.scalars()
    ]


async def list_bookings(
    session: AsyncSession,
    ctx: Ctx,
    *,
    start: date,
    end: date,
    statuses: Sequence[str] = (),
    origins: Sequence[str] = (),
    staff_id: uuid.UUID | None = None,
    q: str | None = None,
) -> tuple[list[Reservation], bool]:
    lo = ctx.at(start, time(0, 0))
    hi = ctx.at(end, time(0, 0)) + timedelta(days=1)
    stmt = sa.select(Reservation).where(Reservation.starts_at >= lo, Reservation.starts_at < hi)
    if statuses:
        stmt = stmt.where(Reservation.status.in_(statuses))
    if origins:
        stmt = stmt.where(Reservation.origin.in_(origins))
    if staff_id is not None:
        stmt = stmt.where(Reservation.staff_id == staff_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            sa.or_(Reservation.contact_name.ilike(like), Reservation.contact_phone.ilike(like))
        )
    rows = list(
        (await session.execute(stmt.order_by(Reservation.starts_at).limit(MAX_ITEMS + 1))).scalars()
    )
    return rows[:MAX_ITEMS], len(rows) > MAX_ITEMS


def closed_days(ctx: Ctx, start: date, end: date) -> list[str]:
    out: list[str] = []
    d = start
    while d <= end:
        if not ctx.day_ranges(d):
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


async def next_booking_of(
    session: AsyncSession, ctx: Ctx, customer_id: uuid.UUID, now: datetime
) -> dict[str, Any] | None:
    r = await session.scalar(
        sa.select(Reservation)
        .where(
            Reservation.customer_id == customer_id,
            Reservation.status.in_(("pending", "confirmed")),
            Reservation.starts_at > now,
        )
        .order_by(Reservation.starts_at)
        .limit(1)
    )
    if r is None:
        return None
    start, end = ctx.local(r.starts_at), ctx.local(r.ends_at)
    return {
        "id": r.id,
        "starts_at": r.starts_at,
        "local": {"date": start.date().isoformat(), "start": _hm(start), "end": _hm(end)},
        "status": r.status,
        "service_name": r.service_name,
        "party_size": r.party_size if r.mode == "capacity" else None,
    }


# ── Aforo: ocupación por franja ─────────────────────────────────────────────


async def occupancy(
    session: AsyncSession, ctx: Ctx, *, start: date, end: date, now: datetime
) -> dict[str, Any]:
    days: list[dict[str, Any]] = []
    d = start
    rules = None
    while d <= end:
        cap = await capacity_day(session, ctx, d)
        rules = cap.rules
        rows = list(
            (
                await session.execute(
                    sa.select(Reservation).where(
                        Reservation.mode == "capacity",
                        Reservation.starts_at >= ctx.at(d, time(0, 0)),
                        Reservation.starts_at < ctx.at(d, time(0, 0)) + timedelta(days=1),
                        Reservation.status.in_((*LIVE_STATUSES, "done")),
                    )
                )
            ).scalars()
        )
        block_of = {
            s.at: b
            for s in cap.slots
            for b in cap.blocks
            if b.from_time <= s.at.timetz().replace(tzinfo=None) <= b.until_time
        }
        slots = []
        for s in cap.slots:
            arriving = [r for r in rows if r.starts_at == s.at and r.status != "done"]
            block = block_of.get(s.at)
            slots.append(
                {
                    "time": _hm(s.at),
                    "shift": s.shift,
                    "present": engine.presence(cap.people, s.at),
                    "arriving": sum(r.party_size for r in arriving),
                    "arrived": sum(r.party_size for r in arriving if r.status == "arrived"),
                    "pending": sum(r.party_size for r in arriving if r.status == "pending"),
                    "blocked": {"id": block.id, "label": block.label} if block else None,
                    "past": s.at < now,
                }
            )
        days.append({"date": d.isoformat(), "closed": not cap.slots, "slots": slots})
        d += timedelta(days=1)
    return {
        "seats": rules.seats if rules else int(ctx.settings.seats or 0),
        "walkin_hold": rules.hold if rules else int(ctx.settings.walkin_hold or 0),
        "stay_minutes": int(ctx.settings.stay_minutes or 0),
        "days": days,
    }


# ── resumen ────────────────────────────────────────────────────────────────


def _week(now_local: datetime) -> tuple[date, date]:
    monday = now_local.date() - timedelta(days=now_local.weekday())
    return monday, monday + timedelta(days=6)


def _pct(part: float, whole: float) -> float | None:
    return round(100 * part / whole, 1) if whole > 0 else None


async def _rows_between(
    session: AsyncSession, ctx: Ctx, start: date, end: date
) -> list[Reservation]:
    lo = ctx.at(start, time(0, 0))
    hi = ctx.at(end, time(0, 0)) + timedelta(days=1)
    return list(
        (
            await session.execute(
                sa.select(Reservation).where(
                    Reservation.starts_at >= lo, Reservation.starts_at < hi
                )
            )
        ).scalars()
    )


async def summary(
    session: AsyncSession, ctx: Ctx, *, now: datetime, with_inbox: bool
) -> dict[str, Any]:
    local_now = ctx.local(now)
    today = local_now.date()
    errors: list[str] = []
    out: dict[str, Any] = {"mode": ctx.mode, "clashes": 0, "errors": errors}

    todays = await _rows_between(session, ctx, today, today)
    not_cancelled = [r for r in todays if r.status != "cancelled"]
    live_today = [r for r in todays if r.status in ("pending", "confirmed")]
    upcoming = sorted((r for r in live_today if r.starts_at >= now), key=lambda r: r.starts_at)
    out["today"] = {
        "date": today.isoformat(),
        "bookings": len(not_cancelled),
        "confirmed": sum(1 for r in not_cancelled if r.status in ("confirmed", "arrived", "done")),
        "pending": sum(1 for r in not_cancelled if r.status == "pending"),
        "next_at": upcoming[0].starts_at if upcoming else None,
        "people": None,
        "inside_now": None,
        "arriving_next_hour": None,
        "seats": None,
    }
    if ctx.mode == "capacity":
        out["today"]["seats"] = ctx.settings.seats
        out["today"]["people"] = sum(r.party_size for r in not_cancelled if r.status != "noshow")
        out["today"]["inside_now"] = sum(
            r.party_size for r in todays if r.status == "arrived" and r.starts_at <= now < r.ends_at
        )
        out["today"]["arriving_next_hour"] = sum(
            r.party_size for r in live_today if now < r.starts_at <= now + timedelta(hours=1)
        )

    try:
        monday, sunday = _week(local_now)
        week = [
            r for r in await _rows_between(session, ctx, monday, sunday) if r.status != "cancelled"
        ]
        agent = sum(1 for r in week if r.origin == "agent")
        if ctx.mode == "services":
            booked = sum(
                (r.ends_at - r.starts_at).total_seconds() / 3600
                for r in week
                if r.status != "noshow"
            )
            open_hours = 0.0
            staff = await active_staff(session)
            d = monday
            while d <= sunday:
                for member in staff:
                    for a, b in staff_ranges(ctx, member, d):
                        for lo, hi in engine.intersect([(a, b)], ctx.day_ranges(d)):
                            open_hours += (
                                datetime.combine(d, hi) - datetime.combine(d, lo)
                            ).total_seconds() / 3600
                d += timedelta(days=1)
            occupancy_pct = _pct(booked, open_hours)
        else:
            stay_h = (ctx.settings.stay_minutes or 0) / 60
            booked = sum(r.party_size * stay_h for r in week if r.status != "noshow")
            seats = ctx.settings.seats or 0
            step_h = int((ctx.settings.schedule or {}).get("step_minutes", 60)) / 60
            service_hours = 0.0
            d = monday
            while d <= sunday:
                service_hours += (
                    len(engine.day_slots(ctx.settings.schedule, d, ctx.tz, ctx.day_ranges(d)))
                    * step_h
                )
                d += timedelta(days=1)
            occupancy_pct = _pct(booked, seats * service_hours)
        out["week"] = {
            "occupancy_pct": occupancy_pct,
            "agent_share_pct": _pct(agent, len(week)),
        }
    except Exception:  # parcial: el bloque se dice ilegible, el resto se pinta
        out["week"] = None
        errors.append("week")

    try:
        first = today.replace(day=1)
        month = await _rows_between(session, ctx, first, today)
        done = sum(1 for r in month if r.status == "done")
        noshow = sum(1 for r in month if r.status == "noshow")
        recovered: int | None = None
        if ctx.settings.waitlist_enabled:
            recovered = int(
                await session.scalar(
                    sa.select(sa.func.count())
                    .select_from(ReservationEvent)
                    .where(
                        ReservationEvent.kind == "waitlist_accepted",
                        ReservationEvent.created_at >= ctx.at(first, time(0, 0)),
                    )
                )
                or 0
            )
        out["month"] = {"noshow_pct": _pct(noshow, done + noshow), "recovered": recovered}
    except Exception:  # parcial
        out["month"] = None
        errors.append("month")

    waiting = await session.scalar(
        sa.select(sa.func.count())
        .select_from(ReservationWaitlist)
        .where(ReservationWaitlist.status.in_(("waiting", "offered")))
    )
    out["waitlist"] = {"waiting": int(waiting or 0)}
    out["upcoming"] = await bookings_out(session, ctx, upcoming[:4], now=now, with_inbox=with_inbox)
    from nexus_api.services.reservations.calendar import clash_count

    out["clashes"] = await clash_count(session, ctx, now)
    return out


__all__ = [
    "booking_out",
    "bookings_out",
    "closed_days",
    "events_out",
    "list_bookings",
    "next_booking_of",
    "occupancy",
    "summary",
]
