from __future__ import annotations

import enum
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Numeric, String
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

    def __repr__(self) -> str:
        return f"<Tenant {self.slug}>"
