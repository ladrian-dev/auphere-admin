"""Trabajos largos — spec 047 (migración 0175, ``data-model.md`` §4).

Leer la web, construir un agente, correr sus pruebas, publicar, certificar:
todo lo que tarda más que una petición responde ``202 {job_id}`` y deja aquí su
ciclo de vida. Una sola tabla para todos los tipos porque comparten el ciclo
(cola → en marcha → hecho | fallido), el progreso por bloques y la caducidad, y
la consola los consulta por una sola ruta.

Por cliente, con RLS FORCE y FK compuesta ``(tenant_id, agent_id)``. La consola
llega a un trabajo solo por su id: la función SQL ``job_tenant`` (SECURITY
DEFINER) devuelve su cliente y nada más, y la API comprueba la pertenencia al
partner antes de abrir la transacción con ese cliente.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import UUIDPrimaryKey

JOB_KINDS: tuple[str, ...] = (
    "client_read",
    "client_builder",
    "agent_draft",
    "tests",
    "publish",
    "fix",
    "copilot",
    "quality_check",
    "suggestions",
)
JOB_STATUSES: tuple[str, ...] = ("queued", "running", "done", "failed")
#: Los estados en los que un trabajo sigue vivo y puede caducar.
LIVE_JOB_STATUSES: tuple[str, ...] = ("queued", "running")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class Job(UUIDPrimaryKey, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_jobs_tenant_id"),
        CheckConstraint(f"kind IN ({_in(JOB_KINDS)})", name="ck_jobs_kind"),
        CheckConstraint(f"status IN ({_in(JOB_STATUSES)})", name="ck_jobs_status"),
        CheckConstraint(
            "(status IN ('done', 'failed')) = (finished_at IS NOT NULL)", name="ck_jobs_finished"
        ),
        CheckConstraint(
            "status <> 'failed' OR error_code IS NOT NULL", name="ck_jobs_failed_has_code"
        ),
        CheckConstraint("cost_micros >= 0", name="ck_jobs_cost"),
        ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agents.tenant_id", "agents.id"],
            name="fk_jobs_agent",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    #: Los bloques ya escritos y el paso actual: ``{"step": str, "blocks": [...]}``.
    progress: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    questions: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    answers: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Lo que costó, en cien milésimas de USD (partida «Construcción y pruebas»).
    cost_micros: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    #: Solo ``publish``: la revisión del borrador que se publica.
    draft_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: La persona que lo lanzó; ``None`` si lo lanzó el sistema.
    created_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: El latido: cada avance lo mueve. Un trabajo vivo sin latido caduca.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
