from __future__ import annotations

import uuid
from datetime import date as Date  # noqa: N812
from datetime import datetime
from typing import Literal

from pydantic import Field

from nexus_mcp.base import InputModel, OutputModel

# ── check_availability ───────────────────────────────────────────────────────


class CheckAvailabilityInput(InputModel):
    on_date: Date = Field(
        description="Date to check (ISO YYYY-MM-DD), interpreted in the tenant's timezone.",
    )
    service_name: str = Field(
        min_length=1,
        max_length=120,
        description="Service the customer wants — must match a service known to the tenant.",
    )
    barber_id: uuid.UUID | None = Field(
        default=None,
        description="Optional preferred barber. Omit to consider any barber.",
    )
    duration_min: int = Field(
        default=30,
        ge=5,
        le=480,
        description="Service duration in minutes. Default 30.",
    )


class AvailableSlot(OutputModel):
    starts_at: datetime
    ends_at: datetime
    barber_id: uuid.UUID | None


class CheckAvailabilityOutput(OutputModel):
    on_date: Date
    service_name: str
    slots: list[AvailableSlot]


# ── create_appointment ───────────────────────────────────────────────────────


class CreateAppointmentInput(InputModel):
    customer_id: uuid.UUID
    service_name: str = Field(min_length=1, max_length=120)
    starts_at: datetime
    duration_min: int = Field(ge=5, le=480, default=30)
    barber_id: uuid.UUID | None = None
    price_cents: int = Field(ge=0, default=0)
    currency: str = Field(default="CLP", min_length=3, max_length=3)
    idempotency_key: str = Field(
        min_length=1,
        max_length=120,
        description=(
            "Caller-supplied idempotency token. Two ``create_appointment`` calls "
            "with the same key for the same tenant return the SAME row, never "
            "two separate appointments. Required to avoid double-booking on "
            "webhook retries."
        ),
    )
    notes: str | None = Field(default=None, max_length=2000)


class AppointmentBrief(OutputModel):
    appointment_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    service_name: str
    barber_id: uuid.UUID | None
    status: str
    price_cents: int
    currency: str


class CreateAppointmentOutput(OutputModel):
    appointment: AppointmentBrief
    idempotent_replay: bool = Field(
        description="True if a prior call with the same idempotency_key already created this row.",
    )


# ── modify_appointment ───────────────────────────────────────────────────────


class ModifyAppointmentInput(InputModel):
    appointment_id: uuid.UUID
    new_starts_at: datetime | None = None
    new_duration_min: int | None = Field(default=None, ge=5, le=480)
    new_barber_id: uuid.UUID | None = None
    new_service_name: str | None = Field(default=None, min_length=1, max_length=120)


class ModifyAppointmentOutput(OutputModel):
    appointment: AppointmentBrief
    status: Literal["modified", "no_changes"]


# ── cancel_appointment ───────────────────────────────────────────────────────


class CancelAppointmentInput(InputModel):
    appointment_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=500)


class CancelAppointmentOutput(OutputModel):
    appointment_id: uuid.UUID
    status: Literal["cancelled"]
    fee_pct: int = Field(
        ge=0,
        le=100,
        description="Cancellation fee percentage applied per tenant policy.",
    )


# ── get_appointments ─────────────────────────────────────────────────────────


class GetAppointmentsInput(InputModel):
    customer_id: uuid.UUID | None = Field(
        default=None,
        description="If provided, restrict to this customer's appointments.",
    )
    from_date: Date | None = Field(
        default=None,
        description="Inclusive lower bound (date, tenant TZ).",
    )
    to_date: Date | None = Field(
        default=None,
        description="Inclusive upper bound (date, tenant TZ).",
    )
    only_upcoming: bool = Field(
        default=False,
        description="If true, ignore from_date and return only appointments at-or-after now().",
    )
    limit: int = Field(default=20, ge=1, le=100)


class GetAppointmentsOutput(OutputModel):
    appointments: list[AppointmentBrief]
