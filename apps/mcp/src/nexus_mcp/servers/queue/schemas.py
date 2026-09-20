from __future__ import annotations

import uuid

from pydantic import Field

from nexus_mcp.base import InputModel, OutputModel


class JoinQueueInput(InputModel):
    # El cliente lo resuelve el servidor desde el contexto del turno
    # (`nexus_mcp/_customer.py`): nadie mete ni saca a otra persona de la cola.
    service_name: str = Field(min_length=1, max_length=120)
    barber_id: uuid.UUID | None = Field(
        default=None,
        description="Optional preferred barber. Omit for any-barber walk-in.",
    )


class JoinQueueOutput(OutputModel):
    queue_entry_id: uuid.UUID
    position: int
    estimated_wait_minutes: int


class GetPositionInput(InputModel):
    pass


class GetPositionOutput(OutputModel):
    customer_id: uuid.UUID
    position: int | None = Field(
        description="1-based position. Null if the customer is not currently in the queue.",
    )
    estimated_wait_minutes: int | None


class GetEstimatedWaitInput(InputModel):
    barber_id: uuid.UUID | None = None


class GetEstimatedWaitOutput(OutputModel):
    queue_length: int
    average_service_minutes: int
    estimated_wait_minutes: int


class CheckInInput(InputModel):
    pass


class CheckInOutput(OutputModel):
    customer_id: uuid.UUID
    queue_entry_id: uuid.UUID
    status: str


class RemoveFromQueueInput(InputModel):
    reason: str | None = Field(default=None, max_length=200)


class RemoveFromQueueOutput(OutputModel):
    customer_id: uuid.UUID
    queue_entry_id: uuid.UUID | None
    status: str
