"""El ClientSpec — la vista tipada de la ficha del negocio (spec 047, T072, requisito 8.3).

La ficha vive en tablas por cliente (research D3); el ClientSpec es su
documento: lo que lee el constructor, el formato de importar y exportar y la
base de los parches que se proponen. **No es una fuente**: se deriva de las
tablas cada vez.

Tres piezas:

- **El modelo** (:class:`ClientSpec`), Pydantic con ``extra="forbid"``, igual a
  ``specs/047-la-fabrica-de-agentes/contracts/client-spec.schema.json``. Lo
  comprueba ``tests/unit/test_client_spec_contract.py``: los mismos campos, los
  mismos obligatorios, los mismos límites y los mismos vocabularios.
- **La vista** (:func:`export_document` y :func:`section_view`): las tablas como
  documento. ``section_view`` es lo que guardan ``before``/``after`` del
  historial (``business_changes``) para cada sección, con la forma
  ``{<clave del ClientSpec>: <valor>}``: el deshacer devuelve a la sección
  exactamente lo que se enseñó.
- **El validador sin modelo** (:func:`validate_document`, :func:`validate_value`):
  lo que Pydantic no dice (una zona que no es IANA, turnos duplicados, una
  fecha especial al revés…). Corre antes de proponer y otra vez al aplicar.

Y :func:`diff_ops`: importar un documento no escribe nada; lo convierte en las
operaciones del parche (``$defs.patch``), que ``suggestions.py`` guarda como
propuestas pendientes de una persona.

Los punteros (``/locations/{id}``, ``/business/name``…) usan el id de cada
elemento como clave en las listas, para que una propuesta siga apuntando al
mismo dato aunque cambie el orden.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from typing import Annotated, Any, Final, Literal

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic.json_schema import SkipJsonSchema
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import KnowledgeDocument, ReservationService, Tenant
from nexus_api.db.models.business import (
    MAX_SHIFTS_PER_DAY,
    MINUTES_PER_DAY,
    BusinessFaq,
    BusinessFieldProvenance,
    BusinessLink,
    BusinessLocation,
    BusinessProfile,
    BusinessSchedule,
    BusinessShift,
    BusinessSpecialDate,
    BusinessSpecialShift,
)

SCHEMA_VERSION: Final = "1"
WEEKDAYS: Final[tuple[str, ...]] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

#: Sección de la ficha → su clave en el ClientSpec.
SECTION_KEYS: Final[dict[str, str]] = {
    "basics": "business",
    "locations": "locations",
    "hours": "hours",
    "special_dates": "special_dates",
    "services": "services",
    "policies": "policies",
    "faqs": "faqs",
    "sources": "documents",
    "links": "links",
}
KEY_SECTIONS: Final[dict[str, str]] = {v: k for k, v in SECTION_KEYS.items()}
#: Lo que un parche (o un import) puede tocar; ``documents``, ``provenance`` y
#: ``business/sovereign`` no (``$defs.patch``).
WRITABLE_KEYS: Final[tuple[str, ...]] = (
    "business",
    "locations",
    "hours",
    "special_dates",
    "services",
    "policies",
    "faqs",
    "links",
)
READ_ONLY_POINTERS: Final[frozenset[str]] = frozenset({"/business/sovereign"})

_HHMM = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"
_HHMM_CLOSE = r"^(([01][0-9]|2[0-3]):[0-5][0-9]|24:00)$"
_URI: dict[str, Any] = {"format": "uri"}
_UUID: dict[str, Any] = {"format": "uuid"}
_RO: dict[str, Any] = {"readOnly": True}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Los límites van **dentro** del tipo (``Annotated``): puestos en el ``Field`` de
# un campo opcional, Pydantic no los aplica a la unión y el esquema sale sin
# ellos (lo pilló la prueba de contrato).
_Uuid = Annotated[str, Field(json_schema_extra=_UUID)]
_Uri = Annotated[str, Field(json_schema_extra=_URI)]
_Uri300 = Annotated[str, Field(max_length=300, json_schema_extra=_URI)]
_Text80 = Annotated[str, Field(max_length=80)]
_Text300 = Annotated[str, Field(max_length=300)]
_Text1000 = Annotated[str, Field(max_length=1000)]
_Text2000 = Annotated[str, Field(max_length=2000)]
_Phone = Annotated[str, Field(pattern=r"^\+[1-9][0-9]{6,14}$")]
_Handle = Annotated[str, Field(pattern=r"^@?[A-Za-z0-9._]{1,30}$")]
_Language = Annotated[str, Field(pattern=r"^[a-z]{2,3}$")]
_Duration = Annotated[int, Field(ge=5, le=480)]


# ── el modelo (contracts/client-spec.schema.json) ──────────────────────────────


class Shift(_Strict):
    """``HH:MM`` en la hora del negocio; un cierre igual o anterior a la
    apertura termina al día siguiente, y de 00:00 a 24:00 es abierto 24 horas."""

    open: str = Field(pattern=_HHMM)
    close: str = Field(pattern=_HHMM_CLOSE)


DayShifts = Annotated[list[Shift], Field(max_length=MAX_SHIFTS_PER_DAY)]


class Days(_Strict):
    mon: DayShifts | SkipJsonSchema[None] = None
    tue: DayShifts | SkipJsonSchema[None] = None
    wed: DayShifts | SkipJsonSchema[None] = None
    thu: DayShifts | SkipJsonSchema[None] = None
    fri: DayShifts | SkipJsonSchema[None] = None
    sat: DayShifts | SkipJsonSchema[None] = None
    sun: DayShifts | SkipJsonSchema[None] = None


class WeekSchedule(_Strict):
    layout: Literal["blocks", "daily"]
    days: Days
    label: str | SkipJsonSchema[None] = Field(default=None, json_schema_extra=_RO)


class Business(_Strict):
    name: str = Field(min_length=1, max_length=60)
    niche: str = Field(min_length=2, max_length=80)
    info: _Text2000 | SkipJsonSchema[None] = None
    website: _Uri300 | None = None
    country: str = Field(pattern=r"^[A-Z]{2}$")
    timezone: str = Field(max_length=64)
    price_currency: str = Field(pattern=r"^[A-Z]{3}$")
    wallet_currency: Literal["EUR", "USD"]
    eu_only: bool | SkipJsonSchema[None] = None
    sovereign: bool | SkipJsonSchema[None] = Field(default=None, json_schema_extra=_RO)


class Location(_Strict):
    id: _Uuid | SkipJsonSchema[None] = None
    name: str = Field(min_length=1, max_length=80)
    address: _Text300 | SkipJsonSchema[None] = None
    phone_e164: _Phone | SkipJsonSchema[None] = None
    hours: WeekSchedule | SkipJsonSchema[None] = None
    archived: bool | SkipJsonSchema[None] = Field(default=None, json_schema_extra=_RO)


class SpecialDate(_Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: _Uuid | SkipJsonSchema[None] = None
    name: _Text80 | SkipJsonSchema[None] = None
    location_id: _Uuid | None = None
    from_: date = Field(alias="from")
    to: date
    closed: bool
    shifts: DayShifts | SkipJsonSchema[None] = None


class PriceNone(_Strict):
    kind: Literal["none", "free"]


class PriceAmount(_Strict):
    kind: Literal["amount"]
    amount_minor: int = Field(ge=0)


def _service_if_then(schema: dict[str, Any]) -> None:
    schema["if"] = {"properties": {"bookable": {"const": True}}}
    schema["then"] = {"required": ["duration_min"]}


class Service(_Strict):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_service_if_then)

    id: _Uuid | SkipJsonSchema[None] = None
    name: str = Field(min_length=1, max_length=120)
    description: _Text1000 | SkipJsonSchema[None] = None
    bookable: bool
    duration_min: _Duration | SkipJsonSchema[None] = None
    price: PriceNone | PriceAmount | SkipJsonSchema[None] = None
    #: Quién lo hace en Reservas: «all» o la lista de personas.
    staff: Literal["all"] | list[_Uuid] | SkipJsonSchema[None] = None
    archived: bool | SkipJsonSchema[None] = Field(default=None, json_schema_extra=_RO)

    @model_validator(mode="after")
    def _bookable_needs_duration(self) -> Service:
        if self.bookable and self.duration_min is None:
            raise ValueError("a bookable service needs duration_min")
        return self


class Policies(_Strict):
    cancellation: _Text1000 | SkipJsonSchema[None] = None
    payments: _Text1000 | SkipJsonSchema[None] = None
    deposit: _Text1000 | SkipJsonSchema[None] = None
    no_show: _Text1000 | SkipJsonSchema[None] = None


class Faq(_Strict):
    id: _Uuid | SkipJsonSchema[None] = None
    q: str = Field(min_length=1, max_length=300)
    a: str = Field(min_length=1, max_length=2000)
    suggested: bool | SkipJsonSchema[None] = None


Network = Literal["web", "instagram", "facebook", "tiktok", "linkedin", "youtube", "x", "threads"]


def _link_any_of(schema: dict[str, Any]) -> None:
    schema["anyOf"] = [{"required": ["url"]}, {"required": ["handle"]}]


class Link(_Strict):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_link_any_of)

    network: Network
    url: _Uri300 | SkipJsonSchema[None] = None
    handle: _Handle | SkipJsonSchema[None] = None

    @model_validator(mode="after")
    def _url_or_handle(self) -> Link:
        if self.url is None and self.handle is None:
            raise ValueError("a link needs its url or its handle")
        return self


class Document(_Strict):
    id: _Uuid | SkipJsonSchema[None] = None
    kind: Literal["file", "web"] | SkipJsonSchema[None] = None
    title: str | SkipJsonSchema[None] = None
    layer: Literal["business", "agent"] | SkipJsonSchema[None] = None
    agent_id: _Uuid | None = None
    status: Literal["reading", "read", "failed"] | SkipJsonSchema[None] = None
    failure: Literal["unreachable", "blocked", "no_text", "too_large"] | None = None


Source = Literal[
    "person", "web", "document", "social", "migrated", "builder", "inbox_correction", "import"
]
Origin = Literal["console", "lite_web", "app", "admin", "api", "system"]


class ProvenanceEntry(_Strict):
    source: Source
    by: dict[str, Any] | None = None
    origin: Origin | SkipJsonSchema[None] = None
    at: str = Field(json_schema_extra={"format": "date-time"})
    source_url: _Uri | SkipJsonSchema[None] = None
    translated_from: _Language | SkipJsonSchema[None] = None
    review: Literal["pending", "confirmed"] | SkipJsonSchema[None] = None


class ClientSpec(_Strict):
    """ClientSpec v1 (``client-spec.schema.json``)."""

    schema_version: Literal["1"]
    business: Business
    locations: Annotated[list[Location], Field(max_length=50)] | SkipJsonSchema[None] = None
    hours: WeekSchedule | SkipJsonSchema[None] = None
    special_dates: Annotated[list[SpecialDate], Field(max_length=200)] | SkipJsonSchema[None] = None
    services: Annotated[list[Service], Field(max_length=500)] | SkipJsonSchema[None] = None
    policies: Policies | SkipJsonSchema[None] = None
    faqs: Annotated[list[Faq], Field(max_length=200)] | SkipJsonSchema[None] = None
    links: Annotated[list[Link], Field(max_length=20)] | SkipJsonSchema[None] = None
    documents: list[Document] | SkipJsonSchema[None] = Field(default=None, json_schema_extra=_RO)
    provenance: dict[str, ProvenanceEntry] | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=_RO
    )


class PatchOp(_Strict):
    op: Literal["add", "replace", "archive"]
    path: str = Field(
        pattern=r"^/(business|locations|hours|special_dates|services|policies|faqs|links)(/.*)?$"
    )
    value: Any = None
    provenance: ProvenanceEntry
    section_decision: Literal["accepted", "edited", "discarded"] | None = None


class Patch(_Strict):
    base_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    ops: list[PatchOp] = Field(min_length=1, max_length=500)


# ── la vista: las tablas como documento ────────────────────────────────────────


def minutes_to_hhmm(minutes: int, *, closing: bool = False) -> str:
    """Minutos desde la medianoche del día que abre → ``HH:MM``. Un cierre a
    las 24:00 justas se escribe ``24:00``; uno que pasa de medianoche, con la
    hora del día siguiente (el ClientSpec lo lee como nocturno)."""
    if closing and minutes == MINUTES_PER_DAY:
        return "24:00"
    m = minutes % MINUTES_PER_DAY
    return f"{m // 60:02d}:{m % 60:02d}"


def hhmm_to_minutes(open_: str, close: str) -> tuple[int, int]:
    """El inverso de :func:`minutes_to_hhmm` para un turno: ``(open_min, close_min)``."""

    def parse(v: str) -> int:
        h, m = v.split(":")
        return int(h) * 60 + int(m)

    o = parse(open_)
    c = MINUTES_PER_DAY if close == "24:00" else parse(close)
    if c <= o:
        c += MINUTES_PER_DAY
    return o, c


def _shift(open_min: int, close_min: int) -> dict[str, str]:
    return {"open": minutes_to_hhmm(open_min), "close": minutes_to_hhmm(close_min, closing=True)}


async def _schedule_view(
    session: AsyncSession, tenant_id: uuid.UUID, location_id: uuid.UUID | None
) -> dict[str, Any] | None:
    cond = (
        BusinessSchedule.location_id.is_(None)
        if location_id is None
        else BusinessSchedule.location_id == location_id
    )
    schedule = await session.scalar(
        sa.select(BusinessSchedule).where(BusinessSchedule.tenant_id == tenant_id, cond)
    )
    if schedule is None:
        return None
    shifts = (
        await session.scalars(
            sa.select(BusinessShift)
            .where(BusinessShift.tenant_id == tenant_id, BusinessShift.schedule_id == schedule.id)
            .order_by(BusinessShift.weekday, BusinessShift.open_min)
        )
    ).all()
    days: dict[str, list[dict[str, str]]] = {d: [] for d in WEEKDAYS}
    for s in shifts:
        days[WEEKDAYS[s.weekday]].append(_shift(s.open_min, s.close_min))
    out: dict[str, Any] = {"layout": schedule.layout, "days": days}
    label = await _hours_label(session, tenant_id) if location_id is None else None
    if label:
        out["label"] = label
    return out


async def _hours_label(session: AsyncSession, tenant_id: uuid.UUID) -> str | None:
    """«Así lo dirá el agente»: la proyección que escribe el servicio de horario."""
    if not hasattr(Tenant, "business_hours_label"):
        return None
    value = await session.scalar(
        sa.select(Tenant.business_hours_label).where(Tenant.id == tenant_id)
    )
    return str(value) if value else None


async def _business_view(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, Any] | None:
    from nexus_api.services.business.profile import DEFAULT_WALLET_CURRENCY

    profile = await session.get(BusinessProfile, tenant_id)
    tenant = await session.get(Tenant, tenant_id)
    if profile is None or tenant is None:
        return None
    out: dict[str, Any] = {
        "name": tenant.name,
        "niche": profile.niche,
        "website": profile.website,
        "country": profile.country,
        "timezone": profile.timezone,
        "price_currency": profile.price_currency,
        # Hasta la ola 7 la bolsa de todos los clientes va en US$ (``partner_allocations``).
        "wallet_currency": DEFAULT_WALLET_CURRENCY,
        "eu_only": profile.eu_only,
        "sovereign": profile.sovereign,
    }
    if profile.info:
        out["info"] = profile.info
    return out


async def _locations_view(session: AsyncSession, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(
            sa.select(BusinessLocation)
            .where(BusinessLocation.tenant_id == tenant_id)
            .order_by(BusinessLocation.position, BusinessLocation.created_at)
        )
    ).all()
    out: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {"id": str(row.id), "name": row.name}
        if row.address:
            item["address"] = row.address
        if row.phone_e164:
            item["phone_e164"] = row.phone_e164
        hours = await _schedule_view(session, tenant_id, row.id)
        if hours is not None:
            item["hours"] = hours
        if row.archived_at is not None:
            item["archived"] = True
        out.append(item)
    return out


async def _special_dates_view(session: AsyncSession, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(
            sa.select(BusinessSpecialDate)
            .where(
                BusinessSpecialDate.tenant_id == tenant_id,
                BusinessSpecialDate.archived_at.is_(None),
            )
            .order_by(BusinessSpecialDate.date_from, BusinessSpecialDate.created_at)
        )
    ).all()
    out: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {
            "id": str(row.id),
            "location_id": str(row.location_id) if row.location_id else None,
            "from": row.date_from.isoformat(),
            "to": row.date_to.isoformat(),
            "closed": row.closed,
        }
        if row.name:
            item["name"] = row.name
        if not row.closed:
            shifts = (
                await session.scalars(
                    sa.select(BusinessSpecialShift)
                    .where(
                        BusinessSpecialShift.tenant_id == tenant_id,
                        BusinessSpecialShift.special_date_id == row.id,
                    )
                    .order_by(BusinessSpecialShift.open_min)
                )
            ).all()
            item["shifts"] = [_shift(s.open_min, s.close_min) for s in shifts]
        out.append(item)
    return out


async def _services_view(session: AsyncSession, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    from nexus_api.db.models import ReservationServiceStaff

    rows = (
        await session.scalars(
            sa.select(ReservationService)
            .where(ReservationService.tenant_id == tenant_id)
            .order_by(ReservationService.position, ReservationService.created_at)
        )
    ).all()
    staff_rows = (
        await session.execute(
            sa.select(ReservationServiceStaff.service_id, ReservationServiceStaff.staff_id).where(
                ReservationServiceStaff.tenant_id == tenant_id
            )
        )
    ).all()
    staff: dict[uuid.UUID, list[str]] = {}
    for service_id, staff_id in staff_rows:
        staff.setdefault(service_id, []).append(str(staff_id))
    out: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {"id": str(row.id), "name": row.name, "bookable": row.bookable}
        if row.description:
            item["description"] = row.description
        if row.duration_minutes is not None:
            item["duration_min"] = row.duration_minutes
        if row.price_kind == "amount" and row.price_minor is not None:
            item["price"] = {"kind": "amount", "amount_minor": int(row.price_minor)}
        else:
            item["price"] = {
                "kind": row.price_kind if row.price_kind in ("none", "free") else "none"
            }
        item["staff"] = "all" if row.all_staff else sorted(staff.get(row.id, []))
        if row.archived_at is not None:
            item["archived"] = True
        out.append(item)
    return out


async def _policies_view(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, str]:
    profile = await session.get(BusinessProfile, tenant_id)
    raw = dict(profile.policies or {}) if profile is not None else {}
    return {k: str(v) for k, v in raw.items() if k in Policies.model_fields and v}


async def _faqs_view(session: AsyncSession, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(
            sa.select(BusinessFaq)
            .where(BusinessFaq.tenant_id == tenant_id, BusinessFaq.archived_at.is_(None))
            .order_by(BusinessFaq.position, BusinessFaq.created_at)
        )
    ).all()
    out: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {"id": str(row.id), "q": row.q, "a": row.a}
        if row.suggested:
            item["suggested"] = True
        out.append(item)
    return out


async def links_view(session: AsyncSession, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    """La web y las redes, con su id (el puntero ``/links/{id}``)."""
    rows = (
        await session.scalars(
            sa.select(BusinessLink)
            .where(BusinessLink.tenant_id == tenant_id)
            .order_by(BusinessLink.created_at, BusinessLink.id)
        )
    ).all()
    out: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {"id": str(row.id), "network": row.network}
        if row.url:
            item["url"] = row.url
        if row.handle:
            item["handle"] = row.handle
        out.append(item)
    return out


#: El estado de una fuente en el ClientSpec, desde el de ``knowledge_documents``.
_DOC_STATUS: Final[dict[str, str]] = {"pending": "reading", "indexed": "read", "failed": "failed"}
#: Y su motivo, desde el código del indexador (``KnowledgeErrorCode``).
_DOC_FAILURE: Final[dict[str, str]] = {
    "fetch_failed": "unreachable",
    "unsupported_type": "no_text",
    "empty": "no_text",
    "too_large": "too_large",
}


def document_status(status: str) -> str:
    return _DOC_STATUS.get(status, "failed")


def document_failure(error_code: str | None) -> str | None:
    return _DOC_FAILURE.get(error_code or "", "unreachable") if error_code else None


async def _documents_view(session: AsyncSession, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(
            sa.select(KnowledgeDocument)
            .where(KnowledgeDocument.tenant_id == tenant_id)
            .order_by(KnowledgeDocument.created_at, KnowledgeDocument.id)
        )
    ).all()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "id": str(row.id),
                "kind": "file" if row.kind == "file" else "web",
                "title": row.title,
                # Hasta la ola 5 todas las fuentes son de la capa del negocio.
                "layer": "business",
                "agent_id": None,
                "status": document_status(row.status),
                "failure": document_failure(row.error_code) if row.status == "failed" else None,
            }
        )
    return out


async def section_view(session: AsyncSession, section: str) -> dict[str, Any]:
    """La sección del cliente del contexto como fragmento del ClientSpec:
    ``{<clave>: <valor>}``. Es lo que guardan ``before``/``after`` del historial."""
    tenant_id = require_current_tenant()
    key = SECTION_KEYS[section]
    value: Any
    if section == "basics":
        value = await _business_view(session, tenant_id)
    elif section == "locations":
        value = await _locations_view(session, tenant_id)
    elif section == "hours":
        value = await _schedule_view(session, tenant_id, None)
    elif section == "special_dates":
        value = await _special_dates_view(session, tenant_id)
    elif section == "services":
        value = await _services_view(session, tenant_id)
    elif section == "policies":
        value = await _policies_view(session, tenant_id)
    elif section == "faqs":
        value = await _faqs_view(session, tenant_id)
    elif section == "links":
        value = await links_view(session, tenant_id)
    elif section == "sources":
        value = await _documents_view(session, tenant_id)
    else:  # pragma: no cover - SECTION_KEYS covers SECTIONS
        raise ValueError(f"unknown section: {section!r}")
    return {key: value}


async def provenance_view(session: AsyncSession) -> dict[str, dict[str, Any]]:
    """La procedencia vigente de cada dato, por su puntero, sin nombres."""
    rows = (
        await session.scalars(
            sa.select(BusinessFieldProvenance)
            .where(BusinessFieldProvenance.tenant_id == require_current_tenant())
            .order_by(BusinessFieldProvenance.pointer)
        )
    ).all()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry: dict[str, Any] = {
            "source": row.source,
            "by": {"kind": row.actor_kind, "id": row.actor_id} if row.actor_id else None,
            "origin": row.origin,
            "at": row.at.isoformat(),
            "review": row.review,
        }
        if row.source_url:
            entry["source_url"] = row.source_url
        if row.translated_from:
            entry["translated_from"] = row.translated_from
        out[row.pointer] = entry
    return out


async def export_document(session: AsyncSession, *, provenance: bool = True) -> dict[str, Any]:
    """El ClientSpec del cliente del contexto, de sus tablas. ``LookupError``
    si el cliente aún no tiene ficha (un cliente de antes de la 047)."""
    tenant_id = require_current_tenant()
    business = await _business_view(session, tenant_id)
    if business is None:
        raise LookupError("this client has no business profile")
    doc: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "business": business}
    for section in ("locations", "hours", "special_dates", "services", "policies", "faqs"):
        fragment = await section_view(session, section)
        value = fragment[SECTION_KEYS[section]]
        if value is not None:
            doc[SECTION_KEYS[section]] = value
    doc["links"] = [
        {k: v for k, v in item.items() if k != "id"}
        for item in await links_view(session, tenant_id)
    ]
    doc["documents"] = await _documents_view(session, tenant_id)
    if provenance:
        doc["provenance"] = await provenance_view(session)
    return doc


def _canonical(doc: Mapping[str, Any]) -> bytes:
    return json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def state_hash(doc: Mapping[str, Any]) -> str:
    """El ``state_hash`` de un documento: lo escribible, canónico. La
    procedencia y las fuentes no cuentan (no se importan)."""
    writable = {k: doc[k] for k in WRITABLE_KEYS if k in doc}
    return hashlib.sha256(_canonical(writable)).hexdigest()


# ── el validador sin modelo ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Problem:
    """Un problema del documento: dónde (puntero) y qué (código cerrado)."""

    pointer: str
    code: str


def _pydantic_problems(exc: ValidationError) -> list[Problem]:
    out: list[Problem] = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if not str(p).startswith("function-")]
        loc = ["from" if p == "from_" else p for p in loc]
        out.append(Problem(pointer="/" + "/".join(loc) if loc else "", code=str(err["type"])))
    return out


def _check_week(problems: list[Problem], base: str, week: WeekSchedule | None) -> None:
    if week is None:
        return
    for day in WEEKDAYS:
        shifts = getattr(week.days, day) or []
        spans = sorted(hhmm_to_minutes(s.open, s.close) for s in shifts)
        for (_o1, c1), (o2, _c2) in pairwise(spans):
            if o2 < c1:
                problems.append(Problem(f"{base}/days/{day}", "shifts_overlap"))
                break
        for o, c in spans:
            if c - o > MINUTES_PER_DAY:
                problems.append(Problem(f"{base}/days/{day}", "shift_too_long"))


def validate_document(doc: Any) -> tuple[ClientSpec | None, list[Problem]]:
    """El documento entero: Pydantic (``extra="forbid"``) y lo que el esquema no
    dice. ``(spec, [])`` si vale; ``(None | spec, problemas)`` si no."""
    from nexus_api.services.business.profile import is_valid_timezone

    try:
        spec = ClientSpec.model_validate(doc)
    except ValidationError as exc:
        return None, _pydantic_problems(exc)
    problems: list[Problem] = []
    if not is_valid_timezone(spec.business.timezone):
        problems.append(Problem("/business/timezone", "invalid_timezone"))
    _check_week(problems, "/hours", spec.hours)
    seen: dict[str, set[str]] = {}
    for key, items in (
        ("locations", spec.locations or []),
        ("special_dates", spec.special_dates or []),
        ("services", spec.services or []),
        ("faqs", spec.faqs or []),
    ):
        ids = seen.setdefault(key, set())
        for i, item in enumerate(items):
            item_id = getattr(item, "id", None)
            if item_id is None:
                continue
            try:
                uuid.UUID(item_id)
            except ValueError:
                problems.append(Problem(f"/{key}/{i}/id", "invalid_id"))
                continue
            if item_id in ids:
                problems.append(Problem(f"/{key}/{i}/id", "duplicate_id"))
            ids.add(item_id)
    for i, loc in enumerate(spec.locations or []):
        _check_week(problems, f"/locations/{i}/hours", loc.hours)
    location_ids = seen.get("locations", set())
    for i, sd in enumerate(spec.special_dates or []):
        if sd.to < sd.from_:
            problems.append(Problem(f"/special_dates/{i}/to", "range_reversed"))
        if sd.closed and sd.shifts:
            problems.append(Problem(f"/special_dates/{i}/shifts", "closed_with_shifts"))
        if sd.location_id is not None and location_ids and sd.location_id not in location_ids:
            problems.append(Problem(f"/special_dates/{i}/location_id", "unknown_location"))
    for i, svc in enumerate(spec.services or []):
        if not svc.bookable and svc.duration_min is not None:
            problems.append(Problem(f"/services/{i}/duration_min", "duration_not_bookable"))
        if svc.duration_min is not None and svc.duration_min % 5:
            problems.append(Problem(f"/services/{i}/duration_min", "duration_step"))
    networks: set[tuple[str, str]] = set()
    for i, link in enumerate(spec.links or []):
        link_key = (str(link.network), (link.handle or link.url or "").lower().lstrip("@"))
        if link_key in networks:
            problems.append(Problem(f"/links/{i}", "duplicate_link"))
        networks.add(link_key)
    return spec, problems


#: Lo que se valida de una sola operación: la clave del ClientSpec → el modelo
#: de un elemento (listas) o de la sección entera.
_ITEM_MODELS: Final[dict[str, type[BaseModel]]] = {
    "locations": Location,
    "special_dates": SpecialDate,
    "services": Service,
    "faqs": Faq,
    "links": Link,
}
_WHOLE_MODELS: Final[dict[str, type[BaseModel]]] = {
    "business": Business,
    "hours": WeekSchedule,
    "policies": Policies,
}


def split_pointer(pointer: str) -> tuple[str, list[str]]:
    """``/services/{id}/price`` → ``("services", ["{id}", "price"])``."""
    parts = [p.replace("~1", "/").replace("~0", "~") for p in pointer.split("/")[1:]]
    if not parts or parts[0] not in SECTION_KEYS.values():
        raise ValueError(f"not a ClientSpec pointer: {pointer!r}")
    return parts[0], parts[1:]


def validate_value(pointer: str, value: Any) -> list[Problem]:
    """Una operación sobre ``pointer`` con ``value``, antes de proponerla y al
    aplicarla. Solo lo escribible; el valor, con el modelo de su sitio."""
    if pointer in READ_ONLY_POINTERS:
        return [Problem(pointer, "read_only")]
    try:
        key, rest = split_pointer(pointer)
    except ValueError:
        return [Problem(pointer, "invalid_pointer")]
    if key not in WRITABLE_KEYS:
        return [Problem(pointer, "read_only")]
    try:
        if key in _ITEM_MODELS and len(rest) == 1:
            _ITEM_MODELS[key].model_validate(value)
        elif key in _ITEM_MODELS and not rest:
            if not isinstance(value, list):
                return [Problem(pointer, "list_type")]
            for item in value:
                _ITEM_MODELS[key].model_validate(item)
        elif key in _WHOLE_MODELS and not rest:
            _WHOLE_MODELS[key].model_validate(value)
        elif key in _WHOLE_MODELS and len(rest) == 1:
            model = _WHOLE_MODELS[key]
            field = rest[0]
            if field not in model.model_fields or (key, field) == ("business", "sovereign"):
                return [Problem(pointer, "unknown_field")]
            # Un campo suelto: se valida dentro de un objeto mínimo de su modelo.
            model.model_validate({**_MINIMAL.get(key, {}), field: value})
        elif key in _ITEM_MODELS and len(rest) == 2:
            model = _ITEM_MODELS[key]
            if rest[1] not in model.model_fields:
                return [Problem(pointer, "unknown_field")]
        else:
            return [Problem(pointer, "invalid_pointer")]
    except ValidationError as exc:
        return [Problem(pointer + p.pointer, p.code) for p in _pydantic_problems(exc)]
    if key == "business" and rest == ["timezone"]:
        from nexus_api.services.business.profile import is_valid_timezone

        if not is_valid_timezone(str(value)):
            return [Problem(pointer, "invalid_timezone")]
    if key == "hours" and not rest:
        problems: list[Problem] = []
        _check_week(problems, "/hours", WeekSchedule.model_validate(value))
        return problems
    return []


#: Un objeto mínimo válido de cada sección entera, para validar un campo suelto.
_MINIMAL: Final[dict[str, dict[str, Any]]] = {
    "business": {
        "name": "x",
        "niche": "xx",
        "country": "ES",
        "timezone": "UTC",
        "price_currency": "EUR",
        "wallet_currency": "USD",
    },
    "hours": {"layout": "blocks", "days": {}},
    "policies": {},
}


# ── importar: un documento → las operaciones del parche ────────────────────────


def _clean(value: Any) -> Any:
    """Sin lo de solo lectura (``archived``, ``label``, ``sovereign``)."""
    if isinstance(value, dict):
        return {
            k: _clean(v)
            for k, v in value.items()
            if k not in ("archived", "label", "sovereign") and v is not None
        }
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def diff_ops(current: Mapping[str, Any], incoming: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Lo que el documento importado cambia del actual, como operaciones
    ``{op, path, value, current}``. Importar **no borra**: lo que falta en el
    documento se queda como está, y nadie lo archiva por omisión."""
    ops: list[dict[str, Any]] = []
    cur_business = dict(current.get("business") or {})
    for field, value in (incoming.get("business") or {}).items():
        if field in ("sovereign",) or value is None:
            continue
        if cur_business.get(field) != value:
            ops.append(
                {
                    "op": "replace",
                    "path": f"/business/{field}",
                    "value": value,
                    "current": cur_business.get(field),
                }
            )
    cur_pol = dict(current.get("policies") or {})
    for key, value in (incoming.get("policies") or {}).items():
        if value and cur_pol.get(key) != value:
            ops.append(
                {
                    "op": "replace",
                    "path": f"/policies/{key}",
                    "value": value,
                    "current": cur_pol.get(key),
                }
            )
    if incoming.get("hours") is not None:
        cur_h = _clean(current.get("hours")) if current.get("hours") else None
        new_h = _clean(incoming["hours"])
        if cur_h != new_h:
            ops.append({"op": "replace", "path": "/hours", "value": new_h, "current": cur_h})
    for key in ("locations", "special_dates", "services", "faqs"):
        cur_list = [_clean(item) for item in (current.get(key) or []) if isinstance(item, dict)]
        cur_items = {str(item["id"]): item for item in cur_list if item.get("id")}
        cur_plain = [{k: v for k, v in item.items() if k != "id"} for item in cur_list]
        for item in incoming.get(key) or []:
            new = _clean(item)
            item_id = str(item.get("id")) if item.get("id") else None
            if item_id is not None and item_id in cur_items:
                if cur_items[item_id] != new:
                    ops.append(
                        {
                            "op": "replace",
                            "path": f"/{key}/{item_id}",
                            "value": new,
                            "current": cur_items[item_id],
                        }
                    )
                continue
            new.pop("id", None)
            if new not in cur_plain:
                ops.append({"op": "add", "path": f"/{key}/-", "value": new, "current": None})
    cur_links = {
        (link.get("network"), (link.get("handle") or link.get("url") or "").lower().lstrip("@"))
        for link in (current.get("links") or [])
    }
    for link in incoming.get("links") or []:
        key = (
            link.get("network"),
            (link.get("handle") or link.get("url") or "").lower().lstrip("@"),
        )
        if key not in cur_links:
            cur_links.add(key)
            ops.append({"op": "add", "path": "/links/-", "value": _clean(link), "current": None})
    return ops


def problems_out(problems: Sequence[Problem]) -> list[dict[str, str]]:
    return [{"pointer": p.pointer, "code": p.code} for p in problems]


__all__ = [
    "KEY_SECTIONS",
    "SCHEMA_VERSION",
    "SECTION_KEYS",
    "WEEKDAYS",
    "WRITABLE_KEYS",
    "Business",
    "ClientSpec",
    "Document",
    "Faq",
    "Link",
    "Location",
    "Patch",
    "PatchOp",
    "Policies",
    "Problem",
    "ProvenanceEntry",
    "Service",
    "Shift",
    "SpecialDate",
    "WeekSchedule",
    "diff_ops",
    "document_failure",
    "document_status",
    "export_document",
    "hhmm_to_minutes",
    "links_view",
    "minutes_to_hhmm",
    "problems_out",
    "provenance_view",
    "section_view",
    "split_pointer",
    "state_hash",
    "validate_document",
    "validate_value",
]
