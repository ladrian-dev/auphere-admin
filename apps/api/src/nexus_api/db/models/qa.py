"""QA Playground models (ADR-020, Phase 3).

All three tables live in the ``qa`` schema and are RLS-protected by
``operator_id`` (see migration 0025). The connecting code MUST set both
``app.tenant_id`` (when the request also touches tenant-scoped tables)
and ``app.operator_id`` inside the transaction; missing the operator
setting yields zero rows from any of these tables — fail-closed.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import UUIDPrimaryKey


class QAThread(UUIDPrimaryKey, Base):
    """One QA conversation between an operator and a tenant's agent.

    ``external_id`` is the LangGraph Server thread id. We mint our own row
    first (so the operator sees the thread in the list immediately) and
    fill ``external_id`` once the first run is dispatched.
    """

    __tablename__ = "threads"
    __table_args__ = ({"schema": "qa"},)

    operator_id: Mapped[str] = mapped_column(
        String(120), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True, unique=True
    )
    # Migration 0027: the underlying ``conversations`` row that holds
    # the inbound/outbound ``messages`` for this QA thread. Filled
    # lazily on the first send by ``POST /qa/threads/{id}/send``;
    # ``ON DELETE SET NULL`` so archiving a tenant's conversation
    # doesn't orphan the thread row.
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, server_default=text("'Untitled'")
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
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


class QASideEffectAudit(UUIDPrimaryKey, Base):
    """Append-only log of tool dispatch attempts the dry_run gate blocked.

    Every row here corresponds to a side-effecting tool call the agent
    *wanted* to make during a QA turn but didn't, because the run was in
    dry-run mode. The MCP registry's dry_run middleware persists one of
    these per blocked call; the QA Playground UI reads them to build the
    "what would have happened" audit panel.
    """

    __tablename__ = "side_effect_audit"
    __table_args__ = ({"schema": "qa"},)

    operator_id: Mapped[str] = mapped_column(
        String(120), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("qa.threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(160), nullable=False)
    tool_args: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    synthetic_result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    blocked_reason: Mapped[str] = mapped_column(
        String(80), nullable=False, server_default=text("'dry_run'")
    )
    run_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class QAAuditLog(UUIDPrimaryKey, Base):
    """Operator action log — distinct from the global ``audit_log``.

    Captures intent events that are interesting for the QA Playground
    even when they have no tenant correlate: operator opened the
    Inspector, switched preview channel, copied a UCM payload, etc.
    """

    __tablename__ = "audit_log"
    __table_args__ = ({"schema": "qa"},)

    operator_id: Mapped[str] = mapped_column(
        String(120), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
    )
    thread_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    target_kind: Mapped[str | None] = mapped_column(String(60), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
