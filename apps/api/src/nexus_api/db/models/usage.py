from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TenantScopedMixin, TimestampMixin, UUIDPrimaryKey


class UsageEvent(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    """Daily aggregated usage metrics per (tenant, event_type, day)."""

    __tablename__ = "usage_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "event_type", "day", name="uq_usage_events_tenant_event_day"),
    )

    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    day: Mapped[date] = mapped_column(Date, nullable=False)
