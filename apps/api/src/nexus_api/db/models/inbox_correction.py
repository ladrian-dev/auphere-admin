"""«Corregir esta respuesta» desde la Bandeja — spec 047 (migración 0198,
``data-model.md`` §9; requisito 52).

Una fila es lo que una persona del cliente escribió sobre una respuesta del
agente: la lección (cómo debió responder o la regla), su alcance (todo el negocio
o solo este agente), si es un **dato** o un **comportamiento**, y una paráfrasis
sin datos personales de lo que preguntó el cliente final. ``pii`` guarda **dónde**
quedan datos de un cliente final en la lección o en la paráfrasis (campo, tipo y
posiciones), nunca los datos.

- ``draft`` → ``applied``: un dato, en la ficha (``applied_change_id``) o en el
  conocimiento del agente (``knowledge_document_id``), con deshacer (``undone``).
- ``draft`` → ``proposed``: un comportamiento, como propuesta al partner con su
  prueba (``proposal_id``: el parche y la prueba juntos, como una sugerencia); el
  partner la acepta o la rechaza (``accepted`` o ``rejected``).

El partner lee ``lesson`` y ``paraphrase``, nunca ``message_id`` ni el mensaje
(C1). Ningún agente lee estas filas: las escribe y las lee la persona del cliente
y, de las de un agente, el partner en sus mejoras.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base

CORRECTION_SCOPES: Final[tuple[str, ...]] = ("business", "agent")
CORRECTION_KINDS: Final[tuple[str, ...]] = ("data", "behavior")
CORRECTION_STATUSES: Final[tuple[str, ...]] = (
    "draft",
    "applied",
    "proposed",
    "accepted",
    "rejected",
    "undone",
)
CORRECTION_ORIGINS: Final[tuple[str, ...]] = ("lite_web", "app")
LESSON_MAX: Final = 2000
PARAPHRASE_MAX: Final = 300


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _fk(column: str, table: str, *, ondelete: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["tenant_id", column],
        [f"{table}.tenant_id", f"{table}.id"],
        name=f"fk_inbox_corrections_{column.removesuffix('_id')}",
        ondelete=ondelete,
    )


class InboxCorrection(Base):
    __tablename__ = "inbox_corrections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_inbox_corrections_tenant_id"),
        CheckConstraint(
            f"origin IN ({_in(CORRECTION_ORIGINS)})", name="ck_inbox_corrections_origin"
        ),
        CheckConstraint(f"scope IN ({_in(CORRECTION_SCOPES)})", name="ck_inbox_corrections_scope"),
        CheckConstraint(f"kind IN ({_in(CORRECTION_KINDS)})", name="ck_inbox_corrections_kind"),
        CheckConstraint(
            f"status IN ({_in(CORRECTION_STATUSES)})", name="ck_inbox_corrections_status"
        ),
        _fk("conversation_id", "conversations", ondelete="CASCADE"),
        _fk("agent_id", "agents", ondelete="CASCADE"),
        _fk("applied_change_id", "business_changes", ondelete="SET NULL"),
        _fk("knowledge_document_id", "knowledge_documents", ondelete="SET NULL"),
        _fk("proposal_id", "proposals", ondelete="SET NULL"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    #: La respuesta del agente que se corrige. Sin FK: ``messages`` está particionada.
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    #: El agente que respondió; con ``scope = agent``, el único que aprende.
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    author_client_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    lesson: Mapped[str] = mapped_column(Text, nullable=False)
    paraphrase: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ``[{field, kind, start, end}]``: dónde hay datos de un cliente final.
    pii: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    #: ``If-Match`` del borrador: sube con cada edición.
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    applied_change_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    knowledge_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = [
    "CORRECTION_KINDS",
    "CORRECTION_ORIGINS",
    "CORRECTION_SCOPES",
    "CORRECTION_STATUSES",
    "LESSON_MAX",
    "PARAPHRASE_MAX",
    "InboxCorrection",
]
