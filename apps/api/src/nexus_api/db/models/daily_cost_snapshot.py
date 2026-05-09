from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TenantScopedMixin, TimestampMixin, UUIDPrimaryKey


class DailyCostSnapshot(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    """One row per (tenant_id, day) maintained by the cost rollup cron.

    The cron upserts ``cost_usd_total`` from ``messages.cost_usd`` for the
    day. When the running total exceeds the tenant's
    ``cost_alert_threshold_usd_per_day`` for the first time on that day,
    ``threshold_exceeded_at`` is set and an ``audit_log`` row with
    ``action='cost.daily_threshold_exceeded'`` is written — the operator
    alerter then notifies via WhatsApp template ``alert_cost_threshold_v1``.

    Re-runs of the cron upsert; the ``threshold_exceeded_at`` only flips
    once per day so a single breach generates exactly one notification.
    RLS-forced.
    """

    __tablename__ = "daily_cost_snapshots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "day", name="uq_daily_cost_snapshots_tenant_day"),
    )

    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    cost_usd_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("0")
    )
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    threshold_exceeded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
