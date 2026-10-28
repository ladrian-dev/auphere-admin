"""Las sugerencias semanales de un agente — spec 047 (migración 0199,
``data-model.md`` §9; requisito 51).

Una fila es el resultado **agregado** de leer las conversaciones de una semana en
el worker, dentro del cliente (51.5): una paráfrasis sin datos personales
(``topic``), cuántas conversaciones y cuántos contactos distintos la sostienen
(al menos 5 y 5, 51.3) y la propuesta con su parche y su prueba
(``proposal_id``). No guarda a qué conversaciones ni a qué contactos se refiere:
el partner no puede llegar desde aquí a ningún mensaje (C1 y C8).

- ``open`` → ``accepted``: el cambio y su prueba van al borrador del agente y
  pasan la puerta al guardar (51.4).
- ``open`` → ``discarded``: con su motivo; la misma sugerencia (``topic_key`` o
  el mismo parche, ``diff_hash``) no vuelve hasta ``suppress_until`` (30 días).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Final

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base

SUGGESTION_STATUSES: Final[tuple[str, ...]] = ("open", "accepted", "discarded")


class AgentSuggestion(Base):
    __tablename__ = "agent_suggestions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_suggestions_tenant_id"),
        UniqueConstraint(
            "tenant_id", "agent_id", "week", "topic_key", name="uq_agent_suggestions_topic"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agents.tenant_id", "agents.id"],
            name="fk_agent_suggestions_agent",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "proposal_id"],
            ["proposals.tenant_id", "proposals.id"],
            name="fk_agent_suggestions_proposal",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "test_id"],
            ["agent_tests.tenant_id", "agent_tests.id"],
            name="fk_agent_suggestions_test",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "job_id"],
            ["jobs.tenant_id", "jobs.id"],
            name="fk_agent_suggestions_job",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    #: El lunes (UTC) de la semana leída.
    week: Mapped[date] = mapped_column(Date, nullable=False)
    #: La clave estable del tema (``aparcamiento``): lo que se aparta al descartar.
    topic_key: Mapped[str] = mapped_column(String(60), nullable=False)
    #: La paráfrasis, sin datos personales.
    topic: Mapped[str] = mapped_column(String(300), nullable=False)
    #: Lo que cambia la propuesta, dicho para el partner.
    summary: Mapped[str | None] = mapped_column(String(300), nullable=True)
    conversations_count: Mapped[int] = mapped_column(Integer, nullable=False)
    contacts_count: Mapped[int] = mapped_column(Integer, nullable=False)
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    #: ``canonical_hash`` del parche y la prueba: el mismo cambio con otras palabras
    #: también se aparta al descartar.
    diff_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: La prueba que entró en la suite al aceptar.
    test_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    #: La pasada semanal que la generó (``jobs``, ``kind = suggestions``).
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="open", server_default="open"
    )
    discard_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    suppress_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


__all__ = ["SUGGESTION_STATUSES", "AgentSuggestion"]
