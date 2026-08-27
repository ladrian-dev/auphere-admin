"""Admin F2 — allowlist y LiteLLM block. El partner sale del path."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AdminModelsIn(BaseModel):
    """Sustituye la allowlist. El partner sale del path, nunca del cuerpo."""

    model_config = ConfigDict(extra="forbid")

    model_ids: list[str] = Field(default_factory=list)


class AdminModelItemOut(BaseModel):
    model_id: str
    display_name: str
    allowed: bool


class AdminModelsOut(BaseModel):
    items: list[AdminModelItemOut]


class AdminLlmBlockIn(BaseModel):
    """Bloquear o activar la VK del partner del path."""

    model_config = ConfigDict(extra="forbid")

    blocked: bool


class AdminLlmOut(BaseModel):
    blocked: bool
