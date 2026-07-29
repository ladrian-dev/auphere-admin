from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._enum import pg_enum
from nexus_api.db.models._mixins import TenantScopedMixin, TimestampMixin, UUIDPrimaryKey
from nexus_api.db.types import FernetEncrypted


class ChannelType(str, enum.Enum):
    WHATSAPP = "whatsapp"
    INSTAGRAM = "instagram"
    TELEGRAM = "telegram"
    EMAIL = "email"
    WEB = "web"
    # Migration 0059 — TikTok Business Messaging. ``provider="tiktok"``,
    # ``provider_identifier`` is the Business Account ``business_id``.
    TIKTOK = "tiktok"


class ChannelStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"


class Channel(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "channels"
    __table_args__ = (
        UniqueConstraint("type", "provider_identifier", name="uq_channels_type_provider_id"),
    )

    type: Mapped[ChannelType] = mapped_column(
        pg_enum(ChannelType, name="channel_type"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    config_encrypted: Mapped[bytes | None] = mapped_column(FernetEncrypted, nullable=True)
    status: Mapped[ChannelStatus] = mapped_column(
        pg_enum(ChannelStatus, name="channel_status"),
        nullable=False,
        default=ChannelStatus.ACTIVE,
    )
    # Migration 0019 — channel health snapshots. ``last_health_check_at`` is
    # set by the WhatsApp quality_rating refresh cron; if Meta degrades a
    # WABA to YELLOW/RED the cron persists the snapshot here so the operator
    # panel can surface the alert without a config rewrite. ``last_provider_
    # synced_at`` mirrors the provider-confirmed metadata fetch (display name,
    # verified status, phone identifier).
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_provider_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TenantCredentials(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "tenant_credentials"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "integration", name="uq_tenant_credentials_tenant_integration"
        ),
    )

    integration: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_payload: Mapped[bytes] = mapped_column(FernetEncrypted, nullable=False)
    # Bloque E: si el health check del context Browserbase falla y el
    # re-login automático tampoco logra recuperarlo, se setea a true y se
    # escala al operador. ``booking.create_appointment`` chequea esto antes
    # de delegar a ``agendapro.*`` — si está true, cae al camino local.
    needs_reauth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
