"""ORM model for the Anthropic Memory tool backend.

Fase B of [[claude-platform-integration]]. The Memory tool
(``memory_20250818``) operates on a virtual filesystem ``/memories/…``;
this table is the storage backing it. Garantía 1 of
[[architecture/agent-isolation]] is enforced by RLS in migration 0032 —
the model exposes ``tenant_id`` so SQL queries the worker writes are
authored explicitly, but the policy is the authority.

The audit / versions table (``agent_memory_versions``) is filled by a DB
trigger; we do NOT model it as an ORM table because:

  - It is append-only and read-only from app code.
  - The retention cron uses raw SQL anyway (range delete by
    ``versioned_at``).
  - Modelling it would tempt a future maintainer into writing app-level
    inserts, bypassing the trigger and breaking the audit invariant.

If we ever need a read-only model for an admin "memory diff" UI, add it
as a separate dataclass / read-only mapped class and explicitly forbid
``session.add(...)`` of instances.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TenantScopedMixin, UUIDPrimaryKey


class AgentMemory(UUIDPrimaryKey, TenantScopedMixin, Base):
    """Current state of one memory file.

    ``customer_id`` is NULL for tenant-wide memories (policies / known
    issues curated by the operator). The path always starts with
    ``/memories/`` — enforced by the DB ``CHECK`` constraint in
    migration 0032 and validated app-side by
    ``nexus_worker.memory.path_validator``.

    ``size_bytes`` is computed by Postgres (``octet_length(content)``) so
    no app code can lie about it. The Memory tool enforces a per-customer
    byte cap by summing this column.
    """

    __tablename__ = "agent_memories"
    __table_args__ = (
        # Path-prefix invariant — duplicated in the DB CHECK constraint in
        # 0032 so the SQL refuses bad paths even if app validation breaks.
        CheckConstraint("path LIKE '/memories/%'", name="ck_agent_memories_path_prefix"),
        # The unique key created in 0032 wraps customer_id in COALESCE so
        # two NULLs at the same path collide as expected. The ORM only
        # needs the existence of the index — the predicate stays in SQL.
        Index("idx_agent_memories_tenant_customer", "tenant_id", "customer_id"),
    )

    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=True,
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Generated column — Postgres computes it from ``content``. Marked
    # ``init=False`` semantics by not specifying a default; the DB always
    # writes it. The ORM reads it back on flush.
    size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


__all__ = ["AgentMemory"]
