"""Modelos de ``/console/lite/reservas/*`` — spec 043, ``contracts/lite-api.md``.

Tipados a propósito: la app genera sus tipos del OpenAPI (spec 031, D14), así
que un campo que cambia aquí rompe su ``tsc``, no el teléfono de nadie.
"""

from __future__ import annotations

import uuid
from datetime import date as Date  # noqa: N812 - hay campos que se llaman «date»
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Mode = Literal["services", "capacity"]
Status = Literal["pending", "confirmed", "arrived", "done", "noshow", "cancelled"]
Action = Literal["confirm", "move", "cancel", "request_confirmation", "arrive", "noshow", "undo"]
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


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


class SettingsOut(BaseModel):
    mode: Mode
    capacity_kind: str | None
    timezone: str
    currency: str
    business_hours: dict[str, list[dict[str, str]]] | None
    business_hours_label: str | None
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


class BusinessHoursIn(_In):
    hours: dict[str, list[dict[str, str]]]


class BusinessHoursOut(BaseModel):
    business_hours: dict[str, list[dict[str, str]]] | None
    business_hours_label: str | None


# ── equipo y servicios ──────────────────────────────────────────────────────


class CalendarStatus(BaseModel):
    status: Literal["none", "connected"]
    calendar_name: str | None = None
    last_sync_at: datetime | None = None


class StaffOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str | None
    hours: dict[str, list[dict[str, str]]] | None
    effective_hours: dict[str, list[dict[str, str]]] | None
    position: int
    archived: bool
    calendar: CalendarStatus


class StaffListOut(BaseModel):
    items: list[StaffOut]


class StaffIn(_In):
    name: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=254)
    hours: dict[str, Any] | None = None


class StaffPatchIn(_In):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=254)
    hours: dict[str, Any] | None = None
    position: int | None = Field(default=None, ge=0, le=1000)


class MoneyOut(BaseModel):
    amount_minor: int
    currency: str


class ServiceOut(BaseModel):
    id: uuid.UUID
    name: str
    duration_minutes: int
    price: MoneyOut | None
    staff: Literal["all", "some"]
    staff_ids: list[uuid.UUID]
    position: int
    archived: bool


class ServiceListOut(BaseModel):
    items: list[ServiceOut]


class ServiceIn(_In):
    name: str = Field(min_length=1, max_length=120)
    duration_minutes: int = Field(ge=15, le=480, multiple_of=15)
    price_minor: int | None = Field(default=None, ge=0)
    staff_ids: list[uuid.UUID] | None = None


class ServicePatchIn(_In):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    duration_minutes: int | None = Field(default=None, ge=15, le=480, multiple_of=15)
    price_minor: int | None = Field(default=None, ge=0)
    clear_price: bool = False
    staff_ids: list[uuid.UUID] | None = None
    all_staff: bool | None = None
    position: int | None = Field(default=None, ge=0, le=1000)


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
    id: str
    name: str


class CalendarOut(BaseModel):
    provider: Literal["google"]
    connected: bool
    calendars: list[CalendarItemOut]


class StaffCalendarIn(_In):
    calendar_id: str | None = Field(default=None, max_length=255)
