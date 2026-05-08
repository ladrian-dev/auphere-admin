from __future__ import annotations

import enum
from typing import Any

from sqlalchemy import String
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

    def __repr__(self) -> str:
        return f"<Tenant {self.slug}>"
