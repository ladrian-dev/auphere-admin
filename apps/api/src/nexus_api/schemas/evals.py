"""Pydantic schemas for the eval suite (Block P)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ── Datasets ────────────────────────────────────────────────────────────────


class EvalDatasetCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    pass_threshold: Decimal | None = Field(default=None, ge=0, le=1)


class EvalDatasetUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    pass_threshold: Decimal | None = Field(default=None, ge=0, le=1)


class EvalDatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: str | None
    version: int
    pass_threshold: Decimal
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ── Cases ────────────────────────────────────────────────────────────────────


class EvalCaseAssertions(BaseModel):
    """Structured assertion DSL — operator-friendly, fully optional.

    Every field can be ``None`` (skipped) or a concrete value. At
    least ONE field must be set per case; an empty assertions object
    is rejected by :func:`services.evals.assertions.validate`.
    """

    model_config = ConfigDict(extra="forbid")

    must_contain: list[str] | None = Field(default=None)
    must_not_contain: list[str] | None = Field(default=None)
    expected_tools_called: list[str] | None = Field(default=None)
    tools_must_not_call: list[str] | None = Field(default=None)
    must_emit_text: bool | None = Field(default=None)
    judge_questions: list[str] | None = Field(default=None)


class EvalCaseCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    user_message: str = Field(min_length=1, max_length=20_000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=40)
    assertions: EvalCaseAssertions
    idx: int | None = Field(default=None, ge=0)


class EvalCaseUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    user_message: str | None = Field(default=None, min_length=1, max_length=20_000)
    history: list[dict[str, str]] | None = Field(default=None, max_length=40)
    assertions: EvalCaseAssertions | None = Field(default=None)
    idx: int | None = Field(default=None, ge=0)


class EvalCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    idx: int
    name: str
    user_message: str
    history: list[dict[str, str]]
    assertions: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class EvalDatasetDetailOut(EvalDatasetOut):
    cases: list[EvalCaseOut]


# ── Runs ────────────────────────────────────────────────────────────────────


class EvalRunStartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_config_version: int | None = Field(default=None, ge=1)


class AssertionResultOut(BaseModel):
    kind: str  # must_contain / expected_tools_called / judge_question / ...
    pass_: bool = Field(alias="pass")
    detail: str
    payload: dict[str, Any] | None = None

    model_config = ConfigDict(populate_by_name=True)


class EvalRunResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    case_id: uuid.UUID
    case_idx: int
    case_name: str
    status: str
    transcript: dict[str, Any]
    assertion_results: list[dict[str, Any]]
    latency_ms: int
    created_at: datetime


class EvalRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    dataset_id: uuid.UUID
    dataset_version: int
    agent_config_version: int
    agent_config_status: str
    status: str
    case_count: int
    pass_count: int
    fail_count: int
    error_count: int
    pass_rate: Decimal
    actor: str | None
    started_at: datetime
    finished_at: datetime | None
    error_message: str | None


class EvalRunDetailOut(EvalRunOut):
    results: list[EvalRunResultOut]


class PromoteOverrideIn(BaseModel):
    """Optional body for the existing promote endpoint when the
    operator wants to bypass the eval gate. Adds an audited reason
    string. ``override=true`` is required to actually skip the gate.
    """

    model_config = ConfigDict(extra="forbid")

    override: bool = False
    reason: str | None = Field(default=None, max_length=500)
