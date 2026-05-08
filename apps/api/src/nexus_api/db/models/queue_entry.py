from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from nexus_api.db.base import Base
from nexus_api.db.models._enum import pg_enum
from nexus_api.db.models._mixins import TenantScopedMixin, TimestampMixin, UUIDPrimaryKey


class QueueEntryStatus(str, enum.Enum):
    WAITING = "waiting"
    CHECKED_IN = "checked_in"
    SERVED = "served"
    LEFT = "left"


class QueueEntry(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    """Audit/history of queue events. Live queue state lives in Redis;
    this table records the durable record of joins / check-ins / leaves."""

    __tablename__ = "queue_entries"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    service_name: Mapped[str] = mapped_column(String(120), nullable=False)
    barber_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kg_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[QueueEntryStatus] = mapped_column(
        pg_enum(QueueEntryStatus, name="queue_entry_status"),
        nullable=False,
        default=QueueEntryStatus.WAITING,
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    served_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
