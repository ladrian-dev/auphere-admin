from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

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
