"""workflow_packs / runs / crons / send receipts — FORCE RLS by partner_id."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TimestampMixin, UUIDPrimaryKey

PACK_TRIGGERS = ("cron", "event")
RUN_STATUSES = ("pending", "running", "error", "success", "timeout", "interrupted")


class WorkflowPack(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "workflow_packs"
    __table_args__ = (
        UniqueConstraint("partner_id", "client_ref", name="uq_workflow_packs_partner_client"),
        ForeignKeyConstraint(
            ["partner_id", "client_ref"],
            ["partner_tenants.partner_id", "partner_tenants.external_client_ref"],
            ondelete="CASCADE",
            name="fk_workflow_packs_client",
        ),
        CheckConstraint("trigger IN ('cron','event')", name="ck_workflow_packs_trigger"),
        CheckConstraint("version >= 1", name="ck_workflow_packs_version"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="CASCADE", name="fk_workflow_packs_partner"),
        nullable=False,
    )
    client_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    yaml: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class WorkflowRun(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','error','success','timeout','interrupted')",
            name="ck_workflow_runs_status",
        ),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="CASCADE", name="fk_workflow_runs_partner"),
        nullable=False,
    )
    pack_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_packs.id", ondelete="CASCADE", name="fk_workflow_runs_pack"),
        nullable=False,
    )
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")


class WorkflowCron(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "workflow_crons"
    __table_args__ = (UniqueConstraint("pack_id", name="uq_workflow_crons_pack"),)

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="CASCADE", name="fk_workflow_crons_partner"),
        nullable=False,
    )
    pack_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_packs.id", ondelete="CASCADE", name="fk_workflow_crons_pack"),
        nullable=False,
    )
    run_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    hour: Mapped[int] = mapped_column(Integer, nullable=False)
    minute: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowSendReceipt(UUIDPrimaryKey, TimestampMixin, Base):
    """Idempotency key (thread_id, step_id, run_id). Written before wait_reply."""

    __tablename__ = "workflow_send_receipts"
    __table_args__ = (
        UniqueConstraint("thread_id", "step_id", "run_id", name="uq_workflow_send_receipts_key"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="CASCADE", name="fk_workflow_send_receipts_partner"),
        nullable=False,
    )
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False)
    step_id: Mapped[str] = mapped_column(String(32), nullable=False)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
