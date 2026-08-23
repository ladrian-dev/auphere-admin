"""Cuerpos del pack v1 en ``/console/*``. extra=forbid. Sin partner_id."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from nexus_api.packs.schema import Trigger, WorkflowCronSpec, WorkflowPackIn


class WorkflowCronOut(BaseModel):
    hour: int
    minute: int
    timezone: str


class WorkflowPackOut(BaseModel):
    client_ref: str
    is_set: bool = False
    version: int | None = None
    trigger: Trigger | None = None
    steps: list[str] = Field(default_factory=list)
    template_id: str | None = None
    cron: WorkflowCronOut | None = None
    enabled: bool | None = None
    end_time: datetime | None = None
    stop: str | None = None


class WorkflowRunOut(BaseModel):
    """``interrupted`` is a status, not an error."""

    thread_id: str
    status: str


class WorkflowRunsOut(BaseModel):
    items: list[WorkflowRunOut]


class WorkflowPackApply(WorkflowPackIn):
    """Alias so OpenAPI names the PUT body."""

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "WorkflowCronOut",
    "WorkflowCronSpec",
    "WorkflowPackApply",
    "WorkflowPackIn",
    "WorkflowPackOut",
    "WorkflowRunOut",
    "WorkflowRunsOut",
]
