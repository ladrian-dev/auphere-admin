from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    version: int
    status: str
    system_prompt_rendered: str
    channels: list[dict[str, Any]]
    tools: list[str]
    policies: dict[str, Any]
    seed_template_ref: str | None
    kg_schema_id: uuid.UUID | None
    created_by: str | None
    promoted_at: datetime | None
    promoted_by: str | None
    created_at: datetime
    updated_at: datetime


class AgentConfigStageIn(BaseModel):
    """Body for PUT /admin/tenants/:id/agent-config — creates a new staged version."""

    system_prompt_rendered: str = Field(min_length=1, max_length=200_000)
    channels: list[dict[str, Any]] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    policies: dict[str, Any] = Field(default_factory=dict)
    seed_template_ref: str | None = None
    kg_schema_id: uuid.UUID | None = None


class AgentConfigBundle(BaseModel):
    """Active version + all versions, in one payload — what the panel needs to render."""

    active: AgentConfigOut | None
    versions: list[AgentConfigOut]
