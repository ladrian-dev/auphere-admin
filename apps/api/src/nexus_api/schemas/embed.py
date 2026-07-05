"""Pydantic schemas for the browser-facing embed surface (ADR-028).

Everything here is consumed by the iframe app (``embed.auphere.com``)
authenticated with a widget session JWT. Responses never carry internal
tenant ids — the token already scopes everything.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from nexus_api.services.whatsapp_templates import TemplateOut


class EmbedStatusOut(BaseModel):
    status: Literal["connected", "not_connected"]
    display_phone_number: str | None = None


class EmbedTemplatesOut(BaseModel):
    templates: list[TemplateOut]


class PartnerConfigOut(BaseModel):
    """Public (unauthenticated) — feeds the CSP ``frame-ancestors``
    middleware of the embed app. Origins are not secrets: they are
    visible in every embedding page anyway."""

    allowed_origins: list[str]


class BroadcastRecipientIn(BaseModel):
    phone: str = Field(min_length=8, max_length=20)
    variables: dict[str, str] = Field(default_factory=dict)


class BroadcastCreateIn(BaseModel):
    template_name: str = Field(min_length=1, max_length=120)
    language: str = Field(default="es", min_length=2, max_length=20)
    recipients: list[BroadcastRecipientIn] = Field(min_length=1)
    idempotency_key: str | None = Field(default=None, max_length=80)


class RejectedRecipientOut(BaseModel):
    phone: str
    reason: str


class BroadcastAcceptedOut(BaseModel):
    broadcast_id: uuid.UUID
    accepted: int
    rejected: list[RejectedRecipientOut]


class BroadcastRecipientStatusOut(BaseModel):
    phone: str
    status: str  # queued | rejected | sent | delivered | read | failed
    reason: str | None = None


class BroadcastStatusOut(BaseModel):
    broadcast_id: uuid.UUID
    template_name: str
    status: str
    created_at: datetime
    counts: dict[str, Any]
    recipients: list[BroadcastRecipientStatusOut]
