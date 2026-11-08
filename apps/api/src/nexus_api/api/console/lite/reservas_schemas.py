"""Modelos de ``/console/lite/reservas/*`` — spec 043, ``contracts/lite-api.md``.

Tipados a propósito: la app genera sus tipos del OpenAPI (spec 031, D14), así
que un campo que cambia aquí rompe su ``tsc``, no el teléfono de nadie.
"""

from __future__ import annotations

import uuid
from datetime import date as Date  # noqa: N812 - hay campos que se llaman «date»
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from nexus_api.api.console.schemas_business_sections import (
    HoursOut,
    PriceIn,
    PriceOut,
    ShiftIn,
)
from nexus_api.services.business import rules

Mode = Literal["services", "capacity"]
Status = Literal["pending", "confirmed", "arrived", "done", "noshow", "cancelled"]
Action = Literal["confirm", "move", "cancel", "request_confirmation", "arrive", "noshow", "undo"]
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
#: RFC 5321: una dirección cabe en 254 caracteres (spec 056, 11.3).
EMAIL_MAX = 254
Email = Annotated[EmailStr, StringConstraints(max_length=EMAIL_MAX)]

#: Spec 056 (5.2): lo que tiene código propio lo comprueba ``rules`` (``422
#: {code, field}``); el esquema solo lo publica en el OpenAPI, con sus valores.
CATEGORY_RULE: dict[str, Any] = {"maxLength": rules.CATEGORY_MAX}
DURATION_RULE: dict[str, Any] = {
    "minimum": rules.DURATION_MIN,
    "maximum": rules.DURATION_MAX,
    "multipleOf": rules.DURATION_STEP,
}


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── ajustes ─────────────────────────────────────────────────────────────────


class RangeOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str


class WaitlistSettings(BaseModel):
    enabled: bool
    lead_minutes: int


class AgentSettings(BaseModel):
    min_notice_minutes: int
    max_days_ahead: int


class ConfirmationSettings(BaseModel):
    enabled: bool
    when: Literal["24h", "same_day_12", "3h"]


class CapacitySettings(BaseModel):
    seats: int
    stay_minutes: int
    max_party: int
    walkin_hold: int
    schedule: dict[str, Any]


class LocationRef(BaseModel):
    id: uuid.UUID
    name: str


class LocationHoursOut(BaseModel):
    location: LocationRef
    has_own_hours: bool
    #: «Así lo dirá el agente» de su horario propio; ``None`` si usa el del negocio.
    label: str | None


class SettingsOut(BaseModel):
    mode: Mode
    capacity_kind: str | None
    timezone: str
    currency: str
    #: Spec 055: si ``currency`` se sabe de verdad; si no, el modal pide elegirla.
    currency_set: bool = True
    #: La proyección de antes (``{"monday": [{"from", "to"}]}``): la leen la app y
    #: los días cerrados de la agenda.
    business_hours: dict[str, list[dict[str, str]]] | None
    business_hours_label: str | None
    #: Spec 056 (5.1): el horario de la ficha, el que se edita (revisión, layout y
    #: días con ``overnight``).
    hours: HoursOut
    #: Las sedes y si tienen horario propio: se enseña, no se edita desde aquí.
    location_hours: list[LocationHoursOut]
    hours_missing: bool
    slot_step_minutes: int
    waitlist: WaitlistSettings
    agent: AgentSettings
    confirmation: ConfirmationSettings
    reminder_enabled: bool
    release_unconfirmed: bool
    capacity: CapacitySettings | None
    version: int


class SettingsPatchIn(_In):
    waitlist: dict[str, Any] | None = None
    agent: dict[str, Any] | None = None
    confirmation: dict[str, Any] | None = None
    reminder_enabled: bool | None = None
    release_unconfirmed: bool | None = None
    slot_step_minutes: int | None = None
    capacity: dict[str, Any] | None = None


class BusinessHoursPatchIn(_In):
    """Spec 056 (5.3): solo los días tocados, con la revisión de la sección que se
    leyó. Los que no llegan se quedan como estaban."""

    revision: int = Field(ge=0)
    days: dict[str, list[ShiftIn]] = Field(max_length=7)


