"""Closed v1 pack YAML. Extra keys (including partner_id) are 422."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

CLOSED_STEP_IDS: frozenset[str] = frozenset({"send_template", "wait_reply", "end"})
Trigger = Literal["cron", "event"]


class WorkflowCronSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hour: int = Field(ge=0, le=23)
    minute: int = Field(ge=0, le=59)
    timezone: str = Field(min_length=1, max_length=64)

    @field_validator("timezone")
    @classmethod
    def _iana(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone {value!r}") from exc
        return value


class WorkflowPackSpec(BaseModel):
    """Persisted shape. Never includes partner_id."""

    model_config = ConfigDict(extra="forbid")

    client_ref: str | None = Field(default=None, max_length=255)
    trigger: Trigger
    steps: list[str] = Field(min_length=1)
    template_id: str | None = Field(default=None, max_length=255)
    cron: WorkflowCronSpec | None = None
    enabled: bool = True
    end_time: datetime | None = None
    stop: Literal["end"] = "end"

    @field_validator("steps")
    @classmethod
    def _closed_steps(cls, steps: list[str]) -> list[str]:
        unknown = [s for s in steps if s not in CLOSED_STEP_IDS]
        if unknown:
            raise ValueError(f"unknown step id: {unknown[0]}")
        return steps

    @model_validator(mode="after")
    def _art50_and_cron(self) -> WorkflowPackSpec:
        if "send_template" in self.steps and self.steps[0] != "send_template":
            raise ValueError("first outbound must be send_template")
        if self.trigger == "cron":
            if self.cron is None:
                raise ValueError("cron trigger requires cron.hour/minute/timezone")
            if self.steps[0] != "send_template":
                raise ValueError("cron first outbound must be send_template")
        if "send_template" in self.steps and not (self.template_id or "").strip():
            raise ValueError("template_id is required when steps include send_template")
        return self


class WorkflowPackIn(BaseModel):
    """PUT body: YAML-as-object or a ``yaml`` field. extra=forbid."""

    model_config = ConfigDict(extra="forbid")

    yaml: str | dict[str, Any] | None = None
    client_ref: str | None = Field(default=None, max_length=255)
    trigger: Trigger | None = None
    steps: list[str] | None = None
    template_id: str | None = Field(default=None, max_length=255)
    cron: WorkflowCronSpec | None = None
    enabled: bool | None = None
    end_time: datetime | None = None
    stop: Literal["end"] | None = None


def parse_workflow_body(body: WorkflowPackIn) -> WorkflowPackSpec:
    """Merge object fields with optional ``yaml``. ``partner_id`` is extra → 422."""
    data = body.model_dump(exclude_none=True)
    raw = data.pop("yaml", None)
    if isinstance(raw, str):
        loaded = yaml.safe_load(raw)
        if not isinstance(loaded, dict):
            raise ValueError("yaml must be a mapping")
        raw = loaded
    merged = {**raw, **data} if isinstance(raw, dict) else data
    try:
        return WorkflowPackSpec.model_validate(merged)
    except ValidationError:
        raise
