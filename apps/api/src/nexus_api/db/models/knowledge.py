"""``knowledge_documents`` (client KB) and ``partner_knowledge_documents`` (playbook).

v1 is deliberately **not** a vector store: a document is fetched/parsed
once, its plain text is kept in ``content_text`` and the worker injects
the ``indexed`` documents of the tenant into the system prompt under a
character cap (``nexus_worker.runtime.knowledge_context``). Semantic
search (pgvector, already available in the dev Postgres image) is the
planned evolution; the table shape (``chunk_count``, ``s3_key``) leaves
room for it without a rewrite.

``content_text`` NEVER leaves through the console API (C8-style rule:
the partner sees status + metadata, not the extracted body).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TimestampMixin, UUIDPrimaryKey


class KnowledgeDocumentKind(str, enum.Enum):
    FILE = "file"
    URL = "url"
    #: Spec 047 (37.3): lo que se enseña a mano con «Enseñar».
    NOTE = "note"


class KnowledgeDocumentStatus(str, enum.Enum):
    PENDING = "pending"
    INDEXED = "indexed"
    FAILED = "failed"


class KnowledgeErrorCode(str, enum.Enum):
    """Explainable, customer-safe failure codes (never free text)."""

    FETCH_FAILED = "fetch_failed"
    UNSUPPORTED_TYPE = "unsupported_type"
    TOO_LARGE = "too_large"
    EMPTY = "empty"


class KnowledgeDocument(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint("kind IN ('file','url','note')", name="ck_kd_kind"),
        CheckConstraint("status IN ('pending','indexed','failed')", name="ck_kd_status"),
        CheckConstraint("size_bytes >= 0", name="ck_kd_size"),
        CheckConstraint("chunk_count >= 0", name="ck_kd_chunks"),
        UniqueConstraint("tenant_id", "id", name="uq_knowledge_documents_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agents.tenant_id", "agents.id"],
            name="fk_kd_agent",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE", name="fk_kd_tenant"),
        nullable=False,
        index=True,
    )
    #: Spec 047 (0193): la capa. Nulo = del negocio, para todos sus agentes.
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    restore_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    s3_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime: Mapped[str] = mapped_column(String(120), nullable=False, default="text/plain")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default=KnowledgeDocumentStatus.PENDING.value
    )
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PartnerKnowledgeDocument(UUIDPrimaryKey, TimestampMixin, Base):
    """Partner playbook. Same shape as ``KnowledgeDocument``, RLS by partner."""

    __tablename__ = "partner_knowledge_documents"
    __table_args__ = (
        CheckConstraint("kind IN ('file','url')", name="ck_pkd_kind"),
        CheckConstraint("status IN ('pending','indexed','failed')", name="ck_pkd_status"),
        CheckConstraint("size_bytes >= 0", name="ck_pkd_size"),
        CheckConstraint("chunk_count >= 0", name="ck_pkd_chunks"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="CASCADE", name="fk_pkd_partner"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    s3_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime: Mapped[str] = mapped_column(String(120), nullable=False, default="text/plain")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default=KnowledgeDocumentStatus.PENDING.value
    )
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeChunk(Base):
    """Spec 047 (0193): un fragmento de una fuente, con su capa. Sin índice ANN:
    la búsqueda es exacta sobre las filas del cliente (research D14)."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_knowledge_chunks_tenant_id"),
        UniqueConstraint("tenant_id", "document_id", "ordinal", name="uq_knowledge_chunks_ordinal"),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["knowledge_documents.tenant_id", "knowledge_documents.id"],
            name="fk_knowledge_chunks_document",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agents.tenant_id", "agents.id"],
            name="fk_knowledge_chunks_agent",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('spanish', text)", persisted=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("now()")
    )


class KnowledgeChunkVector(Base):
    """Spec 047 (0193): el embedding de un fragmento, aparte y en la fila (sin
    TOAST), con su capa repetida para filtrar sin unir (research D14)."""

    __tablename__ = "knowledge_chunk_vectors"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "chunk_id"],
            ["knowledge_chunks.tenant_id", "knowledge_chunks.id"],
            name="fk_knowledge_chunk_vectors_chunk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agents.tenant_id", "agents.id"],
            name="fk_knowledge_chunk_vectors_agent",
            ondelete="CASCADE",
        ),
    )

    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    embedding: Mapped[Any] = mapped_column(HALFVEC(1024), nullable=False)


class KnowledgeRevision(Base):
    """Spec 047 (0193): la revisión de cada capa (nulo = la del negocio)."""

    __tablename__ = "knowledge_revisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    rev: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("now()")
    )


class TurnSource(Base):
    """Spec 047 (0193): las fuentes que usó una respuesta (38.3)."""

    __tablename__ = "turn_sources"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_turn_sources_tenant_id"),
        UniqueConstraint("tenant_id", "message_id", name="uq_turn_sources_message"),
        ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agents.tenant_id", "agents.id"],
            name="fk_turn_sources_agent",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    sources: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("now()")
    )


__all__ = [
    "KnowledgeChunk",
    "KnowledgeChunkVector",
    "KnowledgeDocument",
    "KnowledgeDocumentKind",
    "KnowledgeDocumentStatus",
    "KnowledgeErrorCode",
    "KnowledgeRevision",
    "PartnerKnowledgeDocument",
    "TurnSource",
]
