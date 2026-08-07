"""Pydantic schemas for template messaging on the partner surface.

Consumed by ``/v1/partners/clients/{ref}/templates`` and
``.../broadcasts``: a partner's backend lists the approved templates in
its client's WABA and sends one to N of that client's contacts, using
its secret API key.

Responses never carry internal tenant ids — the partner addresses its
clients by its own ``external_client_ref`` and nothing else.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from nexus_api.services.whatsapp_templates import TemplateOut


class ClientTemplatesOut(BaseModel):
    """APPROVED templates only — offering anything else would produce a
    send that Meta rejects."""

    templates: list[TemplateOut]


class BroadcastRecipientIn(BaseModel):
    phone: str = Field(min_length=8, max_length=20)
    variables: dict[str, str] = Field(default_factory=dict)


class BroadcastCreateIn(BaseModel):
    """One approved template, 1..N recipients.

    ``variables`` keys must match the template's NAMED parameters
    (``{{cliente}}``); positional ones are rejected. ``idempotency_key``
    makes a retry safe: replaying it returns the original result instead
    of sending twice.
    """

    template_name: str = Field(min_length=1, max_length=120)
    language: str = Field(default="es", min_length=2, max_length=20)
    recipients: list[BroadcastRecipientIn] = Field(min_length=1)
    idempotency_key: str | None = Field(default=None, max_length=80)
    channel_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Which of the client's WhatsApp numbers to send from. Omit it to "
            "use the number assigned the 'notifications' role, or the only "
            "number when there is just one."
        ),
    )


class RejectedRecipientOut(BaseModel):
    phone: str
    reason: str


class BroadcastAcceptedOut(BaseModel):
    broadcast_id: uuid.UUID
    accepted: int
    rejected: list[RejectedRecipientOut]


class BroadcastRecipientStatusOut(BaseModel):
    phone: str
    status: str  # pending | rejected | sent | delivered | read | failed
    reason: str | None = None


class BroadcastStatusOut(BaseModel):
    broadcast_id: uuid.UUID
    template_name: str
    status: str
    created_at: datetime
    counts: dict[str, Any]
    recipients: list[BroadcastRecipientStatusOut]
