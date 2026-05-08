from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    channel_id: uuid.UUID
    customer_id: uuid.UUID
    status: str
    created_at: datetime
    updated_at: datetime


class ConversationPageOut(BaseModel):
    items: list[ConversationOut]
    next_cursor: str | None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    direction: str
    content: str
    intent: str | None
    cost_usd: float | None
    latency_ms: int | None
    model: str | None
    trace_id: str | None
    tool_calls: list[dict[str, Any]]
    created_at: datetime
