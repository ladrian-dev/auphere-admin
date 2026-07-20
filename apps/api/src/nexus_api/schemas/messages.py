"""Schemas for the direct outbound message API (``/v1/messages``).

The caller is an automation platform (n8n, Zapier, a cron script), not a
browser. That shapes the contract: flat JSON, no nesting to build in a
visual node editor, and errors that say what to change rather than what
went wrong internally.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TemplateMessageIn(BaseModel):
    """One template message to one recipient."""

    to: str = Field(
        description=(
            "Recipient phone. Accepts +56912345678, 56912345678 or "
            "formatted variants — normalised to E.164 server-side."
        ),
        max_length=40,
    )
    template_name: str = Field(max_length=512)
    language: str = Field(default="es", max_length=16)
    # Named parameters only: {{nombre}}, not {{1}}. Templates using
    # positional placeholders are rejected at resolve time with an
    # explicit message — see services/broadcasts._resolve_template.
    variables: dict[str, str] = Field(default_factory=dict)
    idempotency_key: str | None = Field(
        default=None,
        max_length=80,
        description=(
            "Replay guard. Sending the same key twice returns the original "
            "message instead of delivering a second WhatsApp. Scoped to "
            "your tenant, so it only needs to be unique to you."
        ),
    )


class TemplateMessageAcceptedOut(BaseModel):
    """202 response — queued, not yet delivered.

    ``duplicate=True`` means the idempotency key matched an earlier send
    and nothing new was queued. It is deliberately not an error: a
    retrying caller wants to proceed, not to branch.
    """

    message_id: uuid.UUID
    status: str
    to: str
    duplicate: bool = False


class MessageStatusOut(BaseModel):
    """Delivery state, polled by the caller after accepting a send."""

    model_config = ConfigDict(from_attributes=True)

    message_id: uuid.UUID = Field(validation_alias="id")
    status: str
    created_at: datetime
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    failed_at: datetime | None = None
    # Meta's numeric error (131026 unreachable, 131047 outside the 24h
    # window, 132xxx template paused). Surfaced raw so the caller can
    # branch on it without us inventing a parallel taxonomy.
    failure_code: str | None = None
    last_error: str | None = None