# ── equipo y servicios ──────────────────────────────────────────────────────


class CalendarStatus(BaseModel):
    """El calendario de un profesional. ``pending``: se pidió la autorización y no ha
    terminado. ``needs_calendar``: conectado y sin calendario que usar. ``needs_reauth``:
    hay que volver a conectar. ``account`` es la cuenta que quedó conectada. ``last_error``
    es un código nuestro (``connection``, ``auth``, ``calendar_gone``, ``read``, ``write``,
    ``calendar_in_use``, ``no_calendar``, ``new_account_refused``), nunca el texto del proveedor."""

    status: Literal["none", "pending", "connected", "needs_calendar", "needs_reauth", "error"]
    calendar_name: str | None = None
    account: str | None = None
    last_sync_at: datetime | None = None
    #: Hay horas suyas que bloquea el Google del negocio, hasta que conecte el suyo.
    business_busy: bool = False
    last_error: str | None = None


class StaffOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str | None
    hours: dict[str, list[dict[str, str]]] | None
    effective_hours: dict[str, list[dict[str, str]]] | None
    position: int
    archived: bool
    calendar: CalendarStatus
    #: ``no_hours``: tiene horario propio y no trabaja ningún día (R14.3).
    warnings: list[Literal["no_hours"]] = []


class StaffListOut(BaseModel):
    items: list[StaffOut]


class StaffIn(_In):
    name: str = Field(min_length=1, max_length=120)
    email: Email | None = None
    hours: dict[str, Any] | None = None


class StaffPatchIn(_In):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: Email | None = None
    hours: dict[str, Any] | None = None
    position: int | None = Field(default=None, ge=0, le=1000)


class MoneyOut(BaseModel):
    amount_minor: int
    currency: str


class ServiceOut(BaseModel):
    id: uuid.UUID
    name: str
    #: Spec 055: lo que lo agrupa; ``None`` es sin categoría.
    category: str | None = None
    duration_minutes: int
    #: Spec 056 (5.2): el de la ficha, ``{kind}`` o ``{kind: "amount", amount_minor}``.
    #: «Gratis» es ``free``, no un importe nulo.
    price: PriceOut
    #: La moneda del importe (ISO 4217, unidades menores).
    currency: str
    staff: Literal["all", "some"]
    staff_ids: list[uuid.UUID]
    position: int
    archived: bool
    #: ``no_staff``: no lo hace nadie en activo. ``does_not_fit``: no cabe en el horario de
    #: quienes lo hacen (R14.1 y R14.2).
    warnings: list[Literal["no_staff", "does_not_fit"]] = []


class ServiceListOut(BaseModel):
    items: list[ServiceOut]


class ServiceIn(_In):
    name: str = Field(min_length=rules.NAME_MIN, max_length=rules.NAME_MAX)
    duration_minutes: int = Field(json_schema_extra=DURATION_RULE)
    price: PriceIn = Field(default_factory=lambda: PriceIn(kind="none"))
    staff_ids: list[uuid.UUID] | None = None
    #: Spec 055: solo se usa si el negocio aún no tiene moneda de precios.
    price_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    category: str | None = Field(default=None, json_schema_extra=CATEGORY_RULE)


class ServicePatchIn(_In):
    """Lo que no llega no cambia. ``name`` solo se acepta si es el que ya tiene:
    desde Reservas no se renombra (``422 rename_not_allowed``, spec 056 D5)."""

    name: str | None = Field(default=None, min_length=rules.NAME_MIN, max_length=rules.NAME_MAX)
    duration_minutes: int | None = Field(default=None, json_schema_extra=DURATION_RULE)
    price: PriceIn | None = None
    staff_ids: list[uuid.UUID] | None = None
    all_staff: bool | None = None
    position: int | None = Field(default=None, ge=0, le=1000)
    price_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    category: str | None = Field(default=None, json_schema_extra=CATEGORY_RULE)


# ── reservas ────────────────────────────────────────────────────────────────


class LocalSpan(BaseModel):
    date: Date
    start: str
    end: str


class RefOut(BaseModel):
    id: uuid.UUID
    name: str


