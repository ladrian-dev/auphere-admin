"""reservas.* — el agente reserva en la agenda que el negocio ve (spec 043).

Todas sobre ``nexus_api.services.reservations``: las mismas reglas que la consola
y la app (horario del negocio, aforo y guardadas, bloqueos, ofertas en curso) y
la misma revalidación con candado al escribir.

Dos ejes de aislamiento, como ``booking.*``: el negocio lo resuelve la RLS
(``tool_session``); **la persona, el turno** (``current_customer_or_refuse``).
Ninguna herramienta acepta un cliente. Una reserva de otra persona se lee igual
que una que no existe.

Y un tercero desde la spec 047 (requisito 11.4, garantía 9): **los servicios son
los del agente del turno** —el que contesta en la conversación (``_turn``): el del
número o, si Recepción la derivó, el de destino; nunca un argumento del modelo—. ``services`` solo lista los suyos, y buscar huecos,
reservar o apuntarse a la espera con un servicio de su hermano responde
``not_offered``.

El servicio y la persona van por id o por nombre (fallo
``la-reserva-del-turno-siguiente-pierde-los-ids``): entre turnos el agente solo
conserva el texto, y el id de un turno no llega al siguiente. ``_pick_service`` y
``_pick_staff`` los resuelven contra el catálogo vivo del cliente (la RLS) y el
equipo activo; lo que no se resuelve —un id inventado, un nombre que no está o que
empata— es ``unknown_*`` / ``ambiguous_*`` con las opciones de **este** agente para
reintentar, nunca un error ni un «ocupado». Un servicio de la vecina, por id o por
nombre, es uno que no existe.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Any

import sqlalchemy as sa
from nexus_api.core.tenant_context import get_current_customer, require_current_tenant
from nexus_api.db.models import (
    Agent,
    ClientAccess,
    Conversation,
    Customer,
    Reservation,
    ReservationService,
    ReservationStaff,
)
from nexus_api.services.business import services_catalog
from nexus_api.services.reception import agent_for_conversation
from nexus_api.services.reservations import waitlist
from nexus_api.services.reservations.core import (
    NO_STAFF,
    Actor,
    Ctx,
    NewBooking,
    ReservationError,
    active_staff,
    add_event,
    cancel_booking,
    capacity_day,
    create_booking,
    load_ctx,
    move_booking,
    services_free,
    staff_for_service,
    transition,
)
from nexus_api.services.reservations.engine import capacity_fit, first_fit
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_mcp._customer import current_customer_or_refuse
from nexus_mcp._db import tool_session
from nexus_mcp.base import InputModel, OutputModel, ToolBase, ToolError
from nexus_mcp.servers.reservas.names import (
    AMBIGUOUS_SERVICE,
    AMBIGUOUS_STAFF,
    UNKNOWN_SERVICE,
    UNKNOWN_STAFF,
    fold,
    matches,
)
from nexus_mcp.servers.reservas.schemas import (
    AnswerOfferInput,
    AnswerOfferOutput,
    BookingBrief,
    CancelInput,
    CancelOutput,
    ConfirmAttendanceInput,
    ConfirmAttendanceOutput,
    CreateInput,
    CreateOutput,
    FindSlotsInput,
    FindSlotsOutput,
    JoinWaitlistInput,
    JoinWaitlistOutput,
    ListMineInput,
    ListMineOutput,
    Money,
    RescheduleInput,
    RescheduleOutput,
    ServiceItem,
    ServiceRef,
    ServicesInput,
    ServicesOutput,
    SlotOut,
    StaffRef,
)

NOT_ACTIVE = "Reservas no está activo para este negocio."
REFUSALS = {
    "slot_taken",
    "too_large",
    "too_soon",
    "too_far",
    "closed",
    "hours_missing",
    "not_bookable",
    "not_offered",
    "no_staff",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _hm(raw: str) -> time:
    h, m = raw.split(":")
    return time(int(h), int(m))


async def _ctx(session: AsyncSession) -> Ctx:
    """Los ajustes del cliente, solo con el módulo activo."""
    tenant_id = require_current_tenant()
    access = await session.get(ClientAccess, tenant_id)
    # Spec 048 (decision 16): the module on the list is enough; whether the
    # client's people can sign in (``enabled``) is not the agent's business.
    if access is None or not access.reservas_on:
        raise ToolError(NOT_ACTIVE)
    ctx = await load_ctx(session, tenant_id)
    if ctx is None:
        raise ToolError(NOT_ACTIVE)
    return ctx


async def _brief(session: AsyncSession, ctx: Ctx, r: Reservation) -> BookingBrief:
    staff_name: str | None = None
    if r.staff_id:
        staff = await session.get(ReservationStaff, r.staff_id)
        staff_name = staff.name if staff else None
    start, end = ctx.local(r.starts_at), ctx.local(r.ends_at)
    return BookingBrief(
        id=r.id,
        status=r.status,
        date=start.date(),
        start=start.strftime("%H:%M"),
        end=end.strftime("%H:%M"),
        starts_at=r.starts_at,
        party_size=r.party_size,
        service_name=r.service_name,
        staff_name=staff_name,
        note=r.note,
    )


async def _mine(
    session: AsyncSession, booking_id: uuid.UUID, customer_id: uuid.UUID
) -> Reservation:
    res = await session.get(Reservation, booking_id)
    if res is None or res.customer_id != customer_id:
        raise ToolError(f"booking {booking_id} not found for this customer")
    return res


async def _contact(session: AsyncSession, customer_id: uuid.UUID) -> tuple[str | None, str | None]:
    cust = await session.get(Customer, customer_id)
    if cust is None:
        return None, None
    digits = "".join(ch for ch in cust.identifier if ch.isdigit())
    return cust.name, (f"+{digits}" if len(digits) >= 7 else None)


async def _turn(
    session: AsyncSession, customer_id: uuid.UUID, conversation_id: uuid.UUID | None
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """La conversación del turno (la que nombra el runtime, o la última de esta
    persona) y el agente que contesta en ella."""
    conv: Conversation | None = None
    if conversation_id is not None:
        conv = await session.get(Conversation, conversation_id)
        if conv is not None and conv.customer_id != customer_id:
            conv = None
    if conv is None:
        conv = await session.scalar(
            sa.select(Conversation)
            .where(Conversation.customer_id == customer_id)
            .order_by(Conversation.last_message_at.desc().nulls_last())
            .limit(1)
        )
    if conv is None:
        return None, None
    # Spec 047 (requisito 53): el que contesta en la conversación —el del número
    # o, si Recepción la derivó, el de destino— con sus servicios.
    return conv.id, await agent_for_conversation(session, conv)


async def _turn_agent(session: AsyncSession) -> uuid.UUID | None:
    """El agente del turno: el que contesta en la conversación de la persona. Sin
    persona (una prueba sin turno), ``None``: el agente principal."""
    customer_id = get_current_customer()
    if customer_id is None:
        return None
    _conv, agent_id = await _turn(session, customer_id, None)
    return agent_id


@dataclass
class _Pick:
    """El servicio y la persona que nombró el modelo, resueltos; o por qué no, con
    las opciones para reintentar en el mismo turno."""

    service: ReservationService | None = None
    staff_id: uuid.UUID | None = None
    refused: str | None = None
    services: list[ServiceRef] = field(default_factory=list)
    staff: list[StaffRef] = field(default_factory=list)


def _one(found: list[Any], wanted: str, allowed: set[uuid.UUID]) -> tuple[Any, list[Any]]:
    """De lo que nombra ``wanted`` (``matches``), lo que se puede usar: ``(el elegido,
    [])`` o ``(None, los empatados)``. Uno solo que se puede usar es ese si es el único
    que nombra o si se llama exactamente así: un «Corte» del hermano no empata con el
    «Corte» propio, que es el que este agente reserva."""
    usable = [x for x in found if x.id in allowed]
    if len(usable) == 1 and (len(found) == 1 or fold(usable[0].name) == fold(wanted)):
        return usable[0], []
    return None, usable


async def _pick_service(
    session: AsyncSession,
    agent_id: uuid.UUID | None,
    service_id: uuid.UUID | None,
    service_name: str | None,
) -> _Pick:
    """El servicio, si es uno que el agente del turno ofrece (garantía 9). El id
    manda; sin él, o con uno que no existe, el nombre. Uno del hermano es
    ``not_offered``; uno que no está en el catálogo del cliente —inventado, archivado
    o de la vecina, que la RLS no deja ver—, ``unknown_service``."""
    offered = await services_catalog.services_for_agent(session, agent_id)
    mine = {s.id for s in offered}
    options = [ServiceRef(id=s.id, name=s.name) for s in offered if s.bookable]
    catalog = await services_catalog.list_services(session)
    if service_id is not None:
        svc = next((s for s in offered if s.id == service_id), None)
        if svc is not None:
            return _Pick(service=svc)
        if any(s.id == service_id for s in catalog):
            return _Pick(refused="not_offered")
    if not service_name or not fold(service_name):
        return _Pick(refused=UNKNOWN_SERVICE, services=options)
    found = matches(service_name, catalog, lambda s: s.name)
    if not found:
        return _Pick(refused=UNKNOWN_SERVICE, services=options)
    chosen, tied = _one(found, service_name, mine)
    if chosen is not None:
        return _Pick(service=chosen)
    if not tied:
        return _Pick(refused="not_offered")
    return _Pick(
        refused=AMBIGUOUS_SERVICE, services=[ServiceRef(id=s.id, name=s.name) for s in tied]
    )


async def _pick_staff(
    session: AsyncSession,
    service: ReservationService,
    staff_id: uuid.UUID | None,
    staff_name: str | None,
) -> _Pick:
    """La persona, entre el equipo activo (no archivado), para ``service``. Sin id ni
    nombre, cualquiera. Una que existe y no hace el servicio es ``not_offered``
    (R14.4) con quienes sí; una que no existe, ``unknown_staff``."""
    if staff_id is None and not (staff_name and fold(staff_name)):
        return _Pick(service=service)
    able = await staff_for_service(session, service)
    can = {s.id for s in able}
    options = [StaffRef(id=s.id, name=s.name) for s in able]
    team = await active_staff(session)
    if staff_id is not None:
        if staff_id in can:
            return _Pick(service=service, staff_id=staff_id)
        if any(s.id == staff_id for s in team):
            return _Pick(refused="not_offered", staff=options)
    if not staff_name or not fold(staff_name):
        return _Pick(refused=UNKNOWN_STAFF, staff=options)
    found = matches(staff_name, team, lambda s: s.name)
    if not found:
        return _Pick(refused=UNKNOWN_STAFF, staff=options)
    chosen, tied = _one(found, staff_name, can)
    if chosen is not None:
        return _Pick(service=service, staff_id=chosen.id)
    if not tied:
        return _Pick(refused="not_offered", staff=options)
    return _Pick(refused=AMBIGUOUS_STAFF, staff=[StaffRef(id=s.id, name=s.name) for s in tied])


async def _pick(
    session: AsyncSession,
    agent_id: uuid.UUID | None,
    *,
    service_id: uuid.UUID | None,
    service_name: str | None,
    staff_id: uuid.UUID | None,
    staff_name: str | None,
) -> _Pick:
    picked = await _pick_service(session, agent_id, service_id, service_name)
    if picked.service is None:
        return picked
    return await _pick_staff(session, picked.service, staff_id, staff_name)


# ── lectura ─────────────────────────────────────────────────────────────────


class Services(ToolBase):
    name = "reservas.services"
    description = (
        "What can be booked: in services mode, the services YOU handle, with duration, price "
        "and who does each one (use their ids in find_slots/create, or their names in a "
        "later turn, when the ids are no longer there); a service that is not "
        "bookable has no times — explain how it is ordered. In capacity mode, the largest "
        "group the agent may book."
    )
    input_model = ServicesInput
    output_model = ServicesOutput
    side_effects = ()

    async def run(self, payload: InputModel) -> OutputModel:
        async with tool_session() as session:
            ctx = await _ctx(session)
            if ctx.mode == "capacity":
                return ServicesOutput(mode="capacity", max_party=ctx.settings.max_party)
            agent_id = await _turn_agent(session)
            items: list[ServiceItem] = []
            for svc in await services_catalog.services_for_agent(session, agent_id):
                staff = await staff_for_service(session, svc) if svc.bookable else []
                nobody = svc.bookable and not staff
                kind = services_catalog.price_kind_of(svc)
                items.append(
                    ServiceItem(
                        id=svc.id,
                        name=svc.name,
                        bookable=svc.bookable and not nobody,
                        why_not=NO_STAFF if nobody else None,
                        duration_minutes=svc.duration_minutes,
                        description=svc.description,
                        price_kind=kind,
                        price=Money(amount_minor=int(svc.price_minor or 0), currency=svc.currency)
                        if kind == "amount"
                        else None,
                        staff=[StaffRef(id=s.id, name=s.name) for s in staff],
                    )
                )
            return ServicesOutput(mode="services", services=items)


class FindSlots(ToolBase):
    name = "reservas.find_slots"
    description = (
        "Free times on a day, only within the business's opening hours and its rules. "
        "Services mode: pass the service (service_id, or service_name as the customer said "
        "it) and the team member (staff_id or staff_name, or omit both for anyone). Capacity "
        "mode: pass party_size. Offer only the returned times; if closed or empty, say so "
        "and suggest first_fit or another day. If refused is unknown_service, unknown_staff, "
        "ambiguous_service or ambiguous_staff, the service or person was not recognised and "
        "nothing was searched: call again with one of the returned services/staff, or ask "
        "the customer; it says nothing about free times."
    )
    input_model = FindSlotsInput
    output_model = FindSlotsOutput
    side_effects = ()

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, FindSlotsInput)
        now = _now()
        async with tool_session() as session:
            ctx = await _ctx(session)
            if ctx.hours is None:
                return FindSlotsOutput(date=payload.date, closed=True, why_closed="hours_missing")
            if not ctx.day_ranges(payload.date):
                return FindSlotsOutput(date=payload.date, closed=True, why_closed="closed")
            not_before = now + _notice(ctx)
            if ctx.mode == "services":
                picked = await _pick(
                    session,
                    await _turn_agent(session),
                    service_id=payload.service_id,
                    service_name=payload.service_name,
                    staff_id=payload.staff_id,
                    staff_name=payload.staff_name,
                )
                if picked.refused == "not_offered":
                    return FindSlotsOutput(
                        date=payload.date,
                        closed=True,
                        why_closed="not_offered",
                        staff=picked.staff,
                    )
                if picked.refused is not None or picked.service is None:
                    return FindSlotsOutput(
                        date=payload.date,
                        closed=False,
                        refused=picked.refused,
                        services=picked.services,
                        staff=picked.staff,
                    )
                svc = picked.service
                if not svc.bookable:
                    return FindSlotsOutput(
                        date=payload.date, closed=True, why_closed="not_bookable"
                    )
                if not await staff_for_service(session, svc):
                    return FindSlotsOutput(date=payload.date, closed=True, why_closed=NO_STAFF)
                free = await services_free(
                    session,
                    ctx,
                    day=payload.date,
                    service=svc,
                    staff_ids=[picked.staff_id] if picked.staff_id else None,
                    not_before=not_before,
                )
                names = {s.id: s.name for s in await staff_for_service(session, svc)}
                return FindSlotsOutput(
                    date=payload.date,
                    closed=False,
                    slots=[
                        SlotOut(time=t, staff=[StaffRef(id=i, name=names.get(i, "—")) for i in ids])
                        for t, ids in free.items()
                    ],
                )
            n = payload.party_size or 1
            if n > (ctx.settings.max_party or n):
                return FindSlotsOutput(date=payload.date, closed=False, why_closed="too_large")
            cap = await capacity_day(session, ctx, payload.date)
            slots: list[SlotOut] = []
            for s in cap.slots:
                if s.at < not_before:
                    continue
                fit = capacity_fit(cap.slots, cap.blocked, cap.people, cap.rules, s.at, n, now=now)
                if fit.fits:
                    slots.append(SlotOut(time=s.at.strftime("%H:%M"), left=fit.left))
            nxt = first_fit(cap.slots, cap.blocked, cap.people, cap.rules, n, now=not_before)
            return FindSlotsOutput(
                date=payload.date,
                closed=not cap.slots,
                slots=slots,
                first_fit=nxt.strftime("%H:%M") if nxt else None,
            )


def _notice(ctx: Ctx) -> timedelta:
    return timedelta(minutes=ctx.settings.agent_min_notice_minutes)


class ListMine(ToolBase):
    name = "reservas.list_mine"
    description = "The bookings of the person you are talking to (only theirs)."
    input_model = ListMineInput
    output_model = ListMineOutput
    side_effects = ()

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, ListMineInput)
        customer_id = get_current_customer()
        if customer_id is None:
            return ListMineOutput(bookings=[])
        async with tool_session() as session:
            ctx = await _ctx(session)
            stmt = sa.select(Reservation).where(Reservation.customer_id == customer_id)
            if payload.only_upcoming:
                stmt = stmt.where(
                    Reservation.starts_at > _now(),
                    Reservation.status.in_(("pending", "confirmed")),
                )
            rows = (await session.execute(stmt.order_by(Reservation.starts_at).limit(20))).scalars()
            return ListMineOutput(bookings=[await _brief(session, ctx, r) for r in list(rows)])


# ── escritura ───────────────────────────────────────────────────────────────


def _agent_key(customer_id: uuid.UUID, key: str) -> str:
    """La clave que eligió el modelo, de esta persona.

    El modelo no conoce el id de la conversación, así que dos personas pueden
    mandar la misma clave («sabado-2100»). Sin esto, la segunda recibía la
    reserva de la primera (/cso CSO-001). Cabe en la columna (120).
    """
    digest = hashlib.sha256(f"{customer_id}:{key}".encode()).hexdigest()
    return f"agent:{digest}"


class Create(ToolBase):
    name = "reservas.create"
    description = (
        "Book for the person you are talking to, at a time find_slots returned. You cannot "
        "book for anyone else. Pass the service and the team member by id, or by name "
        "(service_name, staff_name) when the ids are not in this turn — e.g. the customer "
        "picked the time in a later message. Idempotent by idempotency_key. If refused is "
        "'too_large', the group is above what you may book: escalate to a person. If refused "
        "is unknown_service, unknown_staff, ambiguous_service or ambiguous_staff, the time "
        "was NOT checked: call again in this turn with one of the returned services/staff, "
        "or ask the customer which one; never tell them the time is taken. Only 'slot_taken' "
        "means the time is taken. Confirm the booking to the customer only when booking is "
        "returned."
    )
    input_model = CreateInput
    output_model = CreateOutput
    side_effects = ("mutates_db",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, CreateInput)
        customer_id = current_customer_or_refuse("reservar")
        now = _now()
        async with tool_session() as session:
            ctx = await _ctx(session)
            name, phone = await _contact(session, customer_id)
            conversation_id, agent_id = await _turn(session, customer_id, payload.conversation_id)
            service_id, staff_id = payload.service_id, payload.staff_id
            if ctx.mode == "services":
                picked = await _pick(
                    session,
                    agent_id,
                    service_id=payload.service_id,
                    service_name=payload.service_name,
                    staff_id=payload.staff_id,
                    staff_name=payload.staff_name,
                )
                if picked.refused is not None or picked.service is None:
                    return CreateOutput(
                        refused=picked.refused, services=picked.services, staff=picked.staff
                    )
                service_id, staff_id = picked.service.id, picked.staff_id
            agent_name = (
                await session.scalar(sa.select(Agent.name).where(Agent.id == agent_id))
                if agent_id
                else None
            )
            try:
                res, replay = await create_booking(
                    session,
                    ctx,
                    NewBooking(
                        day=payload.date,
                        at=_hm(payload.time),
                        origin="agent",
                        channel="whatsapp",
                        contact_name=name,
                        contact_phone=phone,
                        party_size=payload.party_size,
                        staff_id=staff_id,
                        service_id=service_id,
                        any_staff=payload.any_staff,
                        note=payload.note,
                        join_waitlist=payload.join_waitlist,
                        idempotency_key=_agent_key(customer_id, payload.idempotency_key),
                        customer_id=customer_id,
                        conversation_id=conversation_id,
                        agent_id=agent_id,
                        as_agent=True,
                    ),
                    actor=Actor("agent", str(agent_name) if agent_name else None),
                    now=now,
                )
            except ReservationError as exc:
                if exc.code in REFUSALS:
                    ff = exc.info.get("first_fit")
                    return CreateOutput(
                        refused=exc.code, first_fit=ff.get("time") if isinstance(ff, dict) else None
                    )
                # Esa persona no hace este servicio (R14.4): no es un fallo, es un no.
                # ``_pick_staff`` ya lo dice antes; esto queda por si el equipo cambia
                # entre la resolución y el candado.
                if exc.code == "not_found" and staff_id is not None:
                    return CreateOutput(refused="not_offered")
                raise ToolError(exc.code) from None
            return CreateOutput(booking=await _brief(session, ctx, res), idempotent_replay=replay)


class Reschedule(ToolBase):
    name = "reservas.reschedule"
    description = (
        "Move a booking of the person you are talking to, to a time find_slots returned, "
        "optionally with another team member (staff_id, or staff_name when the id is not "
        "in this turn). A booking that is not theirs reads as not found. If refused is "
        "unknown_staff or ambiguous_staff, the person was not recognised and nothing was "
        "moved: retry with one of the returned staff or ask the customer; never say the "
        "time is taken."
    )
    input_model = RescheduleInput
    output_model = RescheduleOutput
    side_effects = ("mutates_db",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, RescheduleInput)
        customer_id = current_customer_or_refuse("mover una reserva")
        now = _now()
        async with tool_session() as session:
            ctx = await _ctx(session)
            res = await _mine(session, payload.booking_id, customer_id)
            staff_id = payload.staff_id
            if res.service_id is not None and (payload.staff_id or payload.staff_name):
                svc = await session.get(ReservationService, res.service_id)
                if svc is not None:
                    picked = await _pick_staff(session, svc, payload.staff_id, payload.staff_name)
                    if picked.refused is not None:
                        return RescheduleOutput(refused=picked.refused, staff=picked.staff)
                    staff_id = picked.staff_id
            try:
                await move_booking(
                    session,
                    ctx,
                    res,
                    day=payload.date,
                    at=_hm(payload.time),
                    staff_id=staff_id,
                    party_size=None,
                    notify=False,
                    actor=Actor("agent"),
                    now=now,
                    as_agent=True,
                )
            except ReservationError as exc:
                if exc.code in REFUSALS:
                    ff = exc.info.get("first_fit")
                    return RescheduleOutput(
                        refused=exc.code, first_fit=ff.get("time") if isinstance(ff, dict) else None
                    )
                raise ToolError(exc.code) from None
            return RescheduleOutput(booking=await _brief(session, ctx, res))


class Cancel(ToolBase):
    name = "reservas.cancel"
    description = (
        "Cancel a booking of the person you are talking to. A booking that is not theirs "
        "reads as not found. The freed time may be offered to the waitlist."
    )
    input_model = CancelInput
    output_model = CancelOutput
    side_effects = ("mutates_db",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, CancelInput)
        customer_id = current_customer_or_refuse("cancelar una reserva")
        now = _now()
        async with tool_session() as session:
            ctx = await _ctx(session)
            res = await _mine(session, payload.booking_id, customer_id)
            try:
                await cancel_booking(
                    session, ctx, res, by="customer", actor=Actor("customer"), now=now
                )
            except ReservationError as exc:
                raise ToolError(exc.code) from None
            offer = None
            if ctx.mode == "services":
                offer = await waitlist.open_after_cancel(session, ctx, res, now)
            else:
                offers = await waitlist.open_capacity(
                    session, ctx, day=ctx.local(res.starts_at).date(), now=now
                )
                offer = offers[0] if offers else None
            return CancelOutput(
                booking=await _brief(session, ctx, res), offered_to_waitlist=offer is not None
            )


class ConfirmAttendance(ToolBase):
    name = "reservas.confirm_attendance"
    description = (
        "The person answers the confirmation request: attending=true confirms their next "
        "unconfirmed booking (or booking_id), attending=false cancels it."
    )
    input_model = ConfirmAttendanceInput
    output_model = ConfirmAttendanceOutput
    side_effects = ("mutates_db",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, ConfirmAttendanceInput)
        customer_id = current_customer_or_refuse("confirmar una reserva")
        now = _now()
        async with tool_session() as session:
            ctx = await _ctx(session)
            if payload.booking_id is not None:
                res = await _mine(session, payload.booking_id, customer_id)
            else:
                found = await session.scalar(
                    sa.select(Reservation)
                    .where(
                        Reservation.customer_id == customer_id,
                        Reservation.status == "pending",
                        Reservation.starts_at > now,
                    )
                    .order_by(Reservation.starts_at)
                    .limit(1)
                )
                if found is None:
                    raise ToolError("no unconfirmed booking for this customer")
                res = found
            try:
                if payload.attending:
                    if res.status == "pending":
                        await transition(
                            session, ctx, res, "confirm", actor=Actor("customer"), now=now
                        )
                    add_event(session, res, "replied_yes", Actor("customer"))
                else:
                    add_event(session, res, "replied_no", Actor("customer"))
                    await cancel_booking(
                        session, ctx, res, by="customer", actor=Actor("customer"), now=now
                    )
            except ReservationError as exc:
                raise ToolError(exc.code) from None
            return ConfirmAttendanceOutput(booking=await _brief(session, ctx, res))


class JoinWaitlist(ToolBase):
    name = "reservas.join_waitlist"
    description = (
        "Put the person you are talking to on the waitlist. Capacity mode: date, time and "
        "party_size of the full hour they wanted. Services mode: the service (service_id or "
        "service_name; with booking_id, the booking's) and the team member (staff_id or "
        "staff_name, or anyone), and either a day, an 'until' day, or booking_id if they "
        "want to bring an existing booking forward. If refused is unknown_* or ambiguous_*, "
        "nobody was put on the list: retry with one of the returned services/staff."
    )
    input_model = JoinWaitlistInput
    output_model = JoinWaitlistOutput
    side_effects = ("mutates_db",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, JoinWaitlistInput)
        customer_id = current_customer_or_refuse("apuntar en la lista de espera")
        async with tool_session() as session:
            ctx = await _ctx(session)
            reservation_id = None
            booked_service: uuid.UUID | None = None
            if payload.booking_id is not None:
                booking = await _mine(session, payload.booking_id, customer_id)
                reservation_id, booked_service = booking.id, booking.service_id
            service_id, staff_id = payload.service_id, payload.staff_id
            if ctx.mode == "services":
                named = payload.service_id is not None or bool(payload.service_name)
                picked = await _pick(
                    session,
                    await _turn_agent(session),
                    service_id=payload.service_id if named else booked_service,
                    service_name=payload.service_name,
                    staff_id=payload.staff_id,
                    staff_name=payload.staff_name,
                )
                if picked.refused is not None or picked.service is None:
                    return JoinWaitlistOutput(
                        refused=picked.refused, services=picked.services, staff=picked.staff
                    )
                service_id, staff_id = picked.service.id, picked.staff_id
            elif service_id is not None and not await services_catalog.offers(
                session, await _turn_agent(session), service_id
            ):
                return JoinWaitlistOutput(refused="not_offered")
            name, phone = await _contact(session, customer_id)
            try:
                entry = await waitlist.join(
                    session,
                    ctx,
                    waitlist.NewEntry(
                        contact_name=name,
                        contact_phone=phone,
                        joined_by_kind="agent",
                        customer_id=customer_id,
                        party_size=payload.party_size,
                        desired_day=payload.date,
                        desired_time=_hm(payload.time) if payload.time else None,
                        desired_until=payload.until,
                        service_id=service_id,
                        staff_id=staff_id,
                        reservation_id=reservation_id,
                    ),
                )
            except ReservationError as exc:
                raise ToolError(exc.code) from None
            return JoinWaitlistOutput(entry_id=entry.id, status=entry.status)


class AnswerOffer(ToolBase):
    name = "reservas.answer_offer"
    description = (
        "The person answers a waitlist offer we sent them (yes or no). Resolves their open "
        "offer; never name one. result 'booked' means it is theirs; 'late_taken' means "
        "someone else took it first and they stay on the list."
    )
    input_model = AnswerOfferInput
    output_model = AnswerOfferOutput
    side_effects = ("mutates_db",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, AnswerOfferInput)
        customer_id = current_customer_or_refuse("responder a una oferta")
        async with tool_session() as session:
            ctx = await _ctx(session)
            conversation_id, agent_id = await _turn(session, customer_id, payload.conversation_id)
            answer = await waitlist.answer(
                session,
                ctx,
                customer_id=customer_id,
                accept=payload.accept,
                now=_now(),
                conversation_id=conversation_id,
                agent_id=agent_id,
                actor=Actor("customer"),
            )
            return AnswerOfferOutput(
                result=answer.result,
                booking=await _brief(session, ctx, answer.booking) if answer.booking else None,
            )


RESERVAS_TOOLS: tuple[type[ToolBase], ...] = (
    Services,
    FindSlots,
    Create,
    ListMine,
    Reschedule,
    Cancel,
    ConfirmAttendance,
    JoinWaitlist,
    AnswerOffer,
)

__all__ = ["RESERVAS_TOOLS"]
