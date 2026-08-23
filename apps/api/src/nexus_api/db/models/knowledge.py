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

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TimestampMixin, UUIDPrimaryKey


class KnowledgeDocumentKind(str, enum.Enum):
    FILE = "file"
    URL = "url"


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
        CheckConstraint("kind IN ('file','url')", name="ck_kd_kind"),
        CheckConstraint("status IN ('pending','indexed','failed')", name="ck_kd_status"),
        CheckConstraint("size_bytes >= 0", name="ck_kd_size"),
        CheckConstraint("chunk_count >= 0", name="ck_kd_chunks"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE", name="fk_kd_tenant"),
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


__all__ = [
    "KnowledgeDocument",
    "KnowledgeDocumentKind",
    "KnowledgeDocumentStatus",
    "KnowledgeErrorCode",
    "PartnerKnowledgeDocument",
]
