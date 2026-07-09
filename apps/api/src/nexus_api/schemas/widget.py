"""Pydantic schemas for the public web chat widget (``/v1/widget/*``).

All browser-facing. Responses never expose internal tenant ids — the
tenant lives only in the signed session JWT. The visitor is anonymous:
identity is a ``session_id`` the loader stores in ``localStorage``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WidgetSessionCreate(BaseModel):
    # Public, non-secret site key from the ``<script>`` snippet.
    public_key: str = Field(min_length=1, max_length=64)
    # Returning visitor's stored session id (uuid hex). Omitted on the very
    # first visit; the server mints one. High-entropy, so echoing it back is
    # safe — it is the anonymous customer identity, scoped to the tenant.
    session_id: str | None = Field(default=None, min_length=8, max_length=64)


class WidgetConfigOut(BaseModel):
    greeting: str | None = None
    appearance: dict[str, Any] = Field(default_factory=dict)


class WidgetSessionOut(BaseModel):
    session_token: str
    session_id: str
    expires_in: int
    config: WidgetConfigOut


class WidgetMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4096)


class WidgetSendAck(BaseModel):
    status: Literal["enqueued"]


class WidgetMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    direction: str
    content: str
    interactive_payload: dict[str, Any] | None = None
    created_at: datetime


class WidgetPollOut(BaseModel):
    messages: list[WidgetMessageOut]
    # Server clock at read time — the loader uses it as the next ``since``
    # so polling is immune to client/server clock skew.
    server_time: datetime
