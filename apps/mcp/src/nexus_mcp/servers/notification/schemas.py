from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from nexus_mcp.base import InputModel, OutputModel


class SendTemplateInput(InputModel):
    conversation_id: uuid.UUID
    template_name: str = Field(
        min_length=1,
        max_length=120,
        description="Meta-approved WhatsApp template name (e.g. 'reminder_24h').",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Template parameter map.",
    )


class SendTemplateOutput(OutputModel):
    message_id: uuid.UUID
    status: str


class SendTextInput(InputModel):
    conversation_id: uuid.UUID
    body: str = Field(min_length=1, max_length=4096)


class SendTextOutput(OutputModel):
    message_id: uuid.UUID
    status: str


class ScheduleReminderInput(InputModel):
    conversation_id: uuid.UUID
    appointment_id: uuid.UUID | None = None
    run_at: datetime = Field(
        description="When to fire the reminder. Tenant-TZ aware on the caller side; stored as UTC.",
    )
    template_name: str = Field(min_length=1, max_length=120)
    parameters: dict[str, Any] = Field(default_factory=dict)


class ScheduleReminderOutput(OutputModel):
    reminder_id: uuid.UUID
    run_at: datetime
    status: str


class CancelScheduledInput(InputModel):
    reminder_id: uuid.UUID


class CancelScheduledOutput(OutputModel):
    reminder_id: uuid.UUID
    status: str
