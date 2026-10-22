"""Reservas — el dominio (spec 043). Lo llaman la API, las herramientas del
agente y el worker; ninguno decide reglas por su cuenta.

Todo corre en una sesión **ya acotada al cliente** (``tenant_scoped_session`` o
``lite_scope``): la RLS decide qué filas existen. Las escrituras que ocupan un
hueco toman un **candado de transacción** (por persona del equipo en Servicios,
por día en Aforo) y **revalidan** con el mismo motor que ofrece los huecos:
dos peticiones a la vez no se quedan la misma hora (CE-001).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    Customer,
    Reservation,
    ReservationBlock,
    ReservationEvent,
    ReservationOffer,
    ReservationOutbox,
    ReservationService,
    ReservationServiceStaff,
    ReservationSettings,
    ReservationStaff,
    ReservationWaitlist,
    Tenant,
)
from nexus_api.db.models.reservation import LIVE_STATUSES
from nexus_api.services import push_events
from nexus_api.services.business_hours import WEEKDAYS, WeeklyHours, parse_business_hours
from nexus_api.services.reservations import engine

#: Moneda por mercado del negocio (los precios de Servicios no son consumo).
CURRENCY_BY_MARKET = {"CL": "CLP", "AR": "ARS", "MX": "MXN", "CO": "COP", "PE": "PEN", "ES": "EUR"}
#: Ventana del «Llegó»: desde 30 min antes de la hora (diseño).
ARRIVE_EARLY = timedelta(minutes=30)
#: «Llega tarde» a partir de 15 min (diseño).
LATE_AFTER = timedelta(minutes=15)
#: «Pedir confirmación» no se repite antes de 30 min.
ASK_AGAIN_AFTER = timedelta(minutes=30)


class ReservationError(Exception):
    """Un no de negocio. La API lo traduce a ``{status, detail: {code, …}}``; la
    herramienta del agente, a ``refused``."""

    def __init__(self, http_status: int, code: str, **info: Any) -> None:
        super().__init__(code)
        self.http_status = http_status
        self.code = code
        self.info = info


def not_found() -> ReservationError:
    return ReservationError(404, "not_found")


@dataclass(frozen=True)
class Actor:
    kind: str  # agent | person | system | customer
    name: str | None = None


SYSTEM = Actor("system")


@dataclass
class Ctx:
    """Lo que hace falta saber del cliente para decidir: sus ajustes, su zona y
    su horario."""

    tenant_id: uuid.UUID
    settings: ReservationSettings
    tz: ZoneInfo
    hours: WeeklyHours | None
    currency: str
    business_name: str

    @property
    def mode(self) -> str:
        return self.settings.mode

    def day_ranges(self, day: date) -> list[tuple[time, time]]:
        if self.hours is None:
            return []
        return list(self.hours[WEEKDAYS[day.weekday()]])

    def local(self, at: datetime) -> datetime:
        return at.astimezone(self.tz)

    def at(self, day: date, t: time) -> datetime:
        return datetime.combine(day, t, tzinfo=self.tz)

    def today(self, now: datetime) -> date:
        return now.astimezone(self.tz).date()


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


async def load_ctx(session: AsyncSession, tenant_id: uuid.UUID) -> Ctx | None:
    settings = await session.get(ReservationSettings, tenant_id)
    if settings is None:
        return None
    tenant = await session.get(Tenant, tenant_id)
    market = (tenant.market or "CL").upper() if tenant else "CL"
    return Ctx(
        tenant_id=tenant_id,
        settings=settings,
        tz=_zone(tenant.timezone if tenant else None),
        hours=parse_business_hours(tenant.business_hours if tenant else None),
        currency=CURRENCY_BY_MARKET.get(market, "CLP"),
        business_name=tenant.name if tenant else "",
    )


async def lock(session: AsyncSession, key: str) -> None:
    """Candado de transacción: se suelta solo al terminar la transacción."""
    await session.execute(sa.text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": key})


def _staff_lock(ctx: Ctx, staff_id: uuid.UUID) -> str:
    return f"res:{ctx.tenant_id}:staff:{staff_id}"


def _day_lock(ctx: Ctx, day: date) -> str:
    return f"res:{ctx.tenant_id}:day:{day.isoformat()}"


# ── Servicios: equipo, servicios, huecos ────────────────────────────────────


async def active_staff(session: AsyncSession) -> list[ReservationStaff]:
    rows = await session.execute(
        sa.select(ReservationStaff)
        .where(ReservationStaff.archived_at.is_(None))
        .order_by(ReservationStaff.position, ReservationStaff.created_at)
    )
    return list(rows.scalars())


async def staff_for_service(
    session: AsyncSession, service: ReservationService
) -> list[ReservationStaff]:
    staff = await active_staff(session)
    if service.all_staff:
        return staff
    allowed = set(
        (
            await session.execute(
                sa.select(ReservationServiceStaff.staff_id).where(
                    ReservationServiceStaff.service_id == service.id
                )
            )
        ).scalars()
    )
    return [s for s in staff if s.id in allowed]


def staff_ranges(ctx: Ctx, member: ReservationStaff, day: date) -> list[tuple[time, time]]:
    own = parse_business_hours(member.hours) if member.hours else None
    if own is None:
        return ctx.day_ranges(day)
    return list(own[WEEKDAYS[day.weekday()]])


async def _busy_of_staff(
    session: AsyncSession,
    ctx: Ctx,
    staff_id: uuid.UUID,
    day: date,
    *,
    exclude: uuid.UUID | None = None,
) -> list[tuple[datetime, datetime]]:
    lo, hi = ctx.at(day, time(0, 0)), ctx.at(day, time(0, 0)) + timedelta(days=1)
    stmt = sa.select(Reservation.starts_at, Reservation.ends_at).where(
        Reservation.staff_id == staff_id,
        Reservation.status.in_(LIVE_STATUSES),
        Reservation.starts_at < hi,
        Reservation.ends_at > lo,
    )
    if exclude is not None:
        stmt = stmt.where(Reservation.id != exclude)
    busy = [(a, b) for a, b in (await session.execute(stmt)).all()]
    held = await session.execute(
        sa.select(ReservationOffer.starts_at, ReservationOffer.ends_at).where(
            ReservationOffer.staff_id == staff_id,
            ReservationOffer.status == "running",
            ReservationOffer.starts_at < hi,
            ReservationOffer.ends_at > lo,
        )
    )
    busy.extend((a, b) for a, b in held.all())
    busy.extend(await external_busy(session, staff_id, lo, hi))
    return busy


async def external_busy(
    session: AsyncSession, staff_id: uuid.UUID, lo: datetime, hi: datetime
) -> list[tuple[datetime, datetime]]:
    """El «ocupado» de un calendario externo (P3). Sin tabla, nada."""
    has_table = await session.scalar(sa.text("SELECT to_regclass('reservation_busy') IS NOT NULL"))
    if not has_table:
        return []
    rows = await session.execute(
        sa.text(
            "SELECT starts_at, ends_at FROM reservation_busy "
            "WHERE staff_id = :s AND starts_at < :hi AND ends_at > :lo"
        ),
        {"s": staff_id, "lo": lo, "hi": hi},
    )
    return [(a, b) for a, b in rows.all()]


async def services_free(
    session: AsyncSession,
    ctx: Ctx,
    *,
    day: date,
    service: ReservationService,
    staff_ids: Sequence[uuid.UUID] | None,
    not_before: datetime,
    exclude: uuid.UUID | None = None,
) -> dict[str, list[uuid.UUID]]:
    """``HH:MM`` local → personas libres a esa hora para ese servicio."""
    able = await staff_for_service(session, service)
    if staff_ids:
        able = [s for s in able if s.id in set(staff_ids)]
    step = timedelta(minutes=ctx.settings.slot_step_minutes or 30)
    duration = timedelta(minutes=service.duration_minutes)
    out: dict[str, list[uuid.UUID]] = {}
    for member in able:
        busy = await _busy_of_staff(session, ctx, member.id, day, exclude=exclude)
        for at in engine.services_slots(
            day=day,
            tz=ctx.tz,
            business=ctx.day_ranges(day),
            staff=staff_ranges(ctx, member, day),
            duration=duration,
            step=step,
            busy=busy,
            not_before=not_before,
        ):
            out.setdefault(at.strftime("%H:%M"), []).append(member.id)
    return dict(sorted(out.items()))


# ── Aforo: el día ───────────────────────────────────────────────────────────


@dataclass
class CapacityDay:
    slots: list[engine.Slot]
    blocked: set[datetime]
    blocks: list[ReservationBlock]
    people: list[engine.Occupant]
    rules: engine.CapacityRules


def capacity_rules(ctx: Ctx) -> engine.CapacityRules:
    s = ctx.settings
    return engine.CapacityRules(
        seats=int(s.seats or 0),
        hold=int(s.walkin_hold or 0),
        stay=timedelta(minutes=int(s.stay_minutes or 90)),
        max_party=int(s.max_party or 1),
    )


async def capacity_day(session: AsyncSession, ctx: Ctx, day: date) -> CapacityDay:
    rules = capacity_rules(ctx)
    slots = engine.day_slots(ctx.settings.schedule, day, ctx.tz, ctx.day_ranges(day))
    blocks = list(
        (
            await session.execute(
                sa.select(ReservationBlock).where(
                    ReservationBlock.day == day, ReservationBlock.removed_at.is_(None)
                )
            )
        ).scalars()
    )
    blocked = {
        s.at
        for s in slots
        for b in blocks
        if b.from_time <= s.at.timetz().replace(tzinfo=None) <= b.until_time
    }
    lo = ctx.at(day, time(0, 0))
    hi = lo + timedelta(days=1)
    rows = await session.execute(
        sa.select(Reservation).where(
            Reservation.mode == "capacity",
            Reservation.status.in_(LIVE_STATUSES),
            Reservation.starts_at < hi,
            Reservation.ends_at > lo,
        )
    )
    people = [
        engine.Occupant(
            start=r.starts_at, end=r.ends_at, size=r.party_size, status=r.status, id=r.id
        )
        for r in rows.scalars()
    ]
    return CapacityDay(slots=slots, blocked=blocked, blocks=blocks, people=people, rules=rules)


# ── contactos ───────────────────────────────────────────────────────────────


def phone_digits(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    return digits if len(digits) >= 7 else None


async def contact_customer(
    session: AsyncSession, ctx: Ctx, phone: str | None, name: str | None
) -> uuid.UUID | None:
    """El contacto del negocio con ese teléfono, o uno nuevo. Sin teléfono, nadie
    a quien escribir."""
    digits = phone_digits(phone)
    if digits is None:
        return None
    found = await session.scalar(
        sa.select(Customer.id).where(Customer.identifier.in_((digits, f"+{digits}"))).limit(1)
    )
    if found is not None:
        return uuid.UUID(str(found))
    cust = Customer(tenant_id=ctx.tenant_id, identifier=digits, name=name, preferences={})
    session.add(cust)
    await session.flush()
    return cust.id


# ── historial, mensajes al cliente final, avisos al negocio ────────────────


def add_event(
    session: AsyncSession,
    res: Reservation,
    kind: str,
    actor: Actor,
    data: dict[str, Any] | None = None,
) -> None:
    session.add(
        ReservationEvent(
            tenant_id=res.tenant_id,
            reservation_id=res.id,
            kind=kind,
            actor_kind=actor.kind,
            actor_name=actor.name,
            data=data or {},
        )
    )


async def enqueue_message(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    kind: str,
    dedupe_key: str,
    reservation_id: uuid.UUID | None = None,
    offer_id: uuid.UUID | None = None,
    waitlist_id: uuid.UUID | None = None,
) -> None:
    """Lo que hay que decirle al cliente final. Una vez por clave (outbox)."""
    from sqlalchemy.dialects.postgresql import insert

    await session.execute(
        insert(ReservationOutbox)
        .values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            reservation_id=reservation_id,
            offer_id=offer_id,
            waitlist_id=waitlist_id,
            kind=kind,
            dedupe_key=dedupe_key[:160],
        )
        .on_conflict_do_nothing(constraint="uq_reservation_outbox_dedupe")
    )


async def notify_business(
    session: AsyncSession, res: Reservation, kind: str, dedupe_key: str
) -> None:
    await push_events.enqueue(
        session,
        tenant_id=res.tenant_id,
        kind=kind,
        dedupe_key=dedupe_key,
        reservation_id=res.id,
    )


# ── reservas ────────────────────────────────────────────────────────────────


@dataclass
class NewBooking:
    day: date
    at: time
    origin: str  # agent | person | waitlist | walkin
    channel: str  # whatsapp | phone | in_person
    contact_name: str | None = None
    contact_phone: str | None = None
    party_size: int = 1
    staff_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    any_staff: bool = False
    note: str | None = None
    join_waitlist: bool = False
    notify: bool = True
    idempotency_key: str | None = None
    customer_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    status: str | None = None
    #: Las reglas del agente: antelación mínima y máxima, máximo por grupo.
    as_agent: bool = False
    extra_events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)


async def _service(session: AsyncSession, service_id: uuid.UUID | None) -> ReservationService:
    if service_id is None:
        raise ReservationError(422, "service_required")
    svc = await session.get(ReservationService, service_id)
    if svc is None or svc.archived_at is not None:
        raise ReservationError(404, "not_found")
    return svc


def _agent_window(ctx: Ctx, start: datetime, now: datetime) -> None:
    s = ctx.settings
    if start < now + timedelta(minutes=s.agent_min_notice_minutes):
        raise ReservationError(409, "too_soon")
    if start > now + timedelta(days=s.agent_max_days_ahead):
        raise ReservationError(409, "too_far")


async def create_booking(
    session: AsyncSession, ctx: Ctx, req: NewBooking, *, actor: Actor, now: datetime
) -> tuple[Reservation, bool]:
    """Crea la reserva o devuelve la que ya creó esa clave. ``(reserva, repetida)``."""
    if req.idempotency_key:
        prior = await session.scalar(
            sa.select(Reservation).where(Reservation.idempotency_key == req.idempotency_key)
        )
        if prior is not None:
            # Una clave nunca entrega la reserva de otra persona (/cso CSO-001).
            if req.customer_id is not None and prior.customer_id != req.customer_id:
                raise ReservationError(409, "idempotency_conflict")
            return prior, True
    if ctx.hours is None:
        raise ReservationError(409, "hours_missing")
    walkin = req.origin == "walkin"
    start = ctx.at(req.day, req.at)
    if req.as_agent:
        _agent_window(ctx, start, now)

    res = Reservation(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        mode=ctx.mode,
        origin=req.origin,
        channel=req.channel,
        created_by_kind=actor.kind,
        created_by_name=actor.name,
        contact_name=(req.contact_name or "").strip()[:120] or None,
        contact_phone=(req.contact_phone or "").strip()[:32] or None,
        note=(req.note or "").strip()[:500] or None,
        idempotency_key=req.idempotency_key,
        conversation_id=req.conversation_id,
        agent_id=req.agent_id,
        version=1,
    )
    if ctx.mode == "services":
        svc = await _service(session, req.service_id)
        able = await staff_for_service(session, svc)
        candidates = [s.id for s in able if req.staff_id is None or s.id == req.staff_id]
        if req.staff_id is not None and not candidates:
            raise ReservationError(404, "not_found")
        not_before = now + (
            timedelta(minutes=ctx.settings.agent_min_notice_minutes)
            if req.as_agent
            else timedelta()
        )
        chosen: uuid.UUID | None = None
        for staff_id in candidates:
            await lock(session, _staff_lock(ctx, staff_id))
            free = await services_free(
                session, ctx, day=req.day, service=svc, staff_ids=[staff_id], not_before=not_before
            )
            if staff_id in free.get(req.at.strftime("%H:%M"), []):
                chosen = staff_id
                break
        if chosen is None:
            raise ReservationError(409, "slot_taken", first_fit=None)
        res.staff_id = chosen
        res.service_id = svc.id
        res.service_name = svc.name
        res.price_minor = svc.price_minor
        res.currency = svc.currency
        res.party_size = 1
        res.any_staff = req.any_staff or req.staff_id is None
        res.starts_at = start
        res.ends_at = start + timedelta(minutes=svc.duration_minutes)
    else:
        n = max(1, int(req.party_size))
        rules = capacity_rules(ctx)
        if req.as_agent and n > rules.max_party:
            raise ReservationError(409, "too_large", max_party=rules.max_party)
        await lock(session, _day_lock(ctx, req.day))
        day = await capacity_day(session, ctx, req.day)
        fit = engine.capacity_fit(
            day.slots, day.blocked, day.people, rules, start, n, now=now, walkin=walkin
        )
        if not fit.fits:
            nxt = engine.first_fit(
                day.slots, day.blocked, day.people, rules, n, now=now, after=start, walkin=walkin
            )
            raise ReservationError(
                409,
                "slot_taken",
                why=fit.why,
                first_fit={"date": req.day.isoformat(), "time": nxt.strftime("%H:%M")}
                if nxt
                else None,
            )
        res.party_size = n
        res.starts_at = start
        res.ends_at = start + rules.stay

    if req.customer_id is not None:
        res.customer_id = req.customer_id
    else:
        res.customer_id = await contact_customer(session, ctx, res.contact_phone, res.contact_name)
    if walkin:
        res.status = "arrived"
        res.arrived_at = now
    elif req.status is not None:
        res.status = req.status
    elif req.origin == "agent" and ctx.settings.confirm_enabled:
        res.status = "pending"
    else:
        res.status = "confirmed"
    session.add(res)
    await session.flush()

    add_event(session, res, "created", actor, {"channel": res.channel, "origin": res.origin})
    for kind, data in req.extra_events:
        add_event(session, res, kind, actor, data)
    if req.join_waitlist and ctx.mode == "services" and ctx.settings.waitlist_enabled:
        res.wants_earlier = True
        session.add(
            ReservationWaitlist(
                tenant_id=ctx.tenant_id,
                mode="services",
                status="waiting",
                customer_id=res.customer_id,
                contact_name=res.contact_name,
                contact_phone=res.contact_phone,
                service_id=res.service_id,
                staff_id=None if res.any_staff else res.staff_id,
                reservation_id=res.id,
                joined_by_kind="agent" if actor.kind == "agent" else "person",
                joined_by_name=actor.name,
            )
        )
        add_event(session, res, "waitlist_joined", actor)
    if req.origin == "person" and req.notify and res.contact_phone:
        await enqueue_message(
            session,
            tenant_id=ctx.tenant_id,
            kind="confirmation",
            dedupe_key=f"confirmation:{res.id}",
            reservation_id=res.id,
        )
    if req.origin == "agent":
        await notify_business(
            session, res, "reservas.agent_change", f"reservas.agent_change:{res.id}:1"
        )
    await session.flush()
    return res, False


async def get_booking(
    session: AsyncSession, booking_id: uuid.UUID, *, lock: bool = False
) -> Reservation:
    """La reserva por id. ``lock``: bajo candado de fila y releída, para
    comprobar la versión (``If-Match``) contra lo que de verdad hay."""
    res = await session.get(
        Reservation, booking_id, with_for_update=lock or None, populate_existing=lock
    )
    if res is None:
        raise not_found()
    return res


async def _fresh(session: AsyncSession, res: Reservation) -> None:
    """Relee la fila bajo candado antes de escribir en ella. Entre la lectura y
    la escritura otra transacción pudo cambiarla (el cron que libera, otra
    persona); sin esto, la escritura la pisaba: una confirmación resucitaba una
    reserva ya liberada y su sitio, ya ofrecido. El cron coge las filas con
    ``SKIP LOCKED``, así que lo que la API tiene cogido lo deja para la pasada
    siguiente."""
    await session.refresh(res, with_for_update=True)


def check_version(res: Reservation, expected: int | None) -> None:
    if expected is not None and res.version != expected:
        raise ReservationError(412, "stale", version=res.version)


def _bump(res: Reservation) -> None:
    res.version = (res.version or 1) + 1


def _local_hm(ctx: Ctx, at: datetime) -> dict[str, str]:
    loc = ctx.local(at)
    return {"date": loc.date().isoformat(), "start": loc.strftime("%H:%M")}


async def move_booking(
    session: AsyncSession,
    ctx: Ctx,
    res: Reservation,
    *,
    day: date,
    at: time,
    staff_id: uuid.UUID | None,
    party_size: int | None,
    notify: bool,
    actor: Actor,
    now: datetime,
    as_agent: bool = False,
    event: str = "moved",
) -> Reservation:
    await _fresh(session, res)
    if "move" not in allowed_actions(ctx, res, now):
        raise ReservationError(409, "invalid_transition", status=res.status)
    start = ctx.at(day, at)
    if as_agent:
        _agent_window(ctx, start, now)
    before = _local_hm(ctx, res.starts_at)
    if res.mode == "services":
        svc = await _service(session, res.service_id)
        target = staff_id or res.staff_id
        assert target is not None
        await lock(session, _staff_lock(ctx, target))
        not_before = now + (
            timedelta(minutes=ctx.settings.agent_min_notice_minutes) if as_agent else timedelta()
        )
        free = await services_free(
            session,
            ctx,
            day=day,
            service=svc,
            staff_ids=[target],
            not_before=not_before,
            exclude=res.id,
        )
        if target not in free.get(at.strftime("%H:%M"), []):
            raise ReservationError(409, "slot_taken", first_fit=None)
        res.staff_id = target
        res.starts_at = start
        res.ends_at = start + timedelta(minutes=svc.duration_minutes)
    else:
        n = party_size or res.party_size
        rules = capacity_rules(ctx)
        if as_agent and n > rules.max_party:
            raise ReservationError(409, "too_large", max_party=rules.max_party)
        await lock(session, _day_lock(ctx, day))
        cap = await capacity_day(session, ctx, day)
        fit = engine.capacity_fit(
            cap.slots, cap.blocked, cap.people, rules, start, n, now=now, exclude=res.id
        )
        if not fit.fits:
            nxt = engine.first_fit(
                cap.slots, cap.blocked, cap.people, rules, n, now=now, after=start, exclude=res.id
            )
            raise ReservationError(
                409,
                "slot_taken",
                why=fit.why,
                first_fit={"date": day.isoformat(), "time": nxt.strftime("%H:%M")} if nxt else None,
            )
        res.party_size = n
        res.starts_at = start
        res.ends_at = start + rules.stay
    if res.status != "pending":
        res.status = "confirmed"
    _bump(res)
    notified = bool(notify and res.contact_phone)
    add_event(
        session,
        res,
        event,
        actor,
        {"from": before, "to": _local_hm(ctx, res.starts_at), "notified": notified},
    )
    if notified:
        await enqueue_message(
            session,
            tenant_id=ctx.tenant_id,
            kind="moved",
            dedupe_key=f"moved:{res.id}:{res.version}",
            reservation_id=res.id,
        )
    if actor.kind == "agent":
        await notify_business(
            session, res, "reservas.agent_change", f"reservas.agent_change:{res.id}:{res.version}"
        )
    await session.flush()
    return res


async def cancel_booking(
    session: AsyncSession,
    ctx: Ctx,
    res: Reservation,
    *,
    by: str,
    actor: Actor,
    now: datetime,
    notify: bool = True,
    cause: str | None = None,
    check_allowed: bool = True,
) -> Reservation:
    await _fresh(session, res)
    if check_allowed and "cancel" not in allowed_actions(ctx, res, now):
        raise ReservationError(409, "invalid_transition", status=res.status)
    res.status = "cancelled"
    res.cancelled_at = now
    res.cancelled_by = by
    res.cancel_cause = cause
    _bump(res)
    notified = bool(notify and res.contact_phone and by != "customer")
    add_event(session, res, "cancelled", actor, {"by": by, "cause": cause, "notified": notified})
    if notified:
        await enqueue_message(
            session,
            tenant_id=ctx.tenant_id,
            kind="cancelled",
            dedupe_key=f"cancelled:{res.id}",
            reservation_id=res.id,
        )
    # Quien quería adelantar esta cita ya no espera nada.
    await session.execute(
        sa.update(ReservationWaitlist)
        .where(
            ReservationWaitlist.reservation_id == res.id,
            ReservationWaitlist.status.in_(("waiting", "offered")),
        )
        .values(status="removed")
    )
    if by != "business" and ctx.today(now) == ctx.local(res.starts_at).date():
        await notify_business(
            session, res, "reservas.cancelled_today", f"reservas.cancelled_today:{res.id}"
        )
    await session.flush()
    return res


# ── transiciones de estado ──────────────────────────────────────────────────


def allowed_actions(ctx: Ctx, res: Reservation, now: datetime) -> list[str]:
    """Las acciones que la API acepta ahora mismo (``Booking.allowed``)."""
    out: list[str] = []
    today = ctx.today(now) == ctx.local(res.starts_at).date()
    future = res.starts_at > now
    open_ = res.status in ("pending", "confirmed")
    if res.status == "pending" and future:
        out.append("confirm")
    if open_ and future and res.origin != "walkin":
        out.extend(["move", "cancel"])
    if (
        res.status == "pending"
        and future
        and res.contact_phone
        and (
            res.confirmation_requested_at is None
            or now - res.confirmation_requested_at >= ASK_AGAIN_AFTER
        )
    ):
        out.append("request_confirmation")
    if res.mode == "capacity" and open_ and today and now >= res.starts_at - ARRIVE_EARLY:
        out.append("arrive")
    if open_ and today and now >= res.starts_at:
        out.append("noshow")
    if res.status in ("arrived", "noshow") and today and res.origin != "walkin":
        out.append("undo")
    return out


async def transition(
    session: AsyncSession,
    ctx: Ctx,
    res: Reservation,
    action: str,
    *,
    actor: Actor,
    now: datetime,
) -> Reservation:
    await _fresh(session, res)
    if action not in allowed_actions(ctx, res, now):
        raise ReservationError(409, "invalid_transition", status=res.status)
    if action == "confirm":
        res.status = "confirmed"
        add_event(session, res, "confirmed", actor)
    elif action == "arrive":
        res.status = "arrived"
        res.arrived_at = now
        add_event(session, res, "arrived", actor)
    elif action == "noshow":
        res.status = "noshow"
        add_event(session, res, "noshow", actor)
    elif action == "undo":
        res.status = "confirmed"
        res.arrived_at = None
        add_event(session, res, "undone", actor)
    elif action == "request_confirmation":
        res.confirmation_requested_at = now
        add_event(session, res, "confirmation_requested", actor)
        await enqueue_message(
            session,
            tenant_id=ctx.tenant_id,
            kind="ask_confirmation",
            dedupe_key=f"ask:{res.id}:{int(now.timestamp())}",
            reservation_id=res.id,
        )
    else:  # pragma: no cover - la lista de arriba es cerrada
        raise ReservationError(409, "invalid_transition", status=res.status)
    _bump(res)
    await session.flush()
    return res


def late_minutes(res: Reservation, now: datetime) -> int | None:
    if res.mode != "capacity" or res.status not in ("pending", "confirmed"):
        return None
    if res.starts_at + LATE_AFTER <= now < res.ends_at:
        return int((now - res.starts_at).total_seconds() // 60)
    return None


__all__ = [
    "SYSTEM",
    "Actor",
    "CapacityDay",
    "Ctx",
    "NewBooking",
    "ReservationError",
    "add_event",
    "allowed_actions",
    "cancel_booking",
    "capacity_day",
    "capacity_rules",
    "check_version",
    "contact_customer",
    "create_booking",
    "enqueue_message",
    "get_booking",
    "late_minutes",
    "load_ctx",
    "lock",
    "move_booking",
    "not_found",
    "notify_business",
    "services_free",
    "staff_for_service",
    "transition",
]
