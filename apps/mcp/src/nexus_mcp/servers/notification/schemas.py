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
    # Block N: optional language override for templates approved in
    # multiple locales. Defaults to es (Auphere is LATAM).
    language: str = Field(default="es", min_length=2, max_length=10)


class SendTemplateOutput(OutputModel):
    message_id: uuid.UUID
    status: str


class SendTextInput(InputModel):
    conversation_id: uuid.UUID
    body: str = Field(min_length=1, max_length=4096)
    # Block N: optional wamid to quote. When set the recipient sees this
    # text as a reply attached to the cited message bubble. Useful for
    # booking confirmations that quote the original question.
    context_message_id: str | None = Field(default=None, max_length=160)


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


# ── Block N: media + reaction + location schemas ────────────────────────────


class SendImageInput(InputModel):
    conversation_id: uuid.UUID
    media_s3_key: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "S3 key (within the platform's media bucket) of an image previously "
            "uploaded via the operator's catalog or generated from a tool output. "
            "The outbound dispatcher resolves this to a presigned URL the Cloud "
            "API can fetch."
        ),
    )
    caption: str | None = Field(default=None, max_length=1024)
    context_message_id: str | None = Field(default=None, max_length=160)


class SendImageOutput(OutputModel):
    message_id: uuid.UUID
    status: str


class SendAudioInput(InputModel):
    conversation_id: uuid.UUID
    media_s3_key: str = Field(min_length=1, max_length=500)
    context_message_id: str | None = Field(default=None, max_length=160)


class SendAudioOutput(OutputModel):
    message_id: uuid.UUID
    status: str


class SendVideoInput(InputModel):
    conversation_id: uuid.UUID
    media_s3_key: str = Field(min_length=1, max_length=500)
    caption: str | None = Field(default=None, max_length=1024)
    context_message_id: str | None = Field(default=None, max_length=160)


class SendVideoOutput(OutputModel):
    message_id: uuid.UUID
    status: str


class SendDocumentInput(InputModel):
    conversation_id: uuid.UUID
    media_s3_key: str = Field(min_length=1, max_length=500)
    filename: str | None = Field(default=None, max_length=255)
    caption: str | None = Field(default=None, max_length=1024)
    context_message_id: str | None = Field(default=None, max_length=160)


class SendDocumentOutput(OutputModel):
    message_id: uuid.UUID
    status: str


class SendLocationInput(InputModel):
    conversation_id: uuid.UUID
    latitude: float
    longitude: float
    name: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    context_message_id: str | None = Field(default=None, max_length=160)


class SendLocationOutput(OutputModel):
    message_id: uuid.UUID
    status: str


class SendReactionInput(InputModel):
    conversation_id: uuid.UUID
    target_message_id: str = Field(
        min_length=1,
        max_length=160,
        description="wamid of the message to react to. Required.",
    )
    emoji: str = Field(
        default="",
        max_length=20,
        description="Single emoji. Empty string removes a previous reaction.",
    )


class SendReactionOutput(OutputModel):
    message_id: uuid.UUID
    status: str
