"""Pydantic mirrors of the Node MCP tool schemas.

Kept in sync manually with ``agendapro_public_mcp/src/flows/*.ts``.
The Node side validates the same shape via zod; this is the canonical
Python contract the booking facade and the async cron use.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field

from nexus_mcp.base import InputModel, OutputModel


# ── check_availability ─────────────────────────────────────────────────────


class CheckAvailabilityPublicInput(InputModel):
    public_url: str = Field(min_length=1, max_length=500)
    on_date: str = Field(
        min_length=10,
        max_length=10,
        description="ISO date YYYY-MM-DD. The Node side timezone-aware-stamps it.",
    )
    service_hint: str | None = Field(default=None, max_length=120)
    duration_hint_min: int | None = Field(default=None, ge=15, le=240)
    preferred_barber_name: str | None = Field(default=None, max_length=120)


class PublicSlot(OutputModel):
    starts_at_iso: str
    duration_min: int
    barber_name: str | None
    barber_slot_token: str = Field(
        min_length=1,
        max_length=500,
        description="Opaque token returned by the wizard; re-use verbatim "
        "in create_appointment so the slot lookup stays idempotent.",
    )


class CheckAvailabilityPublicOutput(OutputModel):
    slots: list[PublicSlot] = Field(default_factory=list)
    recaptcha_score: float | None = None
    screenshot_url: str | None = None


# ── create_appointment ─────────────────────────────────────────────────────


class PublicSlotInput(InputModel):
    starts_at_iso: str
    duration_min: int = Field(ge=15, le=240)
    barber_slot_token: str = Field(min_length=1, max_length=500)


class PublicCustomerInput(InputModel):
    name: str = Field(min_length=1, max_length=120)
    phone_e164: str = Field(min_length=8, max_length=40)
    email: EmailStr


class CreateAppointmentPublicInput(InputModel):
    public_url: str = Field(min_length=1, max_length=500)
    slot: PublicSlotInput
    customer: PublicCustomerInput
    service_hint: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=120)


class CreateAppointmentPublicOutput(OutputModel):
    external_ref: str | None
    confirmation_at_iso: str
    recaptcha_score: float | None = None
    screenshot_url: str | None = None
    status: Literal["confirmed", "ambiguous", "failed"]
    failure_reason: str | None = None

    @property
    def confirmation_at(self) -> datetime:
        return datetime.fromisoformat(self.confirmation_at_iso)
