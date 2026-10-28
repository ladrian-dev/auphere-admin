"""Esquemas del constructor de agentes en la consola (spec 047, T080;
``contracts/console-api.md`` §4)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DraftStart = Literal["describe", "template", "blank"]


class DraftJobIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=40)
    #: «¿Qué tiene que hacer?» (20 a 1.024). Opcional solo «En blanco».
    description: str | None = Field(default=None, max_length=1024)
    start: DraftStart = "describe"
    template_id: str | None = Field(default=None, max_length=80)


class DraftJobOut(BaseModel):
    job_id: uuid.UUID
    status: Literal["queued", "running", "done", "failed"]
    agent_id: uuid.UUID | None = None


class TemplateOptionOut(BaseModel):
    id: str
    name: str
    group: str
    is_default: bool = False


class DraftOptionsOut(BaseModel):
    """Lo que ofrece «Nuevo agente»: los ejemplos y las plantillas, con la del
    partner primero (17.8, 17.9)."""

    examples: list[str]
    templates: list[TemplateOptionOut]
    default_template: str | None = None
    name_max: int = 40
    description_min: int = 20
    description_max: int = 1024


class AnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=1000)
    #: Dónde se guarda: la ficha (por defecto) o «Solo este agente» (17.5).
    scope: Literal["business", "agent"] | None = None


class AnswersIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: list[AnswerIn] = Field(min_length=1, max_length=5)


class AnswerAppliedOut(BaseModel):
    question_id: str
    scope: Literal["business", "agent"]
    target: str


class AnswersOut(BaseModel):
    applied: list[AnswerAppliedOut]
    agent_id: uuid.UUID
    draft_revision: int
    tests_stale: int


class ProposalOut(BaseModel):
    id: uuid.UUID
    kind: str
    author: str
    summary: str | None
    diff: dict[str, Any]
    status: str
    created_at: datetime
    expires_at: datetime
    problems: list[dict[str, str]] = Field(default_factory=list)


class ProposalDecisionOut(BaseModel):
    id: uuid.UUID
    status: str
    draft_revision: int | None = None


__all__ = [
    "AnswerAppliedOut",
    "AnswerIn",
    "AnswersIn",
    "AnswersOut",
    "DraftJobIn",
    "DraftJobOut",
    "DraftOptionsOut",
    "DraftStart",
    "ProposalDecisionOut",
    "ProposalOut",
    "TemplateOptionOut",
]
