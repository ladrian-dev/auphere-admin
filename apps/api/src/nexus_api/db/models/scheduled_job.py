from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from nexus_api.db.base import Base
from nexus_api.db.models._enum import pg_enum
from nexus_api.db.models._mixins import TenantScopedMixin, TimestampMixin, UUIDPrimaryKey


class ScheduledJobKind(str, enum.Enum):
    REMINDER = "reminder"
    HEALTH_CHECK = "health_check"
    NO_SHOW_SCRAPE = "no_show_scrape"


class ScheduledJobStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ScheduledJob(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "scheduled_jobs"

    kind: Mapped[ScheduledJobKind] = mapped_column(
        pg_enum(ScheduledJobKind, name="scheduled_job_kind"),
        nullable=False,
    )
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[ScheduledJobStatus] = mapped_column(
        pg_enum(ScheduledJobStatus, name="scheduled_job_status"),
        nullable=False,
        default=ScheduledJobStatus.PENDING,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
