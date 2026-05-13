"""Block P — eval suite ORM models.

Four tenant-scoped tables backing the regression suite of each agent:

- :class:`EvalDataset` — operator-curated collection of cases.
- :class:`EvalCase` — one row per ``(user_message, history, assertions)``.
- :class:`EvalRun` — execution of a dataset against an
  ``agent_config`` version.
- :class:`EvalRunResult` — per-case outcome within a run, with the
  transcript and the assertion breakdown.

RLS is applied in migration 0017 (FORCE) for all four. The
``Tenant.eval_required`` boolean is on the existing :class:`Tenant`
model — see ``tenant.py``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TenantScopedMixin, TimestampMixin, UUIDPrimaryKey


class EvalRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class EvalCaseResultStatus(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


class EvalDataset(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    """Operator-curated regression suite. Versioned by ``version`` int —
    when the operator wants to iterate, they create a new version
    instead of mutating the existing one, so historical runs keep
    pointing to a stable snapshot.

    ``pass_threshold`` is the share of cases that must pass for the
    run to be considered ``passed``. Default 0.95 mirrors the
    promotion gate's default expectation.
    """

    __tablename__ = "eval_datasets"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "name", "version", name="uq_eval_datasets_tenant_name_version"
        ),
        CheckConstraint(
            "pass_threshold >= 0 AND pass_threshold <= 1",
            name="ck_eval_datasets_pass_threshold",
        ),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    pass_threshold: Mapped[Decimal] = mapped_column(
        Numeric(4, 3),
        nullable=False,
        default=Decimal("0.950"),
        server_default="0.950",
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvalCase(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    """One case inside a dataset.

    ``assertions`` is a JSONB object with the structured checks (string
    contains, expected tools, LLM-as-judge questions). The runner
    validates the shape — see :mod:`services.evals.assertions`.

    ``history`` is the list of prior ``{role, content}`` messages the
    sandbox should feed before ``user_message``.
    """

    __tablename__ = "eval_cases"
    __table_args__ = (UniqueConstraint("dataset_id", "idx", name="uq_eval_cases_dataset_idx"),)

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    history: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    assertions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class EvalRun(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    """Execution of a dataset against a specific agent_config version.

    The promotion gate consults this table: when
    ``Tenant.eval_required=true``, promoting an agent_config version
    requires a recent ``EvalRun`` with ``status=PASSED`` referencing
    that ``agent_config_version``.

    ``dataset_version`` snapshots the integer at run-time. Subsequent
    edits to the dataset don't muddy historical reports.
    """

    __tablename__ = "eval_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'passed', 'failed', 'error')",
            name="ck_eval_runs_status",
        ),
        CheckConstraint(
            "pass_rate >= 0 AND pass_rate <= 1",
            name="ck_eval_runs_pass_rate",
        ),
    )

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_datasets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    dataset_version: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_config_version: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_config_status: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EvalRunStatus.PENDING.value
    )
    case_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pass_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pass_rate: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, default=Decimal("0.000")
    )
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class EvalRunResult(UUIDPrimaryKey, TenantScopedMixin, Base):
    """One row per (run, case). Includes a snapshot of the case (idx,
    name) so deleting / editing a case never invalidates historical
    reports."""

    __tablename__ = "eval_run_results"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pass', 'fail', 'error')",
            name="ck_eval_run_results_status",
        ),
        UniqueConstraint("run_id", "case_id", name="uq_eval_run_results_run_case"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_cases.id", ondelete="RESTRICT"),
        nullable=False,
    )
    case_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    case_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    transcript: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    assertion_results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
