"""``operator_notifications`` ORM model.

Block F — ledger that prevents the operator alerter from re-notifying on
the same ``audit_log`` row across ticks. See migration ``0010``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._enum import pg_enum
from nexus_api.db.models._mixins import TenantScopedMixin, TimestampMixin, UUIDPrimaryKey


class OperatorNotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class OperatorNotification(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "operator_notifications"
    __table_args__ = (UniqueConstraint("audit_log_id", name="uq_operator_notifications_audit_log"),)

    audit_log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("audit_log.id", ondelete="CASCADE"),
        nullable=False,
    )
    template_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[OperatorNotificationStatus] = mapped_column(
        pg_enum(OperatorNotificationStatus, name="operator_notification_status"),
        nullable=False,
        default=OperatorNotificationStatus.PENDING,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retried_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