class BookingServiceOut(BaseModel):
    id: uuid.UUID
    name: str
    duration_minutes: int


class ContactOut(BaseModel):
    name: str | None
    phone: str | None
    conversation_id: uuid.UUID | None


class CreatedByOut(BaseModel):
    kind: Literal["agent", "person", "system", "customer"]
    name: str | None


class CancelledOut(BaseModel):
    at: datetime | None
    by: Literal["customer", "business", "system"] | None
    cause: str | None


class ClashLocal(BaseModel):
    start: str
    end: str


class ClashOut(BaseModel):
    source: Literal["google"]
    local: ClashLocal


class BookingOut(BaseModel):
    id: uuid.UUID
    mode: Mode
    status: Status
    starts_at: datetime
    ends_at: datetime
    local: LocalSpan
    party_size: int
    staff: RefOut | None
    service: BookingServiceOut | None
    price: MoneyOut | None
    contact: ContactOut
    origin: Literal["agent", "person", "waitlist", "walkin"]
    channel: Literal["whatsapp", "phone", "in_person"]
    created_by: CreatedByOut
    created_at: datetime
    note: str | None
    arrived_at: datetime | None
    cancelled: CancelledOut | None
    wants_earlier: bool
    any_staff: bool
    late_minutes: int | None
    clash: ClashOut | None
    allowed: list[Action]
    version: int


class EventActor(BaseModel):
    kind: Literal["agent", "person", "system", "customer"]
    name: str | None


class EventOut(BaseModel):
    kind: str
    at: datetime
    actor: EventActor
    data: dict[str, Any]


class BookingDetailOut(BookingOut):
    events: list[EventOut]


class BookingListOut(BaseModel):
    items: list[BookingOut]
    closed_days: list[Date]
    truncated: bool


class ContactIn(_In):
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=32)


class NewBookingIn(_In):
    date: Date
    time: str = Field(pattern=HHMM)
    staff_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    party_size: int = Field(default=1, ge=1, le=1000)
    contact: ContactIn
    note: str | None = Field(default=None, max_length=500)
    join_waitlist: bool = False
    notify: bool = True


class MoveIn(_In):
    """Lo que no cambia, se omite (la fecha y la hora, también)."""

    date: Date | None = None
    time: str | None = Field(default=None, pattern=HHMM)
    staff_id: uuid.UUID | None = None
    party_size: int | None = Field(default=None, ge=1, le=1000)
    note: str | None = Field(default=None, max_length=500)
    notify: bool = True


class CancelIn(_In):
    notify: bool = True
    offer_slot: bool = False


class OfferRefOut(BaseModel):
    id: uuid.UUID
    candidates: int


class CancelledBookingOut(BookingOut):
    offer: OfferRefOut | None


class CancelPreviewOut(BaseModel):
    can_offer: bool
    candidates: int
    why_not: Literal["waitlist_off", "too_soon", "nobody_fits", "not_services"] | None


class WalkinIn(_In):
    party_size: int = Field(ge=1, le=1000)
    name: str | None = Field(default=None, max_length=120)


# ── huecos, ocupación, resumen ──────────────────────────────────────────────


class SlotOut(BaseModel):
    time: str
    staff_ids: list[uuid.UUID] | None = None
    shift: str | None = None
    fits: bool | None = None
    left: int | None = None
    why: str | None = None


class SlotsOut(BaseModel):
    date: Date
    closed: bool
    slots: list[SlotOut]
    first_fit: str | None = None


class BlockRefOut(BaseModel):
    id: uuid.UUID
    label: str


class OccupancySlotOut(BaseModel):
    time: str
    shift: str | None
    present: int
    arriving: int
    arrived: int
    pending: int
    blocked: BlockRefOut | None
    past: bool


class OccupancyDayOut(BaseModel):
    date: Date
    closed: bool
    slots: list[OccupancySlotOut]


class OccupancyOut(BaseModel):
    seats: int
    walkin_hold: int
    stay_minutes: int
    days: list[OccupancyDayOut]


