"""Broadcast fan-out tracking (migration 0048, ADR-028).

A broadcast is one ``POST /v1/embed/broadcasts`` call: template +
recipients[] + named variables. The fan-out service expands it into N
``messages`` rows (status=pending, template_payload set) that the
existing outbound dispatcher drains; these tables only track the
grouping and the per-recipient acceptance verdict.

Both tables are tenant-scoped with RLS+FORCE (added in 0048 following
the 0002 pattern), so the embed JWT surface can never read or write a
broadcast across tenants.

Per-recipient delivery state is NOT duplicated here — the status query
joins ``broadcast_recipients.message_id → messages.status`` so the
webhook status callbacks keep working unchanged.
"""

from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TenantScopedMixin, TimestampMixin, UUIDPrimaryKey


class BroadcastStatus(str, enum.Enum):
    ACCEPTED = "accepted"
    COMPLETED = "completed"


class BroadcastRecipientStatus(str, enum.Enum):
    QUEUED = "queued"
    REJECTED = "rejected"


class Broadcast(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "broadcasts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('accepted', 'completed')",
            name="ck_broadcasts_status",
        ),
        # Partner-supplied idempotency key: replaying the same broadcast
        # returns the original instead of double-sending.
        Index(
            "uq_broadcasts_tenant_idempotency",
            "tenant_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index("ix_broadcasts_tenant_created", "tenant_id", "created_at"),
    )

    # Attribution: which partner's widget created it (platform-level id,
    # no FK cascade into tenant data).
    partner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="RESTRICT"),
        nullable=False,
    )
    template_name: Mapped[str] = mapped_column(String(120), nullable=False)
    template_language: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BroadcastStatus.ACCEPTED.value
    )
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # jti of the session token that created it — joins the audit trail.
    jti: Mapped[str | None] = mapped_column(String(40), nullable=True)


class BroadcastRecipient(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "broadcast_recipients"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'rejected')",
            name="ck_broadcast_recipients_status",
        ),
        UniqueConstraint("broadcast_id", "phone_e164", name="uq_broadcast_recipients_phone"),
        Index("ix_broadcast_recipients_tenant_broadcast", "tenant_id", "broadcast_id"),
    )

    broadcast_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("broadcasts.id", ondelete="CASCADE"),
        nullable=False,
    )
    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False)
    # Named template variables for this recipient, e.g.
    # {"body": {"cliente": "Ana", "saldo_pendiente": "$12.000"}}.
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # opted_out / invalid_phone / duplicate — why a recipient was
    # rejected at accept time (delivery failures live on the message).
    reject_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
