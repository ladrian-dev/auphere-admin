"""``/console/lite/business/*`` — Negocio para la persona del cliente (spec 047,
T167; requisitos 50.1, 50.4, 9, 10, 11 y 13; ``contracts/lite-app-api.md`` §2).
Solo módulo ``business``.

Las mismas operaciones que la consola del partner (``api/console/business.py``),
por los mismos servicios y con las mismas vistas, restringidas a lo que el
negocio sabe mejor que nadie (50.1):

- ``GET /business``: horario, fechas especiales, servicios y sedes, cada uno con
  su ``revision``, su procedencia y el historial de esas secciones;
- ``GET /hours?location_id=``: el horario propio de una sede (o el que hereda);
- el horario (``PUT /hours``), las fechas especiales, los servicios (precio,
  duración, descripción y si es reservable; alta y archivo) y las sedes;
- ``POST /history/{change_id}/undo``: deshacer el último cambio de una de esas
  secciones (o una corrección desde la Bandeja, T176).

Cada escritura **exige** ``If-Match`` con la revisión de la sección (``428`` sin
él, ``412`` con una vieja, con lo que cambió). Con ``Idempotency-Key``, la misma
escritura reintentada (se cortó la red antes de la respuesta) no se repite ni
choca con su propia revisión: responde la sección como quedó. Y pasa por
``writes.write_section``:
historial con la persona y su origen (``lite_web`` o ``app``), procedencia,
recompilación de los agentes (el siguiente mensaje ya lo sabe, 8.4), las pruebas
afectadas en segundo plano (13.7) y ``client.business_changed`` al partner (13.6).

Los datos básicos, las políticas, las preguntas frecuentes, las fuentes, quién
hace cada servicio y qué agentes lo usan son del partner: no tienen ruta (50.3).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Final, TypeVar

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from redis.asyncio import Redis

from nexus_api.api.deps import get_redis
from nexus_api.db.models.business import BusinessChange, BusinessLocation
from nexus_api.services.business import (
    history,
    hours,
    locations,
    services_catalog,
    special_dates,
)
from nexus_api.services.business.profile_edits import InvalidField
from nexus_api.services.business.provenance import people_names, provenance_map
from nexus_api.services.business.sections import Actor
from nexus_api.services.business.writes import SectionRevisionConflict, WriteContext

from ..business import (
    domain_refusal,
    etag,
    hours_view,
    locations_view,
    required_revision,
    services_view,
    special_dates_view,
    week_of,
)
from ..schemas_business_sections import (
    HoursIn,
    HoursOut,
    LocationIn,
    LocationPatchIn,
    LocationsOut,
    PriceIn,
    ServicesOut,
    SpecialDateIn,
    SpecialDatePatchIn,
    SpecialDatesOut,
)
from .deps import LiteScope, lite_scope

router = APIRouter(prefix="/business")

BUSINESS = lite_scope("business")

#: Las secciones que el negocio edita desde la lite y la app (50.1).
LITE_SECTIONS: Final[tuple[str, ...]] = ("hours", "special_dates", "services", "locations")
#: Toda persona del cliente puede editar su ficha: no hay papeles (50.2).
ALLOWED: Final[list[Any]] = ["edit"]
HISTORY_LIMIT: Final = 20

Out = TypeVar("Out", bound=BaseModel)


# ── formas ─────────────────────────────────────────────────────────────────


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LiteServiceIn(_In):
    """Un servicio nuevo. Quién lo hace y qué agentes lo usan son del partner."""

    name: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    description: Annotated[str, StringConstraints(max_length=1000)] | None = None
    bookable: bool = True
    duration_min: int | None = None
    price: PriceIn = Field(default_factory=lambda: PriceIn(kind="none"))


class LiteServicePatchIn(_In):
    """Precio, duración, descripción y si es reservable (``lite-app-api.md`` §2)."""

    description: Annotated[str, StringConstraints(max_length=1000)] | None = None
    bookable: bool | None = None
    duration_min: int | None = None
    price: PriceIn | None = None


class LitePersonOut(BaseModel):
    kind: str
    name: str | None = None


class LiteProvenanceOut(BaseModel):
    """«Editado por Marta desde la app», «Leído de la web · revísalo»…"""

    source: str
    by: LitePersonOut | None = None
    origin: str | None = None
    at: str | None = None
    review: str | None = None


class LiteChangeOut(BaseModel):
    id: uuid.UUID
    section: str
    kind: str
    at: datetime
    by: LitePersonOut | None = None
    origin: str
    undone_at: datetime | None = None
    undoable: bool


class LiteBusinessSectionsOut(BaseModel):
    hours: HoursOut
    special_dates: SpecialDatesOut
    services: ServicesOut
    locations: LocationsOut
    #: Por puntero del ClientSpec, solo de las cuatro secciones.
    provenance: dict[str, LiteProvenanceOut]
    #: Los últimos cambios de esas secciones, del más nuevo al más viejo.
    history: list[LiteChangeOut]


class LiteUndoOut(BaseModel):
    section: str
    revision: int | None = None
    change_id: uuid.UUID | None = None


# ── lo común ───────────────────────────────────────────────────────────────


def _actor(scope: LiteScope) -> Actor:
    return Actor(kind="client_user", id=scope.principal.user_id, origin=scope.origin)


def _ctx(scope: LiteScope) -> WriteContext:
    """La persona del cliente, con su nombre en la auditoría (``client:<correo>``)."""
    return WriteContext(actor=_actor(scope), audit_actor=scope.principal.actor)


def _in_lite(pointer: str) -> bool:
    return any(pointer == f"/{s}" or pointer.startswith(f"/{s}/") for s in LITE_SECTIONS)


@dataclass(frozen=True)
class Replay:
    """``Idempotency-Key`` de una escritura: lo que respondió la primera vez se
    guarda un día, ya confirmado, por cliente, ruta y clave."""

    scope: LiteScope
    redis: Redis
    slot: str | None

    async def prior(self) -> dict[str, Any] | None:
        if self.slot is None:
            return None
        raw = await self.redis.get(self.slot)
        return json.loads(raw) if raw else None

    def keep(self, payload: dict[str, Any]) -> None:
        slot = self.slot
        if slot is None:
            return

        async def _store() -> None:
            await self.redis.set(slot, json.dumps(payload), ex=86400)

        self.scope.after_commit(_store)


async def replay_of(
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=80),
    redis: Redis = Depends(get_redis),
    scope: LiteScope = Depends(BUSINESS),
) -> Replay:
    slot = None
    if idempotency_key:
        slot = (
            f"lite:idem:{scope.principal.tenant_id}:business:"
            f"{request.method}:{request.url.path}:{idempotency_key}"
        )
    return Replay(scope=scope, redis=redis, slot=slot)


def _undoable_here(change: BusinessChange) -> bool:
    """Lo que la persona puede deshacer: sus cuatro secciones y lo que corrigió
    desde la Bandeja (T176)."""
    return change.section in LITE_SECTIONS or change.kind == "correction"


async def _run(
    scope: LiteScope,
    response: Response,
    work: Callable[[], Awaitable[Any]],
    view: Callable[[], Awaitable[Out]],
    replay: Replay,
    created: Callable[[Any], uuid.UUID] | None = None,
) -> tuple[uuid.UUID | None, Out]:
    """Escribe y responde la sección como queda (y el id de lo que creó);
    traduce los «no» del dominio igual que la consola del partner. Un reintento
    con la misma ``Idempotency-Key`` no escribe otra vez."""
    prior = await replay.prior()
    if prior is not None:
        out = await view()
        response.headers["ETag"] = etag(int(getattr(out, "revision", 0)))
        made = prior.get("created_id")
        return (uuid.UUID(made) if made else None), out
    try:
        result = await work()
    except SectionRevisionConflict as exc:
        # El savepoint se deshizo y caducó lo que tocó: se relee el cliente.
        await scope.session.refresh(scope.tenant)
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
    made = created(result) if created is not None else None
    replay.keep({"created_id": str(made) if made else None})
    return made, out


async def _hours(scope: LiteScope, location_id: uuid.UUID | None = None) -> HoursOut:
    return await hours_view(scope.session, scope.tenant.id, location_id, allowed=ALLOWED)


async def _special_dates(scope: LiteScope, created: uuid.UUID | None = None) -> SpecialDatesOut:
    return await special_dates_view(
        scope.session, scope.tenant.id, allowed=ALLOWED, created=created
    )


async def _services(scope: LiteScope, created: uuid.UUID | None = None) -> ServicesOut:
    return await services_view(scope.session, scope.tenant.id, allowed=ALLOWED, created=created)


async def _locations(scope: LiteScope, created: uuid.UUID | None = None) -> LocationsOut:
    return await locations_view(scope.session, scope.tenant.id, allowed=ALLOWED, created=created)


async def _provenance(scope: LiteScope) -> dict[str, LiteProvenanceOut]:
    raw = await provenance_map(scope.session, partner_id=scope.principal.partner.id)
    out: dict[str, LiteProvenanceOut] = {}
    for pointer, entry in raw.items():
        if not _in_lite(pointer):
            continue
        person = entry.get("by")
        out[pointer] = LiteProvenanceOut(
            source=str(entry.get("source")),
            by=LitePersonOut(kind=person.kind, name=person.name) if person is not None else None,
            origin=entry.get("origin"),
            at=entry.get("at"),
            review=entry.get("review"),
        )
    return out


async def _history(scope: LiteScope) -> list[LiteChangeOut]:
    views = [
        v for v in await history.list_history(scope.session, limit=100) if _undoable_here(v.row)
    ][:HISTORY_LIMIT]
    names = await people_names(
        scope.principal.partner.id,
        scope.tenant.id,
        [(v.row.actor_kind, v.row.actor_id) for v in views],
    )
    out: list[LiteChangeOut] = []
    for v in views:
        row = v.row
        name = names.get((row.actor_kind, row.actor_id or "")) if row.actor_kind else None
        out.append(
            LiteChangeOut(
                id=row.id,
                section=row.section,
                kind=row.kind,
                at=row.at,
                by=LitePersonOut(kind=row.actor_kind, name=name) if row.actor_kind else None,
                origin=row.origin,
                undone_at=row.undone_at,
                undoable=v.undoable,
            )
        )
    return out


async def _location_or_404(scope: LiteScope, location_id: uuid.UUID | None) -> None:
    if location_id is None:
        return
    loc = await scope.session.get(BusinessLocation, location_id)
    if loc is None or loc.tenant_id != scope.tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


# ── leer ───────────────────────────────────────────────────────────────────


@router.get("", response_model=LiteBusinessSectionsOut)
async def get_business(scope: LiteScope = Depends(BUSINESS)) -> LiteBusinessSectionsOut:
    return LiteBusinessSectionsOut(
        hours=await _hours(scope),
        special_dates=await _special_dates(scope),
        services=await _services(scope),
        locations=await _locations(scope),
        provenance=await _provenance(scope),
        history=await _history(scope),
    )


@router.get("/hours", response_model=HoursOut)
async def get_hours(
    response: Response,
    location_id: uuid.UUID | None = Query(default=None),
    scope: LiteScope = Depends(BUSINESS),
) -> HoursOut:
    """El horario de una sede (el suyo o el que hereda) o el del negocio:
    ``GET /business`` solo trae el del negocio."""
    await _location_or_404(scope, location_id)
    out = await _hours(scope, location_id)
    response.headers["ETag"] = etag(out.revision)
    return out


# ── horario ────────────────────────────────────────────────────────────────

_WRITE_RESPONSES: dict[int | str, dict[str, Any]] = {
    412: {"description": "revision_conflict"},
    422: {"description": "Invalid value"},
    428: {"description": "revision_required"},
}


@router.put(
    "/hours",
    response_model=HoursOut,
    responses={
        409: {"description": "blocks_lose_days: by blocks, some weekdays would be lost"},
        **_WRITE_RESPONSES,
    },
)
async def put_hours(
    body: HoursIn,
    response: Response,
    location_id: uuid.UUID | None = Query(default=None),
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: LiteScope = Depends(BUSINESS),
    replay: Replay = Depends(replay_of),
) -> HoursOut:
    """El horario del negocio o de una sede. Devuelve «Así lo dirá el agente»
    (``label``, requisito 10.5)."""
    expected = required_revision(if_match)
    await _location_or_404(scope, location_id)
    week = week_of(body, location_id)
    _, out = await _run(
        scope,
        response,
        lambda: hours.save_week(
            scope.session,
            week,
            actor=_actor(scope),
            location_id=location_id,
            expected_revision=expected,
            ctx=_ctx(scope),
        ),
        lambda: _hours(scope, location_id),
        replay,
    )
    return out


# ── fechas especiales ──────────────────────────────────────────────────────


@router.post(
    "/special-dates",
    response_model=SpecialDatesOut,
    status_code=status.HTTP_201_CREATED,
    responses=_WRITE_RESPONSES,
)
async def post_special_date(
    body: SpecialDateIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: LiteScope = Depends(BUSINESS),
    replay: Replay = Depends(replay_of),
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
        refusal = domain_refusal(exc)
        assert refusal is not None
        raise refusal from None
    created, out = await _run(
        scope,
        response,
        lambda: special_dates.create_special_date(
            scope.session, special, actor=_actor(scope), expected_revision=expected, ctx=_ctx(scope)
        ),
        lambda: _special_dates(scope),
        replay,
        created=lambda result: result[0],
    )
    out.created_id = created
    return out


@router.patch(
    "/special-dates/{special_id}", response_model=SpecialDatesOut, responses=_WRITE_RESPONSES
)
async def patch_special_date(
    special_id: uuid.UUID,
    body: SpecialDatePatchIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: LiteScope = Depends(BUSINESS),
    replay: Replay = Depends(replay_of),
) -> SpecialDatesOut:
    expected = required_revision(if_match)
    changes: dict[str, Any] = {}
    for key, value in body.model_dump(exclude_unset=True).items():
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
            scope.session,
            special_id,
            changes,
            actor=_actor(scope),
            expected_revision=expected,
            ctx=_ctx(scope),
        ),
        lambda: _special_dates(scope),
        replay,
    )
    return out


@router.post(
    "/special-dates/{special_id}/archive",
    response_model=SpecialDatesOut,
    responses=_WRITE_RESPONSES,
)
async def archive_special_date(
    special_id: uuid.UUID,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: LiteScope = Depends(BUSINESS),
    replay: Replay = Depends(replay_of),
) -> SpecialDatesOut:
    expected = required_revision(if_match)
    _, out = await _run(
        scope,
        response,
        lambda: special_dates.archive_special_date(
            scope.session,
            special_id,
            actor=_actor(scope),
            expected_revision=expected,
            ctx=_ctx(scope),
        ),
        lambda: _special_dates(scope),
        replay,
    )
    return out


# ── servicios ──────────────────────────────────────────────────────────────


@router.post(
    "/services",
    response_model=ServicesOut,
    status_code=status.HTTP_201_CREATED,
    responses=_WRITE_RESPONSES,
)
async def post_service(
    body: LiteServiceIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: LiteScope = Depends(BUSINESS),
    replay: Replay = Depends(replay_of),
) -> ServicesOut:
    expected = required_revision(if_match)
    data = services_catalog.ServiceData(
        name=body.name,
        bookable=body.bookable,
        duration_min=body.duration_min,
        description=body.description,
        price_kind=body.price.kind,
        amount_minor=body.price.amount_minor,
        staff_ids=None,
    )
    created, out = await _run(
        scope,
        response,
        lambda: services_catalog.create_service(
            scope.session, data, actor=_actor(scope), expected_revision=expected, ctx=_ctx(scope)
        ),
        lambda: _services(scope),
        replay,
        created=lambda result: result[0],
    )
    out.created_id = created
    return out


@router.patch("/services/{service_id}", response_model=ServicesOut, responses=_WRITE_RESPONSES)
async def patch_service(
    service_id: uuid.UUID,
    body: LiteServicePatchIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: LiteScope = Depends(BUSINESS),
    replay: Replay = Depends(replay_of),
) -> ServicesOut:
    expected = required_revision(if_match)
    changes = body.model_dump(exclude_unset=True)
    _, out = await _run(
        scope,
        response,
        lambda: services_catalog.update_service(
            scope.session,
            service_id,
            changes,
            actor=_actor(scope),
            expected_revision=expected,
            ctx=_ctx(scope),
        ),
        lambda: _services(scope),
        replay,
    )
    return out


@router.post(
    "/services/{service_id}/archive", response_model=ServicesOut, responses=_WRITE_RESPONSES
)
async def archive_service(
    service_id: uuid.UUID,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: LiteScope = Depends(BUSINESS),
    replay: Replay = Depends(replay_of),
) -> ServicesOut:
    expected = required_revision(if_match)
    _, out = await _run(
        scope,
        response,
        lambda: services_catalog.archive_service(
            scope.session,
            service_id,
            actor=_actor(scope),
            expected_revision=expected,
            ctx=_ctx(scope),
        ),
        lambda: _services(scope),
        replay,
    )
    return out


# ── sedes ──────────────────────────────────────────────────────────────────


@router.post(
    "/locations",
    response_model=LocationsOut,
    status_code=status.HTTP_201_CREATED,
    responses=_WRITE_RESPONSES,
)
async def post_location(
    body: LocationIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: LiteScope = Depends(BUSINESS),
    replay: Replay = Depends(replay_of),
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
            ctx=_ctx(scope),
        ),
        lambda: _locations(scope),
        replay,
        created=lambda result: result[0].id,
    )
    out.created_id = created
    return out


@router.patch("/locations/{location_id}", response_model=LocationsOut, responses=_WRITE_RESPONSES)
async def patch_location(
    location_id: uuid.UUID,
    body: LocationPatchIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: LiteScope = Depends(BUSINESS),
    replay: Replay = Depends(replay_of),
) -> LocationsOut:
    expected = required_revision(if_match)
    changes = body.model_dump(exclude_unset=True)
    _, out = await _run(
        scope,
        response,
        lambda: locations.update_location(
            scope.session,
            location_id,
            changes,
            actor=_actor(scope),
            expected_revision=expected,
            ctx=_ctx(scope),
        ),
        lambda: _locations(scope),
        replay,
    )
    return out


async def _archive_location(
    scope: LiteScope,
    response: Response,
    location_id: uuid.UUID,
    expected: int,
    replay: Replay,
    *,
    restore: bool,
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
            ctx=_ctx(scope),
        ),
        lambda: _locations(scope),
        replay,
    )
    return out


@router.post(
    "/locations/{location_id}/archive", response_model=LocationsOut, responses=_WRITE_RESPONSES
)
async def archive_location(
    location_id: uuid.UUID,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: LiteScope = Depends(BUSINESS),
    replay: Replay = Depends(replay_of),
) -> LocationsOut:
    expected = required_revision(if_match)
    return await _archive_location(scope, response, location_id, expected, replay, restore=False)


@router.post(
    "/locations/{location_id}/restore", response_model=LocationsOut, responses=_WRITE_RESPONSES
)
async def restore_location(
    location_id: uuid.UUID,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: LiteScope = Depends(BUSINESS),
    replay: Replay = Depends(replay_of),
) -> LocationsOut:
    expected = required_revision(if_match)
    return await _archive_location(scope, response, location_id, expected, replay, restore=True)


# ── deshacer ───────────────────────────────────────────────────────────────


def _error(code: int, name: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"code": name})


@router.post(
    "/history/{change_id}/undo",
    response_model=LiteUndoOut,
    responses={
        404: {"description": "unknown_change"},
        409: {"description": "already_undone | undo_not_available"},
        412: {"description": "revision_conflict"},
    },
)
async def undo_change(
    change_id: uuid.UUID,
    scope: LiteScope = Depends(BUSINESS),
    replay: Replay = Depends(replay_of),
) -> LiteUndoOut:
    """Deshacer el último cambio de una sección (13.3). Si alguien escribió
    después, ``412`` con lo que cambió; nadie pisa a nadie (13.4). El reintento
    con la misma ``Idempotency-Key`` responde lo mismo, no ``already_undone``."""
    prior = await replay.prior()
    if prior is not None:
        return LiteUndoOut.model_validate(prior)
    change = await scope.session.get(BusinessChange, change_id)
    if change is None or change.tenant_id != scope.tenant.id or not _undoable_here(change):
        raise _error(status.HTTP_404_NOT_FOUND, "unknown_change")
    section = change.section
    try:
        written = await history.undo(scope.session, change_id, ctx=_ctx(scope))
    except LookupError:
        raise _error(status.HTTP_404_NOT_FOUND, "unknown_change") from None
    except history.AlreadyUndone:
        raise _error(status.HTTP_409_CONFLICT, "already_undone") from None
    except (history.UndoNotAvailable, InvalidField):
        raise _error(status.HTTP_409_CONFLICT, "undo_not_available") from None
    except SectionRevisionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={"code": "revision_conflict", "current": exc.current, "changes": exc.changes},
        ) from None
    out = (
        LiteUndoOut(section=section)
        if written is None
        else LiteUndoOut(
            section=written.section, revision=written.revision, change_id=written.change_id
        )
    )
    replay.keep(out.model_dump(mode="json"))
    return out


__all__ = ["LITE_SECTIONS", "router"]