class SummaryTodayOut(BaseModel):
    date: Date
    bookings: int
    confirmed: int
    pending: int
    next_at: datetime | None
    people: int | None
    inside_now: int | None
    arriving_next_hour: int | None
    #: Aforo: el aforo del negocio («dentro ahora: N de 64»). Servicios: ``None``.
    seats: int | None


class SummaryWeekOut(BaseModel):
    occupancy_pct: float | None
    agent_share_pct: float | None


class SummaryMonthOut(BaseModel):
    noshow_pct: float | None
    recovered: int | None


class SummaryWaitlistOut(BaseModel):
    waiting: int


class SummaryOut(BaseModel):
    mode: Mode
    today: SummaryTodayOut
    week: SummaryWeekOut | None
    month: SummaryMonthOut | None
    waitlist: SummaryWaitlistOut
    clashes: int
    upcoming: list[BookingOut]
    errors: list[str]


# ── bloqueos ────────────────────────────────────────────────────────────────


class BlockOut(BaseModel):
    id: uuid.UUID
    date: Date
    from_: str = Field(alias="from")
    until: str
    label: str
    created_by_name: str | None

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class BlockListOut(BaseModel):
    items: list[BlockOut]


class BlockIn(_In):
    date: Date
    from_: str = Field(alias="from", pattern=HHMM)
    until: str = Field(pattern=HHMM)
    label: str = Field(min_length=1, max_length=120)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BlockCreatedOut(BaseModel):
    block: BlockOut
    overlapping_bookings: int


# ── lista de espera y ofertas ───────────────────────────────────────────────


class DesiredOut(BaseModel):
    date: Date | None
    time: str | None
    until: Date | None


class JoinedOut(BaseModel):
    kind: Literal["agent", "person", "in_person"]
    name: str | None
    at: datetime


class EntryOfferOut(BaseModel):
    id: uuid.UUID
    deadline_at: datetime | None


class WaitlistEntryOut(BaseModel):
    id: uuid.UUID
    status: Literal["waiting", "offered", "accepted", "removed", "expired"]
    contact: ContactOut
    party_size: int
    desired: DesiredOut
    service: BookingServiceOut | None
    staff: RefOut | None
    booking_id: uuid.UUID | None
    booking_local: LocalSpan | None = None
    joined: JoinedOut
    fits_now: bool | None
    offer: EntryOfferOut | None


class WaitlistOut(BaseModel):
    enabled: bool
    items: list[WaitlistEntryOut]


class WaitlistIn(_In):
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    party_size: int = Field(default=1, ge=1, le=1000)
    date: Date | None = None
    time: str | None = Field(default=None, pattern=HHMM)
    in_person: bool = False
    service_id: uuid.UUID | None = None
    staff_id: uuid.UUID | None = None
    until: Date | None = None


class CandidateOut(BaseModel):
    position: int
    waitlist_id: uuid.UUID
    name: str | None
    status: str
    deadline_at: datetime | None
    answered_at: datetime | None


class OfferSlotOut(BaseModel):
    local: LocalSpan
    staff: RefOut | None
    service: RefOut | None
    seats: int | None


class OfferOut(BaseModel):
    id: uuid.UUID
    status: Literal["running", "filled", "empty", "stopped"]
    slot: OfferSlotOut
    cancelled_by_name: str | None
    window_minutes: int
    candidates: list[CandidateOut]
    filled_booking_id: uuid.UUID | None
    created_at: datetime


class OfferListOut(BaseModel):
    items: list[OfferOut]


# ── calendarios (P3) ────────────────────────────────────────────────────────


class CalendarItemOut(BaseModel):
    """Un calendario de la cuenta de ese profesional. ``used_by``: quién del negocio lo
    usa ya; un calendario, un profesional (R12.4)."""

    id: str
    name: str
    primary: bool = False
    used_by: str | None = None


class StaffCalendarsOut(BaseModel):
    calendars: list[CalendarItemOut]


class CalendarConnectIn(_In):
    """``share``: el enlace es para enviárselo al profesional, que no vuelve a la consola."""

    share: bool = False


class CalendarLinkOut(BaseModel):
    redirect_url: str


class StaffCalendarIn(_In):
    calendar_id: str | None = Field(default=None, max_length=255)
