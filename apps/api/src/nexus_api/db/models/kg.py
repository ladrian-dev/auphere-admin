from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TenantScopedMixin, TimestampMixin, UUIDPrimaryKey


class KGSchema(UUIDPrimaryKey, TimestampMixin, Base):
    """Global library of KG schemas (one per vertical). Not tenant-scoped."""

    __tablename__ = "kg_schemas"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_kg_schemas_name_version"),)

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    schema_definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class KGNode(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "kg_nodes"

    label: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)


class KGEdge(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "kg_edges"

    label: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kg_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kg_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
