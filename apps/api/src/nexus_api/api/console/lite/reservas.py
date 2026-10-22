"""``/console/lite/reservas/*`` — la agenda del negocio (spec 043, R2 a R5).

La comparten la consola web y la app (mismo principal de cliente). Solo la
alcanza la persona de un cliente con el módulo ``reservas``; todo corre bajo la
RLS de su cliente (``lite_scope``) y un id de otro cliente responde el mismo 404
que uno inventado. Las reglas viven en ``services/reservations``: aquí solo se
traduce entre HTTP y el dominio.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, NoReturn

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from redis.asyncio import Redis

from nexus_api.api.deps import get_redis
from nexus_api.db.models import (
    Reservation,
    ReservationBlock,
    ReservationOffer,
    ReservationOfferCandidate,
    ReservationService,
    ReservationServiceStaff,
    ReservationStaff,
    ReservationWaitlist,
)
from nexus_api.services.business_hours import (
    BusinessHoursError,
    business_hours_label,
    canonical_business_hours,
    parse_business_hours,
    to_canonical,
    week_of,
)
from nexus_api.services.reservations import calendar_sync, views, waitlist
from nexus_api.services.reservations.calendar import staff_calendar_status
from nexus_api.services.reservations.core import (
    Actor,
    Ctx,
    NewBooking,
    ReservationError,
    cancel_booking,
    capacity_day,
    check_version,
    contact_customer,
    create_booking,
    get_booking,
    load_ctx,
    move_booking,
    services_free,
    transition,
)
from nexus_api.services.reservations.engine import capacity_fit, current_slot, first_fit
from nexus_api.services.reservations.settings import SettingsError, apply_patch

from .deps import LiteScope, lite_scope
from .reservas_schemas import (
    BlockCreatedOut,
    BlockIn,
    BlockListOut,
    BlockOut,
    BookingDetailOut,
    BookingListOut,
    BookingOut,
    BusinessHoursIn,
    BusinessHoursOut,
    CalendarOut,
    CancelIn,
    CancelledBookingOut,
    CancelPreviewOut,
    MoveIn,
    NewBookingIn,
    OccupancyOut,
    OfferListOut,
    OfferOut,
    ServiceIn,
    ServiceListOut,
    ServiceOut,
    ServicePatchIn,
    SettingsOut,
    SettingsPatchIn,
    SlotOut,
    SlotsOut,
    StaffCalendarIn,
    StaffIn,
    StaffListOut,
    StaffOut,
    StaffPatchIn,
    SummaryOut,
    WaitlistEntryOut,
    WaitlistIn,
    WaitlistOut,
    WalkinIn,
)

router = APIRouter(prefix="/reservas")
SCOPE = lite_scope("reservas")
MAX_RANGE_DAYS = 62
OCCUPANCY_RANGE_DAYS = 31


def _now() -> datetime:
    return datetime.now(UTC)


def _raise(exc: ReservationError) -> NoReturn:
    if exc.http_status == 404:
        raise HTTPException(status_code=404, detail="Not found")
    raise HTTPException(status_code=exc.http_status, detail={"code": exc.code, **exc.info})


def _actor(scope: LiteScope) -> Actor:
    m = scope.principal.membership
    return Actor("person", (m.display_name or m.email)[:120])


async def _ctx(scope: LiteScope) -> Ctx:
    ctx = await load_ctx(scope.session, scope.principal.tenant_id)
    if ctx is None:
        # El módulo sin ajustes no existe: el admin lo activa con su modo.
        raise HTTPException(status_code=409, detail={"code": "not_configured"})
    return ctx


def _need(ctx: Ctx, mode: str) -> None:
    if ctx.mode != mode:
        raise HTTPException(status_code=409, detail={"code": "wrong_mode", "mode": ctx.mode})


def _version(if_match: str | None) -> int | None:
    if if_match is None:
        return None
    try:
        return int(if_match.strip().strip('"'))
    except ValueError:
        raise HTTPException(status_code=400, detail="If-Match must be an integer version") from None


def _hm(raw: str) -> time:
    h, m = raw.split(":")
    return time(int(h), int(m))


def _range(start: date, end: date, limit: int) -> None:
    if end < start or (end - start).days >= limit:
        raise HTTPException(status_code=422, detail={"code": "bad_range", "max_days": limit})


async def _idem(redis: Redis, scope: LiteScope, kind: str, key: str | None) -> uuid.UUID | None:
    """La reintentada de una creación sin columna propia: el id de la primera."""
    if not key:
        return None
    raw = await redis.get(f"lite:idem:{scope.principal.tenant_id}:{kind}:{key[:120]}")
    if not raw:
        return None
    return uuid.UUID(raw.decode() if isinstance(raw, bytes) else str(raw))


async def _remember(
    redis: Redis, scope: LiteScope, kind: str, key: str | None, oid: uuid.UUID
) -> None:
    if key:
        await redis.set(
            f"lite:idem:{scope.principal.tenant_id}:{kind}:{key[:120]}", str(oid), ex=86400
        )


# ── ajustes y horario ───────────────────────────────────────────────────────


def _settings_out(scope: LiteScope, ctx: Ctx) -> SettingsOut:
    s = ctx.settings
    hours = ctx.hours
    lang = "es"
    return SettingsOut.model_validate(
        {
            "mode": s.mode,
            "capacity_kind": s.capacity_kind,
            "timezone": str(ctx.tz),
            "currency": ctx.currency,
            "business_hours": to_canonical(hours) if hours else None,
            "business_hours_label": business_hours_label(hours, lang) if hours else None,
            "hours_missing": hours is None,
            "slot_step_minutes": s.slot_step_minutes,
            "waitlist": {"enabled": s.waitlist_enabled, "lead_minutes": s.waitlist_lead_minutes},
            "agent": {
                "min_notice_minutes": s.agent_min_notice_minutes,
                "max_days_ahead": s.agent_max_days_ahead,
            },
            "confirmation": {"enabled": s.confirm_enabled, "when": s.confirm_when},
            "reminder_enabled": s.reminder_enabled,
            "release_unconfirmed": s.release_unconfirmed,
            "capacity": {
                "seats": s.seats,
                "stay_minutes": s.stay_minutes,
                "max_party": s.max_party,
                "walkin_hold": s.walkin_hold,
                "schedule": s.schedule,
            }
            if s.mode == "capacity"
            else None,
            "version": s.version,
        }
    )


@router.get("/settings", response_model=SettingsOut)
async def read_settings(scope: LiteScope = Depends(SCOPE)) -> SettingsOut:
    return _settings_out(scope, await _ctx(scope))


@router.patch("/settings", response_model=SettingsOut)
async def patch_settings(
    body: SettingsPatchIn,
    scope: LiteScope = Depends(SCOPE),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> SettingsOut:
    ctx = await _ctx(scope)
    expected = _version(if_match)
    if expected is not None and ctx.settings.version != expected:
        raise HTTPException(
            status_code=412, detail={"code": "stale", "version": ctx.settings.version}
        )
    try:
        apply_patch(ctx.settings, body.model_dump(exclude_unset=True))
    except SettingsError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid", "field": exc.field, "message": exc.message}
        ) from None
    ctx.settings.version += 1
    ctx.settings.updated_by = scope.principal.actor
    await scope.session.flush()
    return _settings_out(scope, ctx)


@router.put("/business-hours", response_model=BusinessHoursOut)
async def put_business_hours(
    body: BusinessHoursIn, scope: LiteScope = Depends(SCOPE)
) -> BusinessHoursOut:
    try:
        hours = week_of(canonical_business_hours(body.hours))
    except BusinessHoursError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid", "message": str(exc)}
        ) from None
    if any(len(r) > 2 for r in hours.values()):
        raise HTTPException(status_code=422, detail={"code": "invalid", "message": "max 2 ranges"})
    # La etiqueta del prompt (la lee ``agent_configs``) no es del negocio: se queda.
    stored: dict[str, Any] = dict(hours)
    before = scope.tenant.business_hours
    if isinstance(before, dict) and isinstance(before.get("label"), str):
        stored["label"] = before["label"]
    scope.tenant.business_hours = stored
    await scope.session.flush()
    parsed = parse_business_hours(hours)
    return BusinessHoursOut(
        business_hours=hours,
        business_hours_label=business_hours_label(parsed, "es") if parsed else None,
    )


# ── equipo ──────────────────────────────────────────────────────────────────


def _staff_out(
    ctx: Ctx, m: ReservationStaff, calendars: dict[uuid.UUID, dict[str, Any]]
) -> StaffOut:
    own = parse_business_hours(m.hours) if m.hours else None
    effective = own or ctx.hours
    return StaffOut.model_validate(
        {
            "id": m.id,
            "name": m.name,
            "email": m.email,
            "hours": to_canonical(own) if own else None,
            "effective_hours": to_canonical(effective) if effective else None,
            "position": m.position,
            "archived": m.archived_at is not None,
            "calendar": calendars.get(m.id, {"status": "none"}),
        }
    )


async def _calendars(scope: LiteScope) -> dict[uuid.UUID, dict[str, Any]]:
    return await staff_calendar_status(scope.session)


def _clean_hours(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        hours = week_of(canonical_business_hours(raw))
    except BusinessHoursError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid", "message": str(exc)}
        ) from None
    if any(len(r) > 2 for r in hours.values()):
        raise HTTPException(status_code=422, detail={"code": "invalid", "message": "max 2 ranges"})
    return hours


@router.get("/staff", response_model=StaffListOut)
async def list_staff(
    archived: bool = Query(default=False), scope: LiteScope = Depends(SCOPE)
) -> StaffListOut:
    ctx = await _ctx(scope)
    _need(ctx, "services")
    stmt = sa.select(ReservationStaff).order_by(
        ReservationStaff.position, ReservationStaff.created_at
    )
    if not archived:
        stmt = stmt.where(ReservationStaff.archived_at.is_(None))
    cal = await _calendars(scope)
    return StaffListOut(
        items=[_staff_out(ctx, m, cal) for m in (await scope.session.execute(stmt)).scalars()]
    )


@router.post("/staff", response_model=StaffOut, status_code=201)
async def create_staff(
    body: StaffIn,
    scope: LiteScope = Depends(SCOPE),
    redis: Redis = Depends(get_redis),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> StaffOut:
    ctx = await _ctx(scope)
    _need(ctx, "services")
    prior = await _idem(redis, scope, "staff", idempotency_key)
    if prior is not None:
        found = await scope.session.get(ReservationStaff, prior)
        if found is not None:
            return _staff_out(ctx, found, {})
    count = await scope.session.scalar(sa.select(sa.func.count()).select_from(ReservationStaff))
    m = ReservationStaff(
        tenant_id=ctx.tenant_id,
        name=body.name.strip(),
        email=(body.email or "").strip() or None,
        hours=_clean_hours(body.hours),
        position=int(count or 0) + 1,
    )
    scope.session.add(m)
    await scope.session.flush()
    await _remember(redis, scope, "staff", idempotency_key, m.id)
    return _staff_out(ctx, m, {})


async def _staff(scope: LiteScope, staff_id: uuid.UUID) -> ReservationStaff:
    m = await scope.session.get(ReservationStaff, staff_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Not found")
    return m


@router.patch("/staff/{staff_id}", response_model=StaffOut)
async def patch_staff(
    staff_id: uuid.UUID, body: StaffPatchIn, scope: LiteScope = Depends(SCOPE)
) -> StaffOut:
    ctx = await _ctx(scope)
    m = await _staff(scope, staff_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("name"):
        m.name = data["name"].strip()
    if "email" in data:
        m.email = (data["email"] or "").strip() or None
    if "hours" in data:
        m.hours = _clean_hours(data["hours"])
    if "position" in data and data["position"] is not None:
        m.position = int(data["position"])
    await scope.session.flush()
    return _staff_out(ctx, m, await _calendars(scope))


@router.get("/calendar", response_model=CalendarOut)
async def read_calendar(scope: LiteScope = Depends(SCOPE)) -> CalendarOut:
    """P3: la cuenta de Google Calendar del cliente y sus calendarios."""
    await _ctx(scope)
    conn = await calendar_sync.connection_of(scope.session, scope.principal.tenant_id)
    if conn is None:
        return CalendarOut(provider="google", connected=False, calendars=[])
    try:
        cals = await calendar_sync.default_gateway().list_calendars(conn)
    except Exception:  # el proveedor caído no rompe la pantalla
        cals = []
    return CalendarOut.model_validate({"provider": "google", "connected": True, "calendars": cals})


@router.put("/staff/{staff_id}/calendar", response_model=StaffOut)
async def put_staff_calendar(
    staff_id: uuid.UUID, body: StaffCalendarIn, scope: LiteScope = Depends(SCOPE)
) -> StaffOut:
    ctx = await _ctx(scope)
    member = await _staff(scope, staff_id)
    name: str | None = None
    if body.calendar_id is not None:
        conn = await calendar_sync.connection_of(scope.session, ctx.tenant_id)
        if conn is None:
            raise HTTPException(status_code=409, detail={"code": "calendar_not_connected"})
        # Solo un calendario de la cuenta que el cliente conectó (/cso, apéndice).
        try:
            cals = await calendar_sync.default_gateway().list_calendars(conn)
        except Exception:
            raise HTTPException(status_code=409, detail={"code": "calendar_unavailable"}) from None
        chosen = next((c for c in cals if c.get("id") == body.calendar_id), None)
        if chosen is None:
            raise HTTPException(status_code=422, detail={"code": "unknown_calendar"})
        name = chosen.get("name") or body.calendar_id
    await calendar_sync.set_staff_calendar(scope.session, ctx, member.id, body.calendar_id, name)
    return _staff_out(ctx, member, await _calendars(scope))


@router.post("/staff/{staff_id}/archive", status_code=204)
async def archive_staff(staff_id: uuid.UUID, scope: LiteScope = Depends(SCOPE)) -> Response:
    m = await _staff(scope, staff_id)
    live = await scope.session.scalar(
        sa.select(sa.func.count())
        .select_from(Reservation)
        .where(
            Reservation.staff_id == m.id,
            Reservation.status.in_(("pending", "confirmed")),
            Reservation.starts_at > _now(),
        )
    )
    if live:
        raise HTTPException(
            status_code=409, detail={"code": "live_reservations", "count": int(live)}
        )
    m.archived_at = _now()
    return Response(status_code=204)


# ── servicios ───────────────────────────────────────────────────────────────


async def _service_staff(scope: LiteScope, service_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await scope.session.execute(
        sa.select(ReservationServiceStaff.staff_id).where(
            ReservationServiceStaff.service_id == service_id
        )
    )
    return list(rows.scalars())


async def _service_out(scope: LiteScope, s: ReservationService) -> ServiceOut:
    return ServiceOut.model_validate(
        {
            "id": s.id,
            "name": s.name,
            "duration_minutes": s.duration_minutes,
            "price": {"amount_minor": s.price_minor, "currency": s.currency}
            if s.price_minor is not None
            else None,
            "staff": "all" if s.all_staff else "some",
            "staff_ids": [] if s.all_staff else await _service_staff(scope, s.id),
            "position": s.position,
            "archived": s.archived_at is not None,
        }
    )


async def _set_service_staff(
    scope: LiteScope, ctx: Ctx, svc: ReservationService, staff_ids: list[uuid.UUID] | None
) -> None:
    await scope.session.execute(
        sa.delete(ReservationServiceStaff).where(ReservationServiceStaff.service_id == svc.id)
    )
    svc.all_staff = staff_ids is None
    for sid in staff_ids or []:
        member = await scope.session.get(ReservationStaff, sid)
        if member is None:
            raise HTTPException(status_code=404, detail="Not found")
        scope.session.add(
            ReservationServiceStaff(tenant_id=ctx.tenant_id, service_id=svc.id, staff_id=sid)
        )


@router.get("/services", response_model=ServiceListOut)
async def list_services(
    archived: bool = Query(default=False), scope: LiteScope = Depends(SCOPE)
) -> ServiceListOut:
    ctx = await _ctx(scope)
    _need(ctx, "services")
    stmt = sa.select(ReservationService).order_by(
        ReservationService.position, ReservationService.name
    )
    if not archived:
        stmt = stmt.where(ReservationService.archived_at.is_(None))
    return ServiceListOut(
        items=[await _service_out(scope, s) for s in (await scope.session.execute(stmt)).scalars()]
    )


@router.post("/services", response_model=ServiceOut, status_code=201)
async def create_service(
    body: ServiceIn,
    scope: LiteScope = Depends(SCOPE),
    redis: Redis = Depends(get_redis),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ServiceOut:
    ctx = await _ctx(scope)
    _need(ctx, "services")
    prior = await _idem(redis, scope, "service", idempotency_key)
    if prior is not None:
        found = await scope.session.get(ReservationService, prior)
        if found is not None:
            return await _service_out(scope, found)
    count = await scope.session.scalar(sa.select(sa.func.count()).select_from(ReservationService))
    svc = ReservationService(
        tenant_id=ctx.tenant_id,
        name=body.name.strip(),
        duration_minutes=body.duration_minutes,
        price_minor=body.price_minor,
        currency=ctx.currency,
        all_staff=True,
        position=int(count or 0) + 1,
    )
    scope.session.add(svc)
    await scope.session.flush()
    await _set_service_staff(scope, ctx, svc, body.staff_ids)
    await scope.session.flush()
    await _remember(redis, scope, "service", idempotency_key, svc.id)
    return await _service_out(scope, svc)


async def _svc(scope: LiteScope, service_id: uuid.UUID) -> ReservationService:
    s = await scope.session.get(ReservationService, service_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Not found")
    return s


@router.patch("/services/{service_id}", response_model=ServiceOut)
async def patch_service(
    service_id: uuid.UUID, body: ServicePatchIn, scope: LiteScope = Depends(SCOPE)
) -> ServiceOut:
    ctx = await _ctx(scope)
    svc = await _svc(scope, service_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("name"):
        svc.name = data["name"].strip()
    if data.get("duration_minutes"):
        svc.duration_minutes = int(data["duration_minutes"])
    if data.get("clear_price"):
        svc.price_minor = None
    elif "price_minor" in data:
        svc.price_minor = data["price_minor"]
    if "staff_ids" in data or data.get("all_staff"):
        await _set_service_staff(
            scope, ctx, svc, None if data.get("all_staff") else data.get("staff_ids")
        )
    if data.get("position") is not None:
        svc.position = int(data["position"])
    await scope.session.flush()
    return await _service_out(scope, svc)


@router.post("/services/{service_id}/archive", status_code=204)
async def archive_service(service_id: uuid.UUID, scope: LiteScope = Depends(SCOPE)) -> Response:
    svc = await _svc(scope, service_id)
    svc.archived_at = _now()
    return Response(status_code=204)


# ── reservas ────────────────────────────────────────────────────────────────


async def _booking_out(scope: LiteScope, ctx: Ctx, res: Any) -> dict[str, Any]:
    out = await views.bookings_out(
        scope.session, ctx, [res], now=_now(), with_inbox=scope.principal.has("inbox")
    )
    return out[0]


@router.get("/bookings", response_model=BookingListOut)
async def list_bookings(
    from_: date = Query(alias="from"),
    to: date = Query(),
    status_: list[str] = Query(default=[], alias="status"),
    origin: list[str] = Query(default=[]),
    staff_id: uuid.UUID | None = Query(default=None),
    q: str | None = Query(default=None, max_length=80),
    scope: LiteScope = Depends(SCOPE),
) -> BookingListOut:
    ctx = await _ctx(scope)
    _range(from_, to, MAX_RANGE_DAYS)
    rows, truncated = await views.list_bookings(
        scope.session,
        ctx,
        start=from_,
        end=to,
        statuses=status_,
        origins=origin,
        staff_id=staff_id,
        q=q,
    )
    items = await views.bookings_out(
        scope.session, ctx, rows, now=_now(), with_inbox=scope.principal.has("inbox")
    )
    return BookingListOut.model_validate(
        {"items": items, "closed_days": views.closed_days(ctx, from_, to), "truncated": truncated}
    )


@router.get("/bookings/{booking_id}", response_model=BookingDetailOut)
async def read_booking(
    booking_id: uuid.UUID, scope: LiteScope = Depends(SCOPE)
) -> BookingDetailOut:
    ctx = await _ctx(scope)
    try:
        res = await get_booking(scope.session, booking_id)
    except ReservationError as exc:
        _raise(exc)
    out = await _booking_out(scope, ctx, res)
    out["events"] = await views.events_out(scope.session, res.id)
    return BookingDetailOut.model_validate(out)


@router.post("/bookings", response_model=BookingOut, status_code=201)
async def create(
    body: NewBookingIn,
    scope: LiteScope = Depends(SCOPE),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> BookingOut:
    ctx = await _ctx(scope)
    try:
        res, _ = await create_booking(
            scope.session,
            ctx,
            NewBooking(
                day=body.date,
                at=_hm(body.time),
                origin="person",
                channel="phone",
                contact_name=body.contact.name,
                contact_phone=body.contact.phone,
                party_size=body.party_size,
                staff_id=body.staff_id,
                service_id=body.service_id,
                note=body.note,
                join_waitlist=body.join_waitlist,
                notify=body.notify,
                idempotency_key=f"lite:{idempotency_key}" if idempotency_key else None,
            ),
            actor=_actor(scope),
            now=_now(),
        )
    except ReservationError as exc:
        _raise(exc)
    return BookingOut.model_validate(await _booking_out(scope, ctx, res))


async def _for_write(scope: LiteScope, booking_id: uuid.UUID, if_match: str | None) -> Any:
    try:
        res = await get_booking(scope.session, booking_id, lock=True)
        check_version(res, _version(if_match))
    except ReservationError as exc:
        _raise(exc)
    return res


@router.post("/bookings/{booking_id}/move", response_model=BookingOut)
async def move(
    booking_id: uuid.UUID,
    body: MoveIn,
    scope: LiteScope = Depends(SCOPE),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> BookingOut:
    ctx = await _ctx(scope)
    res = await _for_write(scope, booking_id, if_match)
    was = ctx.local(res.starts_at)
    try:
        await move_booking(
            scope.session,
            ctx,
            res,
            day=body.date or was.date(),
            at=_hm(body.time) if body.time else time(was.hour, was.minute),
            staff_id=body.staff_id,
            party_size=body.party_size,
            notify=body.notify,
            actor=_actor(scope),
            now=_now(),
        )
    except ReservationError as exc:
        _raise(exc)
    if "note" in body.model_fields_set:
        res.note = (body.note or "").strip()[:500] or None
    return BookingOut.model_validate(await _booking_out(scope, ctx, res))


@router.get("/bookings/{booking_id}/cancel-preview", response_model=CancelPreviewOut)
async def cancel_preview(
    booking_id: uuid.UUID, scope: LiteScope = Depends(SCOPE)
) -> CancelPreviewOut:
    ctx = await _ctx(scope)
    try:
        res = await get_booking(scope.session, booking_id)
    except ReservationError as exc:
        _raise(exc)
    p = await waitlist.cancel_preview(scope.session, ctx, res, _now())
    return CancelPreviewOut(can_offer=p.can_offer, candidates=p.candidates, why_not=p.why_not)  # type: ignore[arg-type]


@router.post("/bookings/{booking_id}/cancel", response_model=CancelledBookingOut)
async def cancel(
    booking_id: uuid.UUID,
    body: CancelIn,
    scope: LiteScope = Depends(SCOPE),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> CancelledBookingOut:
    ctx = await _ctx(scope)
    res = await _for_write(scope, booking_id, if_match)
    now = _now()
    try:
        await cancel_booking(
            scope.session, ctx, res, by="business", actor=_actor(scope), now=now, notify=body.notify
        )
    except ReservationError as exc:
        _raise(exc)
    offer = None
    if ctx.mode == "services" and body.offer_slot:
        offer = await waitlist.open_after_cancel(scope.session, ctx, res, now)
    elif ctx.mode == "capacity":
        opened = await waitlist.open_capacity(
            scope.session, ctx, day=ctx.local(res.starts_at).date(), now=now
        )
        offer = opened[0] if opened else None
    out = await _booking_out(scope, ctx, res)
    if offer is not None:
        n = await scope.session.scalar(
            sa.select(sa.func.count())
            .select_from(ReservationOfferCandidate)
            .where(ReservationOfferCandidate.offer_id == offer.id)
        )
        out["offer"] = {"id": offer.id, "candidates": int(n or 0)}
    else:
        out["offer"] = None
    return CancelledBookingOut.model_validate(out)


async def _act(
    scope: LiteScope, booking_id: uuid.UUID, if_match: str | None, action: str
) -> BookingOut:
    ctx = await _ctx(scope)
    res = await _for_write(scope, booking_id, if_match)
    now = _now()
    try:
        await transition(scope.session, ctx, res, action, actor=_actor(scope), now=now)
    except ReservationError as exc:
        _raise(exc)
    if action == "noshow" and ctx.mode == "capacity":
        await waitlist.open_capacity(
            scope.session, ctx, day=ctx.local(res.starts_at).date(), now=now
        )
    return BookingOut.model_validate(await _booking_out(scope, ctx, res))


@router.post("/bookings/{booking_id}/confirm", response_model=BookingOut)
async def confirm(
    booking_id: uuid.UUID,
    scope: LiteScope = Depends(SCOPE),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> BookingOut:
    return await _act(scope, booking_id, if_match, "confirm")


@router.post("/bookings/{booking_id}/request-confirmation", response_model=BookingOut)
async def request_confirmation(
    booking_id: uuid.UUID,
    scope: LiteScope = Depends(SCOPE),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> BookingOut:
    return await _act(scope, booking_id, if_match, "request_confirmation")


@router.post("/bookings/{booking_id}/arrive", response_model=BookingOut)
async def arrive(
    booking_id: uuid.UUID,
    scope: LiteScope = Depends(SCOPE),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> BookingOut:
    return await _act(scope, booking_id, if_match, "arrive")


@router.post("/bookings/{booking_id}/noshow", response_model=BookingOut)
async def noshow(
    booking_id: uuid.UUID,
    scope: LiteScope = Depends(SCOPE),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> BookingOut:
    return await _act(scope, booking_id, if_match, "noshow")


@router.post("/bookings/{booking_id}/undo", response_model=BookingOut)
async def undo(
    booking_id: uuid.UUID,
    scope: LiteScope = Depends(SCOPE),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> BookingOut:
    return await _act(scope, booking_id, if_match, "undo")


@router.post("/walkins", response_model=BookingOut, status_code=201)
async def walkin(
    body: WalkinIn,
    scope: LiteScope = Depends(SCOPE),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> BookingOut:
    ctx = await _ctx(scope)
    _need(ctx, "capacity")
    now = _now()
    today = ctx.today(now)
    cap = await capacity_day(scope.session, ctx, today)
    at = current_slot(cap.slots, now)
    if at is None:
        nxt = next((s.at for s in cap.slots if s.at > now), None)
        raise HTTPException(
            status_code=409,
            detail={
                "code": "invalid_transition",
                "next_time": nxt.strftime("%H:%M") if nxt else None,
            },
        )
    try:
        res, _ = await create_booking(
            scope.session,
            ctx,
            NewBooking(
                day=today,
                at=ctx.local(at).time().replace(tzinfo=None),
                origin="walkin",
                channel="in_person",
                contact_name=body.name,
                party_size=body.party_size,
                notify=False,
                idempotency_key=f"walkin:{idempotency_key}" if idempotency_key else None,
            ),
            actor=_actor(scope),
            now=now,
        )
    except ReservationError as exc:
        _raise(exc)
    return BookingOut.model_validate(await _booking_out(scope, ctx, res))


# ── huecos, ocupación, resumen ──────────────────────────────────────────────


@router.get("/slots", response_model=SlotsOut)
async def slots(
    date_: date = Query(alias="date"),
    service_id: uuid.UUID | None = Query(default=None),
    staff_id: uuid.UUID | None = Query(default=None),
    party_size: int = Query(default=1, ge=1, le=1000),
    walkin: bool = Query(default=False),
    exclude: uuid.UUID | None = Query(default=None),
    scope: LiteScope = Depends(SCOPE),
) -> SlotsOut:
    ctx = await _ctx(scope)
    now = _now()
    if not ctx.day_ranges(date_):
        return SlotsOut(date=date_, closed=True, slots=[])
    if ctx.mode == "services":
        if service_id is None:
            raise HTTPException(status_code=422, detail={"code": "service_required"})
        svc = await scope.session.get(ReservationService, service_id)
        if svc is None:
            raise HTTPException(status_code=404, detail="Not found")
        free = await services_free(
            scope.session,
            ctx,
            day=date_,
            service=svc,
            staff_ids=[staff_id] if staff_id else None,
            not_before=now,
            exclude=exclude,
        )
        return SlotsOut(
            date=date_,
            closed=False,
            slots=[SlotOut(time=t, staff_ids=ids) for t, ids in free.items()],
        )
    cap = await capacity_day(scope.session, ctx, date_)
    out: list[SlotOut] = []
    for s in cap.slots:
        fit = capacity_fit(
            cap.slots,
            cap.blocked,
            cap.people,
            cap.rules,
            s.at,
            party_size,
            now=now,
            walkin=walkin,
            exclude=exclude,
        )
        out.append(
            SlotOut(
                time=s.at.strftime("%H:%M"),
                shift=s.shift,
                fits=fit.fits,
                left=fit.left,
                why=fit.why,
            )
        )
    nxt = first_fit(
        cap.slots,
        cap.blocked,
        cap.people,
        cap.rules,
        party_size,
        now=now,
        walkin=walkin,
        exclude=exclude,
    )
    return SlotsOut(
        date=date_,
        closed=not cap.slots,
        slots=out,
        first_fit=nxt.strftime("%H:%M") if nxt else None,
    )


@router.get("/occupancy", response_model=OccupancyOut)
async def occupancy(
    from_: date = Query(alias="from"), to: date = Query(), scope: LiteScope = Depends(SCOPE)
) -> OccupancyOut:
    ctx = await _ctx(scope)
    _need(ctx, "capacity")
    _range(from_, to, OCCUPANCY_RANGE_DAYS)
    return OccupancyOut.model_validate(
        await views.occupancy(scope.session, ctx, start=from_, end=to, now=_now())
    )


@router.get("/summary", response_model=SummaryOut)
async def summary(scope: LiteScope = Depends(SCOPE)) -> SummaryOut:
    ctx = await _ctx(scope)
    return SummaryOut.model_validate(
        await views.summary(scope.session, ctx, now=_now(), with_inbox=scope.principal.has("inbox"))
    )


# ── bloqueos ────────────────────────────────────────────────────────────────


def _block_out(b: ReservationBlock) -> BlockOut:
    return BlockOut.model_validate(
        {
            "id": b.id,
            "date": b.day,
            "from": b.from_time.strftime("%H:%M"),
            "until": b.until_time.strftime("%H:%M"),
            "label": b.label,
            "created_by_name": b.created_by_name,
        }
    )


@router.get("/blocks", response_model=BlockListOut)
async def list_blocks(
    from_: date = Query(alias="from"), to: date = Query(), scope: LiteScope = Depends(SCOPE)
) -> BlockListOut:
    ctx = await _ctx(scope)
    _need(ctx, "capacity")
    _range(from_, to, MAX_RANGE_DAYS)
    rows = await scope.session.execute(
        sa.select(ReservationBlock)
        .where(
            ReservationBlock.day >= from_,
            ReservationBlock.day <= to,
            ReservationBlock.removed_at.is_(None),
        )
        .order_by(ReservationBlock.day, ReservationBlock.from_time)
    )
    return BlockListOut(items=[_block_out(b) for b in rows.scalars()])


@router.post("/blocks", response_model=BlockCreatedOut, status_code=201)
async def create_block(
    body: BlockIn,
    scope: LiteScope = Depends(SCOPE),
    redis: Redis = Depends(get_redis),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> BlockCreatedOut:
    ctx = await _ctx(scope)
    _need(ctx, "capacity")
    a, b = _hm(body.from_), _hm(body.until)
    if b < a:
        raise HTTPException(status_code=422, detail={"code": "invalid", "field": "until"})
    prior = await _idem(redis, scope, "block", idempotency_key)
    block = await scope.session.get(ReservationBlock, prior) if prior else None
    if block is None:
        block = ReservationBlock(
            tenant_id=ctx.tenant_id,
            day=body.date,
            from_time=a,
            until_time=b,
            label=body.label.strip(),
            created_by_name=_actor(scope).name,
        )
        scope.session.add(block)
        await scope.session.flush()
        await _remember(redis, scope, "block", idempotency_key, block.id)
    lo, hi = ctx.at(body.date, a), ctx.at(body.date, b)
    overlapping = await scope.session.scalar(
        sa.select(sa.func.count())
        .select_from(Reservation)
        .where(
            Reservation.status.in_(("pending", "confirmed", "arrived")),
            Reservation.starts_at >= lo,
            Reservation.starts_at <= hi,
        )
    )
    return BlockCreatedOut(block=_block_out(block), overlapping_bookings=int(overlapping or 0))


@router.post("/blocks/{block_id}/remove", status_code=204)
async def remove_block(block_id: uuid.UUID, scope: LiteScope = Depends(SCOPE)) -> Response:
    block = await scope.session.get(ReservationBlock, block_id)
    if block is None:
        raise HTTPException(status_code=404, detail="Not found")
    if block.removed_at is None:
        block.removed_at = _now()
    return Response(status_code=204)


# ── lista de espera ─────────────────────────────────────────────────────────


async def _entry_out(
    scope: LiteScope, ctx: Ctx, e: ReservationWaitlist, now: datetime
) -> dict[str, Any]:
    service = await scope.session.get(ReservationService, e.service_id) if e.service_id else None
    staff = await scope.session.get(ReservationStaff, e.staff_id) if e.staff_id else None
    fits_now: bool | None = None
    if ctx.mode == "capacity" and e.desired_day and e.desired_time and e.status == "waiting":
        cap = await capacity_day(scope.session, ctx, e.desired_day)
        at = ctx.at(e.desired_day, e.desired_time)
        fits_now = capacity_fit(
            cap.slots, cap.blocked, cap.people, cap.rules, at, e.party_size, now=now
        ).fits
    offer = (
        await scope.session.execute(
            sa.select(ReservationOfferCandidate.offer_id, ReservationOfferCandidate.deadline_at)
            .join(ReservationOffer, ReservationOffer.id == ReservationOfferCandidate.offer_id)
            .where(
                ReservationOfferCandidate.waitlist_id == e.id,
                ReservationOfferCandidate.status == "waiting",
                ReservationOffer.status == "running",
            )
            .limit(1)
        )
    ).first()
    booking_local = None
    if e.reservation_id is not None:
        current = await scope.session.get(Reservation, e.reservation_id)
        if current is not None:
            a, b = ctx.local(current.starts_at), ctx.local(current.ends_at)
            booking_local = {
                "date": a.date(),
                "start": a.strftime("%H:%M"),
                "end": b.strftime("%H:%M"),
            }
    return {
        "booking_local": booking_local,
        "id": e.id,
        "status": e.status,
        "contact": {"name": e.contact_name, "phone": e.contact_phone, "conversation_id": None},
        "party_size": e.party_size,
        "desired": {
            "date": e.desired_day,
            "time": e.desired_time.strftime("%H:%M") if e.desired_time else None,
            "until": e.desired_until,
        },
        "service": {
            "id": service.id,
            "name": service.name,
            "duration_minutes": service.duration_minutes,
        }
        if service
        else None,
        "staff": {"id": staff.id, "name": staff.name} if staff else None,
        "booking_id": e.reservation_id,
        "joined": {"kind": e.joined_by_kind, "name": e.joined_by_name, "at": e.created_at},
        "fits_now": fits_now,
        "offer": {"id": offer[0], "deadline_at": offer[1]} if offer else None,
    }


@router.get("/waitlist", response_model=WaitlistOut)
async def list_waitlist(
    status_: str = Query(default="waiting", alias="status", pattern="^(waiting|all)$"),
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    scope: LiteScope = Depends(SCOPE),
) -> WaitlistOut:
    ctx = await _ctx(scope)
    now = _now()
    stmt = sa.select(ReservationWaitlist).order_by(ReservationWaitlist.created_at)
    if status_ == "waiting":
        stmt = stmt.where(ReservationWaitlist.status.in_(("waiting", "offered")))
    if from_ is not None:
        stmt = stmt.where(
            sa.or_(
                ReservationWaitlist.desired_day.is_(None), ReservationWaitlist.desired_day >= from_
            )
        )
    if to is not None:
        stmt = stmt.where(
            sa.or_(ReservationWaitlist.desired_day.is_(None), ReservationWaitlist.desired_day <= to)
        )
    rows = list((await scope.session.execute(stmt.limit(500))).scalars())
    return WaitlistOut.model_validate(
        {
            "enabled": ctx.settings.waitlist_enabled,
            "items": [await _entry_out(scope, ctx, e, now) for e in rows],
        }
    )


@router.post("/waitlist", response_model=WaitlistEntryOut, status_code=201)
async def add_waitlist(
    body: WaitlistIn,
    scope: LiteScope = Depends(SCOPE),
    redis: Redis = Depends(get_redis),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> WaitlistEntryOut:
    ctx = await _ctx(scope)
    now = _now()
    prior = await _idem(redis, scope, "waitlist", idempotency_key)
    entry = await scope.session.get(ReservationWaitlist, prior) if prior else None
    if entry is None:
        try:
            entry = await waitlist.join(
                scope.session,
                ctx,
                waitlist.NewEntry(
                    contact_name=body.name.strip(),
                    contact_phone=(body.phone or "").strip() or None,
                    joined_by_kind="in_person" if body.in_person else "person",
                    joined_by_name=_actor(scope).name,
                    customer_id=await contact_customer(scope.session, ctx, body.phone, body.name),
                    party_size=body.party_size,
                    desired_day=body.date,
                    desired_time=_hm(body.time) if body.time else None,
                    desired_until=body.until,
                    service_id=body.service_id,
                    staff_id=body.staff_id,
                ),
            )
        except ReservationError as exc:
            _raise(exc)
        await _remember(redis, scope, "waitlist", idempotency_key, entry.id)
    return WaitlistEntryOut.model_validate(await _entry_out(scope, ctx, entry, now))


async def _entry(scope: LiteScope, entry_id: uuid.UUID) -> ReservationWaitlist:
    e = await scope.session.get(ReservationWaitlist, entry_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Not found")
    return e


@router.post("/waitlist/{entry_id}/remove", status_code=204)
async def remove_waitlist(entry_id: uuid.UUID, scope: LiteScope = Depends(SCOPE)) -> Response:
    await _ctx(scope)
    await waitlist.remove(scope.session, await _entry(scope, entry_id))
    return Response(status_code=204)


async def _offer_out(scope: LiteScope, ctx: Ctx, o: ReservationOffer) -> OfferOut:
    cands = (
        await scope.session.execute(
            sa.select(ReservationOfferCandidate, ReservationWaitlist.contact_name)
            .join(
                ReservationWaitlist, ReservationWaitlist.id == ReservationOfferCandidate.waitlist_id
            )
            .where(ReservationOfferCandidate.offer_id == o.id)
            .order_by(ReservationOfferCandidate.position)
        )
    ).all()
    staff = await scope.session.get(ReservationStaff, o.staff_id) if o.staff_id else None
    service = await scope.session.get(ReservationService, o.service_id) if o.service_id else None
    a, b = ctx.local(o.starts_at), ctx.local(o.ends_at)
    return OfferOut.model_validate(
        {
            "id": o.id,
            "status": o.status,
            "slot": {
                "local": {
                    "date": a.date(),
                    "start": a.strftime("%H:%M"),
                    "end": b.strftime("%H:%M"),
                },
                "staff": {"id": staff.id, "name": staff.name} if staff else None,
                "service": {"id": service.id, "name": service.name} if service else None,
                "seats": o.seats,
            },
            "cancelled_by_name": o.cancelled_by_name,
            "window_minutes": o.window_minutes,
            "candidates": [
                {
                    "position": c.position,
                    "waitlist_id": c.waitlist_id,
                    "name": name,
                    "status": c.status,
                    "deadline_at": c.deadline_at,
                    "answered_at": c.answered_at,
                }
                for c, name in cands
            ],
            "filled_booking_id": o.filled_reservation_id,
            "created_at": o.created_at,
        }
    )


@router.post("/waitlist/{entry_id}/offer", response_model=OfferOut)
async def offer_waitlist(entry_id: uuid.UUID, scope: LiteScope = Depends(SCOPE)) -> OfferOut:
    ctx = await _ctx(scope)
    _need(ctx, "capacity")
    entry = await _entry(scope, entry_id)
    try:
        offer = await waitlist.offer_manual(scope.session, ctx, entry, _now())
    except ReservationError as exc:
        _raise(exc)
    return await _offer_out(scope, ctx, offer)


@router.get("/offers", response_model=OfferListOut)
async def list_offers(
    status_: str = Query(default="running", alias="status", pattern="^(running|recent)$"),
    scope: LiteScope = Depends(SCOPE),
) -> OfferListOut:
    ctx = await _ctx(scope)
    stmt = sa.select(ReservationOffer).order_by(ReservationOffer.created_at.desc())
    if status_ == "running":
        stmt = stmt.where(ReservationOffer.status == "running")
    else:
        stmt = stmt.where(
            ReservationOffer.status != "running",
            ReservationOffer.closed_at >= _now() - timedelta(hours=24),
        )
    rows = list((await scope.session.execute(stmt.limit(100))).scalars())
    return OfferListOut(items=[await _offer_out(scope, ctx, o) for o in rows])


@router.post("/offers/{offer_id}/stop", response_model=OfferOut)
async def stop_offer(offer_id: uuid.UUID, scope: LiteScope = Depends(SCOPE)) -> OfferOut:
    ctx = await _ctx(scope)
    offer = await scope.session.get(ReservationOffer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="Not found")
    await waitlist.stop(scope.session, offer, _now())
    return await _offer_out(scope, ctx, offer)


__all__ = ["router"]
