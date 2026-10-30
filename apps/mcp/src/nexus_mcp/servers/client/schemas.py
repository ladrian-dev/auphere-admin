from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from nexus_mcp.base import InputModel, OutputModel

# El cliente NO viaja como argumento en ninguna entrada de este servidor: lo
# resuelve el servidor desde el contexto del turno (`nexus_mcp/_customer.py`).
# Sigue apareciendo en las **salidas**, donde es un eco de la identidad ya
# resuelta y no algo que el modelo pueda elegir.


class GetPreferencesInput(InputModel):
    pass


class GetPreferencesOutput(OutputModel):
    customer_id: uuid.UUID
    preferences: dict[str, Any]


class UpdatePreferencesInput(InputModel):
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
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Max number of past appointments to return (most recent first).",
    )


class HistoryAppointment(OutputModel):
    #: The booking's id — a Reservas booking, or an appointment from before.
    appointment_id: uuid.UUID
    starts_at: datetime
    service_name: str
    barber_id: uuid.UUID | None
    status: str
    price_cents: int
    currency: str
    #: Spec 048: where it lives. ``reservas`` is the agenda the business sees;
    #: ``appointments`` holds the ones from before that were not passed over.
    source: Literal["reservas", "appointments"] = "appointments"
    #: Who does it, by name (Reservas only).
    staff_name: str | None = None


class GetHistoryOutput(OutputModel):
    customer_id: uuid.UUID
    appointments: list[HistoryAppointment]
