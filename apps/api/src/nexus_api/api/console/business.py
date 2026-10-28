"""``/console/clients/{ref}/business/*`` — las secciones de la ficha que escribe
la persona: datos básicos, sedes, horario, fechas especiales, servicios,
políticas y preguntas frecuentes (spec 047, T057 y T058; ``console-api.md`` §3).

Cada sección tiene su ``revision`` (y su ``ETag``). Las escrituras **exigen**
``If-Match`` con la que la pantalla leyó: sin él, ``428``; con una vieja,
``412`` con ``{code: "revision_conflict", current, changes}`` —la sección tal
como está y lo que cambió desde entonces—, y no queda nada escrito (requisito
13.4). Dos personas en secciones distintas no chocan.

Toda escritura pasa por los servicios de ``services/business`` y de ahí por
``writes.write_section``: historial, procedencia, la revisión de la sección y
``content_rev``, y la recompilación de los agentes del cliente, que usan el dato
nuevo desde el siguiente mensaje sin publicar (8.4).

El cliente es el de ``{ref}`` bajo el partner del token (``client_scope``): un
id de otro cliente es el mismo ``404`` que uno inventado. La vista entera de la
ficha (``GET /``), los enlaces, las fuentes, las sugerencias, el historial y
exportar o importar viven en las rutas de la ficha (T068).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import BusinessSection, Tenant
from nexus_api.db.models.business import BusinessLocation
from nexus_api.services.business import (
    faqs,
    hours,
    locations,
    profile_edits,
    section_write,
    services_catalog,
    special_dates,
)
from nexus_api.services.business.sections import INITIAL_STATES, Actor
from nexus_api.services.business.writes import SectionRevisionConflict

from .deps import ClientScope, client_scope
from .schemas_business_sections import (
    AgentOption,
    AgentRef,
    AgentsOfService,
    BasicsIn,
    BasicsOut,
    FaqIn,
    FaqOut,
    FaqPatchIn,
    FaqsOut,
    HoursIn,
    HoursOut,
    LocationIn,
    LocationOut,
    LocationPatchIn,
    LocationsOut,
    PoliciesIn,
    PoliciesOut,
    PriceOut,
    SectionState,
    ServiceAgentsIn,
    ServiceIn,
    ServiceOut,
    ServicePatchIn,
    ServicesOut,
    ShiftOut,
    SpecialDateIn,
    SpecialDateOut,
    SpecialDatePatchIn,
    SpecialDatesOut,
)

router = APIRouter(prefix="/clients/{ref}/business", tags=["console-business"])

READ = client_scope("clients:read")
WRITE = client_scope("clients:write")

Out = TypeVar("Out", bound=BaseModel)


# ── lo común ───────────────────────────────────────────────────────────────


def _actor(scope: ClientScope) -> Actor:
    return Actor(kind="partner_member", id=scope.principal.user_id, origin="console")


def _allowed(scope: ClientScope) -> list[Any]:
    return ["edit"] if "clients:write" in scope.principal.permissions else []


def etag(revision: int) -> str:
    return f'"{revision}"'


def required_revision(if_match: str | None) -> int:
    """``"5"``, ``W/"5"`` o ``5`` → 5. Sin él, ``428``; otra cosa, ``400``."""
    if if_match is None:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail={"code": "revision_required"},
        )
    raw = if_match.strip()
    if raw.startswith("W/"):
        raw = raw[2:]
    raw = raw.strip().strip('"')
    if not raw.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "revision_invalid"}
        )
    return int(raw)


async def section_meta(
    session: AsyncSession, tenant_id: uuid.UUID, section: str
) -> tuple[int, SectionState]:
    """La revisión y el estado de una sección (los de alta si aún no tiene fila)."""
    row = await session.get(BusinessSection, (tenant_id, section))
    if row is None:
        return 0, cast(SectionState, INITIAL_STATES[section])
    return row.revision, cast(SectionState, row.state)


async def _section(scope: ClientScope, section: str) -> tuple[int, SectionState]:
    return await section_meta(scope.session, scope.tenant.id, section)


def _invalid(code: str, **info: Any) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": code, **{k: v for k, v in info.items() if v is not None}},
    )


def domain_refusal(exc: Exception) -> HTTPException | None:
    """Los «no» del dominio de cada sección, como respuesta (``422`` con su
    código, ``404`` si no existe). ``None``: no es un «no» del dominio. Lo
    comparten esta consola y la lite (spec 047, T167)."""
    if isinstance(exc, hours.HoursError):
        return _invalid(exc.code, day=exc.day, message=str(exc))
    if isinstance(
        exc,
        (
            locations.LocationError,
            services_catalog.ServiceError,
            faqs.FaqError,
            profile_edits.InvalidField,
        ),
    ):
        return _invalid(exc.code, field=exc.field)
    if isinstance(exc, profile_edits.BagCurrencyLocked):
        return _invalid("wallet_currency_locked", field="wallet_currency")
    if isinstance(exc, LookupError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return None


async def _run(
    scope: ClientScope,
    response: Response,
    work: Callable[[], Awaitable[Any]],
    view: Callable[[], Awaitable[Out]],
) -> tuple[Any, Out]:
    """Escribe y responde la sección como queda; traduce los «no» del dominio."""
    try:
        result = await work()
    except SectionRevisionConflict as exc:
        # The savepoint rolled back and expired what it had touched: reload
        # what the views read off the scope before answering what is there now.
        await scope.session.refresh(scope.tenant)
        await scope.session.refresh(scope.mapping)
        current = await view()
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={
                "code": "revision_conflict",
                "current": current.model_dump(mode="json", by_alias=True),
                "changes": exc.changes,
            },
            headers={"ETag": etag(exc.current)},
        ) from None
    except Exception as exc:
        refusal = domain_refusal(exc)
        if refusal is None:
            raise
        raise refusal from None
    out = await view()
    response.headers["ETag"] = etag(int(getattr(out, "revision", 0)))
    return result, out


def _shifts(days: dict[str, list[dict[str, Any]]]) -> dict[str, list[ShiftOut]]:
    return {d: [ShiftOut(**s) for s in shifts] for d, shifts in days.items()}


EMPTY_DAYS: dict[str, list[dict[str, Any]]] = {d: [] for d in hours.DAY_KEYS}


# ── datos básicos ──────────────────────────────────────────────────────────


async def _nested(scope: ClientScope, work: Callable[[], Awaitable[Any]]) -> Any:
    """``profile_edits`` escribe en la transacción del llamante: en un
    *savepoint*, un ``412`` no deja nada escrito y responde lo que hay."""
    await section_write.ensure_profile(scope.session, scope.tenant.id)
    async with scope.session.begin_nested():
        return await work()


async def _basics_out(scope: ClientScope) -> BasicsOut:
    profile = await section_write.ensure_profile(scope.session, scope.tenant.id)
    tenant = await scope.session.get(Tenant, scope.tenant.id)
    assert tenant is not None
    revision, state = await _section(scope, "basics")
    return BasicsOut(
        revision=revision,
        state=state,
        allowed=_allowed(scope),
        name=tenant.name,
        niche=profile.niche,
        info=profile.info,
        website=profile.website,
        country=profile.country,
        timezone=profile.timezone,
        price_currency=profile.price_currency,
        eu_only=profile.eu_only,
    )


@router.get("/basics", response_model=BasicsOut)
async def get_basics(response: Response, scope: ClientScope = Depends(READ)) -> BasicsOut:
    out = await _basics_out(scope)
    response.headers["ETag"] = etag(out.revision)
    return out


@router.put("/basics", response_model=BasicsOut)
async def put_basics(
    body: BasicsIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(WRITE),
) -> BasicsOut:
    expected = required_revision(if_match)
    changes = body.model_dump(exclude_unset=True)
    _, out = await _run(
        scope,
        response,
        lambda: _nested(
            scope,
            lambda: profile_edits.update_basics(
                scope.session,
                changes,
                actor=_actor(scope),
                expected_revision=expected,
                audit_actor=scope.principal.actor,
            ),
        ),
        lambda: _basics_out(scope),
    )
    return out


# ── horario ────────────────────────────────────────────────────────────────


async def _location_or_404(scope: ClientScope, location_id: uuid.UUID | None) -> None:
    if location_id is None:
        return
    loc = await scope.session.get(BusinessLocation, location_id)
    if loc is None or loc.tenant_id != scope.tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


async def _hours_out(scope: ClientScope, location_id: uuid.UUID | None) -> HoursOut:
    return await hours_view(scope.session, scope.tenant.id, location_id, allowed=_allowed(scope))


async def hours_view(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID | None,
    *,
    allowed: list[Any],
) -> HoursOut:
    """El horario del negocio o de una sede, con su frase (también la lite)."""
    locale = await hours.business_locale(session, tenant_id)
    own = (
        await hours.load_week(session, location_id=location_id) if location_id is not None else None
    )
    effective = await hours.load_hours(session, location_id=location_id)
    week = effective.week
    revision, state = await section_meta(
        session, tenant_id, "hours" if location_id is None else "locations"
    )
    return HoursOut(
        revision=revision,
        state=state,
        allowed=allowed,
        location_id=location_id,
        inherits=location_id is not None and own is None,
        layout=week.layout if week is not None else None,  # type: ignore[arg-type]
        days=_shifts(hours.week_to_days(week) if week is not None else EMPTY_DAYS),  # type: ignore[arg-type]
        label=hours.phrase(week, locale=locale),
    )


@router.get("/hours", response_model=HoursOut)
async def get_hours(
    response: Response,
    location_id: uuid.UUID | None = Query(default=None),
    scope: ClientScope = Depends(READ),
) -> HoursOut:
    await _location_or_404(scope, location_id)
    out = await _hours_out(scope, location_id)
    response.headers["ETag"] = etag(out.revision)
    return out


def week_of(body: HoursIn, location_id: uuid.UUID | None) -> hours.Week | None:
    """La semana que se guarda (``None`` quita el horario o hereda el del
    negocio). Pasar a bloques con días distintos responde ``409`` con lo que se
    perdería, hasta que llega ``confirm_loss`` (10.6). También la lite."""
    if body.inherit or body.clear:
        if (body.inherit and location_id is None) or (body.clear and location_id is not None):
            raise _invalid("invalid_target")
        return None
    try:
        week = hours.week_from_days(
            "daily",
            {d: [s.model_dump(exclude={"overnight"}) for s in v] for d, v in body.days.items()},
        )
        if body.layout == "blocks":
            lost = hours.blocks_loss(week)
            if lost and not body.confirm_loss:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "blocks_lose_days",
                        "lost": lost,
                        "keeps": [
                            {"open": s.hhmm()[0], "close": s.hhmm()[1]} for s in week.days[0]
                        ],
                    },
                )
            week = hours.to_blocks(week)
    except hours.HoursError as exc:
        raise _invalid(exc.code, day=exc.day, message=str(exc)) from None
    return week


@router.put(
    "/hours",
    response_model=HoursOut,
    responses={
        409: {"description": "blocks_lose_days: by blocks, some weekdays would be lost"},
        412: {"description": "revision_conflict"},
        422: {"description": "Invalid hours (too_many_shifts, overlap, …)"},
        428: {"description": "revision_required"},
    },
)
async def put_hours(
    body: HoursIn,
    response: Response,
    location_id: uuid.UUID | None = Query(default=None),
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(WRITE),
) -> HoursOut:
    """Por bloques o día por día, con hasta 6 turnos (requisito 10). Pasar a
    bloques con días distintos responde ``409`` con lo que se perdería, hasta
    que llega ``confirm_loss`` (10.6)."""
    expected = required_revision(if_match)
    await _location_or_404(scope, location_id)
    chosen = week_of(body, location_id)
    _, out = await _run(
        scope,
        response,
        lambda: hours.save_week(
            scope.session,
            chosen,
            actor=_actor(scope),
            location_id=location_id,
            expected_revision=expected,
        ),
        lambda: _hours_out(scope, location_id),
    )
    return out


# ── sedes ──────────────────────────────────────────────────────────────────


async def _locations_out(
    scope: ClientScope, *, archived: bool = False, created: uuid.UUID | None = None
) -> LocationsOut:
    return await locations_view(
        scope.session,
        scope.tenant.id,
        allowed=_allowed(scope),
        archived=archived,
        created=created,
    )


async def locations_view(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    allowed: list[Any],
    archived: bool = False,
    created: uuid.UUID | None = None,
) -> LocationsOut:
    """Las sedes con la frase de su horario (también la lite)."""
    locale = await hours.business_locale(session, tenant_id)
    business = await hours.load_hours(session)
    own = await locations.with_own_hours(session)
    items: list[LocationOut] = []
    for loc in await locations.list_locations(session, archived=archived):
        week = (
            await hours.load_week(session, location_id=loc.id) if loc.id in own else business.week
        )
        items.append(
            LocationOut(
                id=loc.id,
                name=loc.name,
                address=loc.address,
                phone_e164=loc.phone_e164,
                own_hours=loc.id in own,
                label=hours.phrase(week, locale=locale),
                archived=loc.archived_at is not None,
            )
        )
    revision, state = await section_meta(session, tenant_id, "locations")
    return LocationsOut(
        revision=revision, state=state, allowed=allowed, items=items, created_id=created
    )


@router.get("/locations", response_model=LocationsOut)
async def get_locations(
    response: Response,
    archived: bool = Query(default=False),
    scope: ClientScope = Depends(READ),
) -> LocationsOut:
    out = await _locations_out(scope, archived=archived)
    response.headers["ETag"] = etag(out.revision)
    return out


@router.post("/locations", response_model=LocationsOut, status_code=status.HTTP_201_CREATED)
async def post_location(
    body: LocationIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(WRITE),
) -> LocationsOut:
    expected = required_revision(if_match)
    created, out = await _run(
        scope,
        response,
        lambda: locations.create_location(
            scope.session,
            locations.LocationData(**body.model_dump()),
            actor=_actor(scope),
            expected_revision=expected,
        ),
        lambda: _locations_out(scope),
    )
    out.created_id = created[0].id
    return out


@router.patch("/locations/{location_id}", response_model=LocationsOut)
async def patch_location(
    location_id: uuid.UUID,
    body: LocationPatchIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(WRITE),
) -> LocationsOut:
    expected = required_revision(if_match)
    changes = body.model_dump(exclude_unset=True)
    _, out = await _run(
        scope,
        response,
        lambda: locations.update_location(
            scope.session, location_id, changes, actor=_actor(scope), expected_revision=expected
        ),
        lambda: _locations_out(scope),
    )
    return out


async def _archive_location(
    scope: ClientScope, response: Response, location_id: uuid.UUID, expected: int, restore: bool
) -> LocationsOut:
    _, out = await _run(
        scope,
        response,
        lambda: locations.archive_location(
            scope.session,
            location_id,
            actor=_actor(scope),
            expected_revision=expected,
            restore=restore,
        ),
        lambda: _locations_out(scope),
    )
    return out


@router.post("/locations/{location_id}/archive", response_model=LocationsOut)
async def archive_location(
    location_id: uuid.UUID,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(WRITE),
) -> LocationsOut:
    return await _archive_location(
        scope, response, location_id, required_revision(if_match), restore=False
    )


@router.post("/locations/{location_id}/restore", response_model=LocationsOut)
async def restore_location(
    location_id: uuid.UUID,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(WRITE),
) -> LocationsOut:
    return await _archive_location(
        scope, response, location_id, required_revision(if_match), restore=True
    )


# ── fechas especiales ──────────────────────────────────────────────────────


async def _special_dates_out(
    scope: ClientScope, *, archived: bool = False, created: uuid.UUID | None = None
) -> SpecialDatesOut:
    return await special_dates_view(
        scope.session,
        scope.tenant.id,
        allowed=_allowed(scope),
        archived=archived,
        created=created,
    )


async def special_dates_view(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    allowed: list[Any],
    archived: bool = False,
    created: uuid.UUID | None = None,
) -> SpecialDatesOut:
    """Las fechas especiales con sus turnos (también la lite)."""
    items: list[SpecialDateOut] = []
    for row, sp in await special_dates.list_special_dates(session, archived=archived):
        shifts = sp.shifts if sp is not None else ()
        items.append(
            SpecialDateOut(
                id=row.id,
                name=row.name or "",
                location_id=row.location_id,
                from_=row.date_from,
                to=row.date_to,
                closed=row.closed,
                shifts=[
                    ShiftOut(open=s.hhmm()[0], close=s.hhmm()[1], overnight=s.overnight)
                    for s in shifts
                ],
                archived=row.archived_at is not None,
            )
        )
    revision, state = await section_meta(session, tenant_id, "special_dates")
    return SpecialDatesOut(
        revision=revision, state=state, allowed=allowed, items=items, created_id=created
    )


@router.get("/special-dates", response_model=SpecialDatesOut)
async def get_special_dates(
    response: Response,
    archived: bool = Query(default=False),
    scope: ClientScope = Depends(READ),
) -> SpecialDatesOut:
    out = await _special_dates_out(scope, archived=archived)
    response.headers["ETag"] = etag(out.revision)
    return out


@router.post("/special-dates", response_model=SpecialDatesOut, status_code=status.HTTP_201_CREATED)
async def post_special_date(
    body: SpecialDateIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(WRITE),
) -> SpecialDatesOut:
    expected = required_revision(if_match)
    try:
        special = special_dates.build(
            date_from=body.from_,
            date_to=body.to,
            closed=body.closed,
            shifts=[s.model_dump(exclude={"overnight"}) for s in body.shifts],
            name=body.name,
            location_id=body.location_id,
        )
    except hours.HoursError as exc:
        raise _invalid(exc.code, message=str(exc)) from None
    created, out = await _run(
        scope,
        response,
        lambda: special_dates.create_special_date(
            scope.session, special, actor=_actor(scope), expected_revision=expected
        ),
        lambda: _special_dates_out(scope),
    )
    out.created_id = created[0]
    return out


@router.patch("/special-dates/{special_id}", response_model=SpecialDatesOut)
async def patch_special_date(
    special_id: uuid.UUID,
    body: SpecialDatePatchIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(WRITE),
) -> SpecialDatesOut:
    expected = required_revision(if_match)
    raw = body.model_dump(exclude_unset=True)
    changes: dict[str, Any] = {}
    for key, value in raw.items():
        if key == "from_":
            changes["from"] = value
        elif key == "shifts" and value is not None:
            changes["shifts"] = [{"open": s["open"], "close": s["close"]} for s in value]
        else:
            changes[key] = value
    _, out = await _run(
        scope,
        response,
        lambda: special_dates.update_special_date(
            scope.session, special_id, changes, actor=_actor(scope), expected_revision=expected
        ),
        lambda: _special_dates_out(scope),
    )
    return out


@router.post("/special-dates/{special_id}/archive", response_model=SpecialDatesOut)
async def archive_special_date(
    special_id: uuid.UUID,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(WRITE),
) -> SpecialDatesOut:
    expected = required_revision(if_match)
    _, out = await _run(
        scope,
        response,
        lambda: special_dates.archive_special_date(
            scope.session, special_id, actor=_actor(scope), expected_revision=expected
        ),
        lambda: _special_dates_out(scope),
    )
    return out


# ── servicios ──────────────────────────────────────────────────────────────


async def _services_out(
    scope: ClientScope, *, archived: bool = False, created: uuid.UUID | None = None
) -> ServicesOut:
    return await services_view(
        scope.session,
        scope.tenant.id,
        allowed=_allowed(scope),
        archived=archived,
        created=created,
    )


async def services_view(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    allowed: list[Any],
    archived: bool = False,
    created: uuid.UUID | None = None,
) -> ServicesOut:
    """Los servicios con su precio y su duración (también la lite)."""
    agents = await services_catalog.client_agents(session)
    rows = await services_catalog.agent_rows(session)
    order = {a.id: i for i, a in enumerate(agents)}
    items: list[ServiceOut] = []
    for svc in await services_catalog.list_services(session, archived=archived):
        listed = sorted(rows.get(svc.id, set()), key=lambda a: (order.get(a, len(order)), str(a)))
        items.append(
            ServiceOut(
                id=svc.id,
                name=svc.name,
                description=svc.description,
                bookable=svc.bookable,
                duration_min=svc.duration_minutes,
                price=PriceOut(**services_catalog.price_view(svc)),
                currency=svc.currency,
                staff="all" if svc.all_staff else await services_catalog.staff_of(session, svc.id),
                agents=AgentsOfService(
                    mode="list" if listed else "all_agents", agent_ids=list(listed)
                ),
                used_by=[
                    AgentRef(id=a.id, name=a.name)
                    for a in services_catalog.used_by(svc.id, agents, rows)
                ],
                archived=svc.archived_at is not None,
            )
        )
    currency = await services_catalog.business_currency(session, tenant_id)
    revision, state = await section_meta(session, tenant_id, "services")
    return ServicesOut(
        revision=revision,
        state=state,
        allowed=allowed,
        currency=currency,
        exponent=services_catalog.exponent(currency),
        items=items,
        agents=[
            AgentOption(id=a.id, name=a.name, serves_all=a.serves_all_services) for a in agents
        ],
        created_id=created,
    )


@router.get("/services", response_model=ServicesOut)
async def get_services(
    response: Response,
    archived: bool = Query(default=False),
    scope: ClientScope = Depends(READ),
) -> ServicesOut:
    out = await _services_out(scope, archived=archived)
    response.headers["ETag"] = etag(out.revision)
    return out


def _service_data(body: ServiceIn) -> services_catalog.ServiceData:
    return services_catalog.ServiceData(
        name=body.name,
        bookable=body.bookable,
        duration_min=body.duration_min,
        description=body.description,
        price_kind=body.price.kind,
        amount_minor=body.price.amount_minor,
        staff_ids=None if body.staff == "all" else tuple(body.staff),
    )


@router.post("/services", response_model=ServicesOut, status_code=status.HTTP_201_CREATED)
async def post_service(
    body: ServiceIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(WRITE),
) -> ServicesOut:
    expected = required_revision(if_match)
    created, out = await _run(
        scope,
        response,
        lambda: services_catalog.create_service(
            scope.session, _service_data(body), actor=_actor(scope), expected_revision=expected
        ),
        lambda: _services_out(scope),
    )
    out.created_id = created[0]
    return out


@router.patch("/services/{service_id}", response_model=ServicesOut)
async def patch_service(
    service_id: uuid.UUID,
    body: ServicePatchIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(WRITE),
) -> ServicesOut:
    expected = required_revision(if_match)
    changes = body.model_dump(exclude_unset=True)
    _, out = await _run(
        scope,
        response,
        lambda: services_catalog.update_service(
            scope.session, service_id, changes, actor=_actor(scope), expected_revision=expected
        ),
        lambda: _services_out(scope),
    )
    return out


@router.post("/services/{service_id}/archive", response_model=ServicesOut)
async def archive_service(
    service_id: uuid.UUID,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(WRITE),
) -> ServicesOut:
    expected = required_revision(if_match)
    _, out = await _run(
        scope,
        response,
        lambda: services_catalog.archive_service(
            scope.session, service_id, actor=_actor(scope), expected_revision=expected
        ),
        lambda: _services_out(scope),
    )
    return out


@router.post(
    "/services/{service_id}/duplicate",
    response_model=ServicesOut,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_service(
    service_id: uuid.UUID,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(WRITE),
) -> ServicesOut:
    expected = required_revision(if_match)
    created, out = await _run(
        scope,
        response,
        lambda: services_catalog.duplicate_service(
            scope.session, service_id, actor=_actor(scope), expected_revision=expected
        ),
        lambda: _services_out(scope),
    )
    out.created_id = created[0]
    return out


@router.put("/services/{service_id}/agents", response_model=ServicesOut)
async def put_service_agents(
    service_id: uuid.UUID,
    body: ServiceAgentsIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(WRITE),
) -> ServicesOut:
    """«Para todos los agentes» o una lista (requisitos 11.2 y 11.3)."""
    expected = required_revision(if_match)
    _, out = await _run(
        scope,
        response,
        lambda: services_catalog.set_service_agents(
            scope.session,
            service_id,
            mode=body.mode,
            agent_ids=body.agent_ids,
            actor=_actor(scope),
            expected_revision=expected,
        ),
        lambda: _services_out(scope),
    )
    return out


# ── políticas ──────────────────────────────────────────────────────────────


async def _policies_out(scope: ClientScope) -> PoliciesOut:
    profile = await section_write.ensure_profile(scope.session, scope.tenant.id)
    values = dict(profile.policies or {})
    revision, state = await _section(scope, "policies")
    return PoliciesOut(
        revision=revision,
        state=state,
        allowed=_allowed(scope),
        **{k: (str(values[k]) if values.get(k) else None) for k in profile_edits.POLICY_KEYS},
    )


@router.get("/policies", response_model=PoliciesOut)
async def get_policies(response: Response, scope: ClientScope = Depends(READ)) -> PoliciesOut:
    out = await _policies_out(scope)
    response.headers["ETag"] = etag(out.revision)
    return out


@router.put("/policies", response_model=PoliciesOut)
async def put_policies(
    body: PoliciesIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(WRITE),
) -> PoliciesOut:
    """Cancelación, pagos, señal y no presentarse, tal cual llegan."""
    expected = required_revision(if_match)
    _, out = await _run(
        scope,
        response,
        lambda: _nested(
            scope,
            lambda: profile_edits.update_policies(
                scope.session,
                body.model_dump(),
                actor=_actor(scope),
                expected_revision=expected,
                replace=True,
                audit_actor=scope.principal.actor,
            ),
        ),
        lambda: _policies_out(scope),
    )
    return out


# ── preguntas frecuentes ───────────────────────────────────────────────────


async def _faqs_out(scope: ClientScope, *, created: uuid.UUID | None = None) -> FaqsOut:
    items = [
        FaqOut(id=f.id, q=f.q, a=f.a, suggested=f.suggested)
        for f in await faqs.list_faqs(scope.session)
    ]
    revision, state = await _section(scope, "faqs")
    return FaqsOut(
        revision=revision, state=state, allowed=_allowed(scope), items=items, created_id=created
    )


@router.get("/faqs", response_model=FaqsOut)
async def get_faqs(response: Response, scope: ClientScope = Depends(READ)) -> FaqsOut:
    out = await _faqs_out(scope)
    response.headers["ETag"] = etag(out.revision)
    return out


@router.post("/faqs", response_model=FaqsOut, status_code=status.HTTP_201_CREATED)
async def post_faq(
    body: FaqIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(WRITE),
) -> FaqsOut:
    expected = required_revision(if_match)
    created, out = await _run(
        scope,
        response,
        lambda: faqs.create_faq(
            scope.session, q=body.q, a=body.a, actor=_actor(scope), expected_revision=expected
        ),
        lambda: _faqs_out(scope),
    )
    out.created_id = created[0]
    return out


@router.patch("/faqs/{faq_id}", response_model=FaqsOut)
async def patch_faq(
    faq_id: uuid.UUID,
    body: FaqPatchIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(WRITE),
) -> FaqsOut:
    expected = required_revision(if_match)
    changes = body.model_dump(exclude_unset=True)
    _, out = await _run(
        scope,
        response,
        lambda: faqs.update_faq(
            scope.session, faq_id, changes, actor=_actor(scope), expected_revision=expected
        ),
        lambda: _faqs_out(scope),
    )
    return out


@router.post("/faqs/{faq_id}/archive", response_model=FaqsOut)
async def archive_faq(
    faq_id: uuid.UUID,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(WRITE),
) -> FaqsOut:
    expected = required_revision(if_match)
    _, out = await _run(
        scope,
        response,
        lambda: faqs.archive_faq(
            scope.session, faq_id, actor=_actor(scope), expected_revision=expected
        ),
        lambda: _faqs_out(scope),
    )
    return out


__all__ = [
    "domain_refusal",
    "etag",
    "hours_view",
    "locations_view",
    "required_revision",
    "router",
    "section_meta",
    "services_view",
    "special_dates_view",
    "week_of",
]
