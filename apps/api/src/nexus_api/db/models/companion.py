"""Modelos del Companion de la consola (CO-01, migración 0090).

Las cuatro tablas viven bajo el esquema ``companion`` y están protegidas
por RLS **por ``principal_id``** — el mismo patrón fail-closed que ``qa.*``
por ``operator_id``. El código que las toca DEBE aplicar
``app.principal_id`` dentro de la transacción
(:func:`nexus_api.core.principal_context.apply_principal_to_session`);
sin el GUC no se ve ninguna fila, que es lo que se quiere.

``principal_id`` es texto porque ``partner_memberships.user_id`` lo es.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import UUIDPrimaryKey

SCHEMA = "companion"

# ── estados de un run ──────────────────────────────────────────────────
#
# ``interrupted`` no es un ``error``: el proceso de la API se reinició a
# mitad de run. El usuario tiene que ver qué pasó, no un fallo que no
# ocurrió ni una pantalla en blanco.
RUN_RUNNING = "running"
RUN_COMPLETED = "completed"
RUN_CANCELLED = "cancelled"
RUN_ERROR = "error"
RUN_INTERRUPTED = "interrupted"
RUN_STATUSES: tuple[str, ...] = (
    RUN_RUNNING,
    RUN_COMPLETED,
    RUN_CANCELLED,
    RUN_ERROR,
    RUN_INTERRUPTED,
)
#: Un run en cualquiera de estos ya no produce eventos nuevos.
TERMINAL_RUN_STATUSES: frozenset[str] = frozenset(
    {RUN_COMPLETED, RUN_CANCELLED, RUN_ERROR, RUN_INTERRUPTED}
)

# ── modos del hilo ─────────────────────────────────────────────────────
#
# El cambio de modo es un acto del usuario, nunca del modelo. En CO-01 solo
# existe ``consult`` de facto (no hay herramientas); ``build`` se declara ya
# para que el dato no cambie de forma cuando llegue CO-04.
MODE_CONSULT = "consult"
MODE_BUILD = "build"
THREAD_MODES: tuple[str, ...] = (MODE_CONSULT, MODE_BUILD)


class CompanionThread(UUIDPrimaryKey, Base):
    """Una conversación entre una persona del partner y el Companion."""

    __tablename__ = "threads"
    __table_args__ = (
        CheckConstraint("mode IN ('consult', 'build')", name="ck_companion_threads_mode"),
        {"schema": SCHEMA},
    )

    principal_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partners.id", ondelete="CASCADE"), nullable=False
    )
    # NULLABLE: un hilo puede empezar sin cliente ("créame un agente para una
    # clínica dental") y atarse a uno después. SET NULL al borrar el tenant —
    # la conversación en la que se decidió algo sobrevive al cliente.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'Nueva conversación'")
    )
    mode: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'consult'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CompanionRun(UUIDPrimaryKey, Base):
    """Un turno. La fila la cierra la propia API al terminar el stream, lo
    que hace que el tope mensual sea síncrono y no dependa del consumidor
    de metering — mismo razonamiento que ``qa.runs`` en CP-16."""

    __tablename__ = "runs"
    __table_args__ = ({"schema": SCHEMA},)

    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    principal_id: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'running'"))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class CompanionMessage(UUIDPrimaryKey, Base):
    """Un mensaje del hilo. **Sin razonamiento**: los bloques de pensamiento
    viajan por el stream y mueren con la sesión (§8.2 de la investigación).

    ``content`` es la transcripción del Companion: lo que Auphere le dijo al
    partner y lo que el partner le dijo a Auphere. **Nunca** el cuerpo de un
    mensaje de un cliente final — eso lo garantiza el catálogo cerrado de
    ``api/companion_streaming.py`` y el test de aislamiento que lo prueba.
    """

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("thread_id", "seq", name="uq_companion_messages_thread_seq"),
        {"schema": SCHEMA},
    )

    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.runs.id", ondelete="SET NULL"), nullable=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    tool_calls: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class CompanionAction(Base):
    """Una acción propuesta y su decisión. La escribe CO-04.

    ``id`` **sin default**: se deriva de forma determinista del run y del
    índice del paso, y se escribe con UPSERT. ``interrupt()`` de LangGraph
    reanuda re-ejecutando el nodo entero desde la primera línea; con un
    INSERT la acción entraría dos veces en cada confirmación (Parte II, C2).
    """

    __tablename__ = "actions"
    __table_args__ = ({"schema": SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.runs.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    diff: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    state_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'proposed'"))
    proposed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


__all__ = [
    "MODE_BUILD",
    "MODE_CONSULT",
    "RUN_CANCELLED",
    "RUN_COMPLETED",
    "RUN_ERROR",
    "RUN_INTERRUPTED",
    "RUN_RUNNING",
    "RUN_STATUSES",
    "TERMINAL_RUN_STATUSES",
    "THREAD_MODES",
    "CompanionAction",
    "CompanionMessage",
    "CompanionRun",
    "CompanionThread",
]
