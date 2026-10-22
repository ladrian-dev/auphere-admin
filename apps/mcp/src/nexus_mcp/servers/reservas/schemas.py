"""Esquemas de ``reservas.*`` (spec 043, ``contracts/agent-tools.md``).

**Ninguno tiene un campo de cliente** (spec 014): la persona es la del turno.
Las fechas y horas son las del negocio (``date`` + ``HH:MM``).
"""

from __future__ import annotations

import uuid
from datetime import date as Date  # noqa: N812 - un campo se llama «date»
from datetime import datetime

from pydantic import Field

from nexus_mcp.base import InputModel, OutputModel

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class Money(OutputModel):
    amount_minor: int
    currency: str


class StaffRef(OutputModel):
    id: uuid.UUID
    name: str


class ServiceItem(OutputModel):
    id: uuid.UUID
    name: str
    duration_minutes: int
    price: Money | None = None
    staff: list[StaffRef]


class ServicesInput(InputModel):
    pass


class ServicesOutput(OutputModel):
    mode: str
    services: list[ServiceItem] = Field(default_factory=list)
    max_party: int | None = None


class FindSlotsInput(InputModel):
    date: Date = Field(description="Business-local day to search.")
    service_id: uuid.UUID | None = Field(default=None, description="Services mode: the service.")
    staff_id: uuid.UUID | None = Field(
        default=None, description="Services mode: a team member, or omit for anyone."
    )
    party_size: int | None = Field(default=None, ge=1, le=500, description="Capacity mode.")


class SlotOut(OutputModel):
    time: str
    staff: list[StaffRef] = Field(default_factory=list)
    left: int | None = None


class FindSlotsOutput(OutputModel):
    date: Date
    closed: bool
    why_closed: str | None = None
    slots: list[SlotOut] = Field(default_factory=list)
    first_fit: str | None = None


class BookingBrief(OutputModel):
    id: uuid.UUID
    status: str
    date: Date
    start: str
    end: str
    starts_at: datetime
    party_size: int
    service_name: str | None = None
    staff_name: str | None = None
    note: str | None = None


class CreateInput(InputModel):
    date: Date
    time: str = Field(pattern=HHMM)
    service_id: uuid.UUID | None = None
    staff_id: uuid.UUID | None = None
    any_staff: bool = False
    party_size: int = Field(default=1, ge=1, le=500)
    note: str | None = Field(default=None, max_length=500)
    join_waitlist: bool = Field(
        default=False, description="Services: also notify them if an earlier slot frees up."
    )
    idempotency_key: str = Field(
        min_length=1,
        max_length=120,
        description="Stable for this request: repeating it returns the same booking instead of a second one, e.g. 'reserva:{date}:{time}'.",
    )
    conversation_id: uuid.UUID | None = None


class CreateOutput(OutputModel):
    booking: BookingBrief | None = None
    idempotent_replay: bool = False
    refused: str | None = Field(
        default=None,
        description=(
            "slot_taken | too_large | too_soon | too_far | closed | hours_missing. "
            "too_large: escalate to a person with escalate.escalate_to_human."
        ),
    )
    first_fit: str | None = None


class ListMineInput(InputModel):
    only_upcoming: bool = True


class ListMineOutput(OutputModel):
    bookings: list[BookingBrief]


class RescheduleInput(InputModel):
    booking_id: uuid.UUID
    date: Date
    time: str = Field(pattern=HHMM)
    staff_id: uuid.UUID | None = None


class RescheduleOutput(OutputModel):
    booking: BookingBrief | None = None
    refused: str | None = None
    first_fit: str | None = None


class CancelInput(InputModel):
    booking_id: uuid.UUID


class CancelOutput(OutputModel):
    booking: BookingBrief
    offered_to_waitlist: bool


class ConfirmAttendanceInput(InputModel):
    attending: bool
    booking_id: uuid.UUID | None = None


class ConfirmAttendanceOutput(OutputModel):
    booking: BookingBrief


class JoinWaitlistInput(InputModel):
    date: Date | None = None
    time: str | None = Field(default=None, pattern=HHMM)
    party_size: int = Field(default=1, ge=1, le=500)
    service_id: uuid.UUID | None = None
    staff_id: uuid.UUID | None = None
    until: Date | None = None
    booking_id: uuid.UUID | None = None


class JoinWaitlistOutput(OutputModel):
    entry_id: uuid.UUID
    status: str


class AnswerOfferInput(InputModel):
    accept: bool
    conversation_id: uuid.UUID | None = None


class AnswerOfferOutput(OutputModel):
    result: str  # booked | late_taken | declined | no_offer
    booking: BookingBrief | None = None
