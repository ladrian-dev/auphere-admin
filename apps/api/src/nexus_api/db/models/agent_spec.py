"""Propuestas, pruebas y revisión de agentes — spec 047 (migración 0187,
``data-model.md`` §4).

- :class:`Proposal`: lo que propone el constructor, el copiloto, una sugerencia o
  una corrección. Nunca se aplica sola (§IV): una persona con permiso la aplica,
  y solo si el estado sobre el que se hizo (``state_hash``) sigue igual y no
  pasaron 15 minutos.
- La suite: :class:`AgentTestSuite` (una por agente), :class:`AgentTest`,
  :class:`AgentTestRun` y :class:`AgentTestResult` (tres pasadas).
- :class:`AgentReview`: los hallazgos de la revisión de una versión.
- De plataforma: :class:`SectorTestCatalog` y :class:`BuilderEvalRun`.

Todas las de cliente: RLS FORCE y FK compuestas (garantía 1); las de agente, en
el barrido de la garantía 9.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import UUIDPrimaryKey

PROPOSAL_KINDS: tuple[str, ...] = (
    "agent_spec_patch",
    "client_spec_patch",
    "test_add",
    "fix",
    "channel_config_patch",
)
PROPOSAL_AUTHORS: tuple[str, ...] = ("builder", "copilot", "suggestion", "correction")
PROPOSAL_STATUSES: tuple[str, ...] = ("open", "applied", "rejected", "expired", "stale")
TEST_KINDS: tuple[str, ...] = ("case", "sector", "person", "conversation", "correction")


def _now() -> Any:
    return text("now()")


def _agent_fk(table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["tenant_id", "agent_id"],
        ["agents.tenant_id", "agents.id"],
        name=f"fk_{table}_agent",
        ondelete="CASCADE",
    )


class Proposal(Base):
    __tablename__ = "proposals"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_proposals_tenant_id"),
        _agent_fk("proposals"),
    )

    #: uuid5 del contenido y del estado: proponer dos veces lo mismo es una fila.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    author: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(300), nullable=True)
    #: El parche (JSON Patch acotado) y lo que lo acompaña.
    diff: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="open")
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentTestSuite(UUIDPrimaryKey, Base):
    __tablename__ = "agent_test_suites"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_test_suites_tenant_id"),
        UniqueConstraint("tenant_id", "agent_id", name="uq_agent_test_suites_agent"),
        _agent_fk("agent_test_suites"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_now(), onupdate=_now()
    )


class AgentTest(UUIDPrimaryKey, Base):
    __tablename__ = "agent_tests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_tests_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "suite_id"],
            ["agent_test_suites.tenant_id", "agent_test_suites.id"],
            name="fk_agent_tests_suite",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "generated_guide_id"],
            ["generated_guides.tenant_id", "generated_guides.id"],
            name="fk_agent_tests_generated_guide",
            ondelete="SET NULL",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    suite_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    persona: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    first_message: Mapped[str] = mapped_column(Text, nullable=False)
    plan: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    #: Lo que tiene que quedar hecho: ``{"booking": {"service": …}}``, ``{"escalated": true}``…
    expected_state: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    #: Una dimensión por criterio: ``[{"key", "text"}]``.
    criteria: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    not_applicable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ``sector@versión#clave`` de una prueba del sector.
    sector_test_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: Spec 047, enmienda del 2026-10-29 (0206): la prueba del sector salió de una
    #: guía generada para este cliente (``origin: generated``, requisito 58.4).
    generated_guide_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="builder")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_now(), onupdate=_now()
    )


class AgentTestRun(UUIDPrimaryKey, Base):
    __tablename__ = "agent_test_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_test_runs_tenant_id"),
        _agent_fk("agent_test_runs"),
        ForeignKeyConstraint(
            ["tenant_id", "agent_config_id"],
            ["agent_configs.tenant_id", "agent_configs.id"],
            name="fk_agent_test_runs_version",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_config_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    model_policy: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    scope: Mapped[str] = mapped_column(String(12), nullable=False, default="all")
    reason: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="queued")
    paid_by: Mapped[str] = mapped_column(String(12), nullable=False, default="partner")
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    #: ``{"passed", "failed", "flaky", "unknown", "not_applicable", "critical_failed", "rate"}``.
    summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentTestResult(UUIDPrimaryKey, Base):
    __tablename__ = "agent_test_results"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_test_results_tenant_id"),
        UniqueConstraint(
            "tenant_id", "run_id", "test_id", "attempt", name="uq_agent_test_results_attempt"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["agent_test_runs.tenant_id", "agent_test_runs.id"],
            name="fk_agent_test_results_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "test_id"],
            ["agent_tests.tenant_id", "agent_tests.id"],
            name="fk_agent_test_results_test",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    test_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    attempt: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    #: ``None`` = «No sé» (el juez no pudo decidir).
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    dimensions: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_state: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    #: Sintético: el cliente es simulado, no hay datos de clientes finales.
    transcript: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    #: Spec 047, enmienda del 2026-10-29 (0206, requisito 61.3): por qué terminó la
    #: conversación con el cliente simulado (``TEST_STOPS``). La escribe la T206.
    stop: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_now()
    )


class AgentReview(UUIDPrimaryKey, Base):
    __tablename__ = "agent_reviews"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_reviews_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "agent_config_id"],
            ["agent_configs.tenant_id", "agent_configs.id"],
            name="fk_agent_reviews_version",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_config_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    #: ``[{"code", "severity": "block" | "warn", "message", "pointer", "fix"}]``.
    findings: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_now()
    )


class SectorTestCatalog(Base):
    """De plataforma: las 12 pruebas de cada sector, por versión."""

    __tablename__ = "sector_test_catalog"

    sector_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    tests: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_now()
    )
    published_by: Mapped[str] = mapped_column(String(160), nullable=False)


class BuilderEvalRun(UUIDPrimaryKey, Base):
    """De plataforma: la evaluación del constructor contra su banco."""

    __tablename__ = "builder_eval_runs"

    bank_version: Mapped[str] = mapped_column(String(40), nullable=False)
    results: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    validator_first_pass_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    sector_pass_unedited_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    draft_p90_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_now()
    )
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)


__all__ = [
    "PROPOSAL_AUTHORS",
    "PROPOSAL_KINDS",
    "PROPOSAL_STATUSES",
    "TEST_KINDS",
    "AgentReview",
    "AgentTest",
    "AgentTestResult",
    "AgentTestRun",
    "AgentTestSuite",
    "BuilderEvalRun",
    "Proposal",
    "SectorTestCatalog",
]


# ── Spec 047, enmienda del 2026-10-29 (migración 0206): las guías generadas ──

#: Por qué termina la conversación de una pasada (requisito 61.3).
TEST_STOPS: tuple[str, ...] = ("plan_done", "goodbye", "handoff", "turn_limit")
GENERATED_GUIDE_STATUSES: tuple[str, ...] = ("generated", "reviewed", "promoted", "archived")


class GeneratedGuide(UUIDPrimaryKey, Base):
    """La guía del sector que el constructor genera **para este cliente** cuando su
    sector no tiene guía de Auphere (requisito 58.4, D47): qué preguntar,
    procedimientos, riesgos y herramientas (``guide``) y sus 12 pruebas (``tests``).
    Es del cliente (garantía 1) y nunca se comparte; Auphere puede convertir una
    revisada y sin datos del cliente en guía propia (58.5, ``promoted_to``). La
    escribe la T201."""

    __tablename__ = "generated_guides"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_generated_guides_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "job_id"],
            ["jobs.tenant_id", "jobs.id"],
            name="fk_generated_guides_job",
            ondelete="SET NULL",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    #: La etiqueta del sector para la que se generó (1-40).
    sector_label: Mapped[str] = mapped_column(String(40), nullable=False)
    #: La etiqueta normalizada: una guía viva por etiqueta y cliente.
    label_key: Mapped[str] = mapped_column(String(60), nullable=False)
    guide: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    tests: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="generated", server_default="generated"
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_to: Mapped[str | None] = mapped_column(String(40), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_now(), onupdate=_now()
    )


class SectorGuide(Base):
    """De plataforma (0207): una guía de Auphere convertida desde la guía generada de
    un cliente, revisada y sin datos del cliente («Convertir en guía de Auphere»,
    requisito 58.5, D66). Nada en la fila apunta al cliente del que salió. Un cliente
    de «otro» con la misma ``label_key`` recibe esta guía; sus 12 pruebas están en
    ``sector_test_catalog`` con ``key``. Las de las plantillas viven en el código."""

    __tablename__ = "sector_guides"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(40), nullable=False)
    label_key: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    guide: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    published_by: Mapped[str] = mapped_column(String(160), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_now()
    )
