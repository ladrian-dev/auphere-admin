from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from nexus_mcp.base import InputModel, OutputModel


class GetPreferencesInput(InputModel):
    customer_id: uuid.UUID = Field(
        description="UUID of the customer (in the local Nexus DB).",
    )


class GetPreferencesOutput(OutputModel):
    customer_id: uuid.UUID
    preferences: dict[str, Any]


class UpdatePreferencesInput(InputModel):
    customer_id: uuid.UUID
    preferences: dict[str, Any] = Field(
        description=(
            "Partial dict to merge into the customer's preferences. Keys are "
            "preserved; existing keys are overwritten by new values. Pass {} "
            "to reset (no-op for missing keys)."
        ),
    )


class UpdatePreferencesOutput(OutputModel):
    customer_id: uuid.UUID
    preferences: dict[str, Any]
    status: str


class GetHistoryInput(InputModel):
    customer_id: uuid.UUID
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Max number of past appointments to return (most recent first).",
    )


class HistoryAppointment(OutputModel):
    appointment_id: uuid.UUID
    starts_at: datetime
    service_name: str
    barber_id: uuid.UUID | None
    status: str
    price_cents: int
    currency: str


class GetHistoryOutput(OutputModel):
    customer_id: uuid.UUID
    appointments: list[HistoryAppointment]
