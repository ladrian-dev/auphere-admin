from __future__ import annotations

import enum
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._enum import pg_enum
from nexus_api.db.models._mixins import TimestampMixin, UUIDPrimaryKey


class TenantPlan(str, enum.Enum):
    ESSENTIAL = "essential"
    PRO = "pro"
    BUSINESS = "business"
    INTERNAL = "internal"  # canary / Auphere internal tenants


class TenantStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class Tenant(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    plan: Mapped[TenantPlan] = mapped_column(
        pg_enum(TenantPlan, name="tenant_plan"),
        nullable=False,
        default=TenantPlan.PRO,
    )
    status: Mapped[TenantStatus] = mapped_column(
        pg_enum(TenantStatus, name="tenant_status"),
        nullable=False,
        default=TenantStatus.ACTIVE,
    )
    market: Mapped[str | None] = mapped_column(String(8), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    business_hours: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    owner_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    owner_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cost_alert_threshold_usd_per_day: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("40.00"),
        server_default="40.00",
    )
    # Block P (migration 0017). When true, ``promote_agent_config``
    # rejects unless there's a passing :class:`EvalRun` for the
    # candidate version. False keeps the legacy "promote freely"
    # behaviour so existing tenants are unaffected.
    eval_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    # Migration 0018 — owner backchannel. When ``backchannel_enabled`` is
    # false, ``operator.consult_owner`` refuses and the agent must fall
    # back to ``escalate.escalate_to_human``. SLA minutes drive the
    # timeout-sweep cron; offline_pause_after_timeouts is reserved for
    # Phase 2 (auto-pause on N consecutive timeouts).
    backchannel_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    backchannel_max_consultations_per_hour: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
        server_default="5",
    )
    backchannel_offline_pause_after_timeouts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        server_default="3",
    )
    backchannel_sla_high_min: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
        server_default="30",
    )
    backchannel_sla_normal_min: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=240,
        server_default="240",
    )
    backchannel_sla_low_min: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1440,
        server_default="1440",
    )

    # Migration 0021 — public AgendaPro link (ADR-017). The new public
    # browser MCP reads this URL to scrape availability and create
    # appointments; modify / cancel / get_appointments are not supported
    # via the public flow and escalate to the owner backchannel.
    # Optional — only set on tenants whose booking provider is AgendaPro.
    agendapro_public_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Tenant {self.slug}>"
