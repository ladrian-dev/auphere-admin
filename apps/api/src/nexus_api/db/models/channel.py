from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._enum import pg_enum
from nexus_api.db.models._mixins import TenantScopedMixin, TimestampMixin, UUIDPrimaryKey
from nexus_api.db.types import FernetEncrypted

# The Playground's own ``web`` channel (see ``api/qa.py``). It is a real
# ``channels`` row so QA conversations have somewhere to live, but it never
# carries customer traffic: onboarding, home figures and the conversations
# lane must not count it, or the screen says "channel connected" and
# "first conversation" after a dry run.
QA_PLAYGROUND_PROVIDER = "qa_playground"


class ChannelType(str, enum.Enum):
    WHATSAPP = "whatsapp"
    INSTAGRAM = "instagram"
    TELEGRAM = "telegram"
    EMAIL = "email"
    WEB = "web"
    # Migration 0059 — TikTok Business Messaging. ``provider="tiktok"``,
    # ``provider_identifier`` is the Business Account ``business_id``.
    TIKTOK = "tiktok"
    # Migration 0205 — spec 049. Instagram uses ``provider="meta_instagram"``
    # (the value above, there since 0001); Messenger ``provider="meta_messenger"``
    # and the Page id as ``provider_identifier``.
    MESSENGER = "messenger"


class ChannelStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"


class Channel(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "channels"
    __table_args__ = (
        # Spec 021: dos canales **vivos** no comparten número en toda la
        # plataforma; uno vivo y uno desvinculado sí. Antes era una
        # restricción sin condición, y un número desvinculado quedaba
        # ocupado para siempre: el mismo cliente podía reactivarlo, pero
        # ningún otro —ni de otro partner— podía conectarlo. La fila se
        # conserva (historial, reconectar); lo que deja de hacer es
        # ocupar sitio.
        Index(
            "uq_channels_live_number",
            "type",
            "provider_identifier",
            unique=True,
            postgresql_where=text("status <> 'disconnected'"),
        ),
    )

    type: Mapped[ChannelType] = mapped_column(
        pg_enum(ChannelType, name="channel_type"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    # Spec 030: the agent that answers on this number. NULL = the tenant's
    # principal agent (and the value of send-only lines and the Playground).
    # In the database the key is ``(tenant_id, agent_id)`` (0155): a number
    # can only point at an agent of its own client.
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
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
    # Spec 047 (migración 0191): the channel's own configuration (requisito 32).
    problem_reason: Mapped[str | None] = mapped_column(String(24), nullable=True)
    audience_mode: Mapped[str] = mapped_column(
        String(12), nullable=False, default="unset", server_default="unset"
    )
    config_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    coexistence: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    paused_by_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    paused_by_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    paused_origin: Mapped[str | None] = mapped_column(String(16), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChannelAudienceNumber(UUIDPrimaryKey, Base):
    """Spec 047 (0191): a test number («Solo mi equipo») or an exception («A todos»)."""

    __tablename__ = "channel_audience_numbers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_channel_audience_numbers_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "channel_id",
            "kind",
            "phone_e164",
            name="uq_channel_audience_numbers_number",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["channels.tenant_id", "channels.id"],
            name="fk_channel_audience_numbers_channel",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class ChannelEscalationRecipient(UUIDPrimaryKey, Base):
    """Spec 047 (0191): who a hand-over on this number tells, and how (requisito 33)."""

    __tablename__ = "channel_escalation_recipients"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_channel_escalation_recipients_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["channels.tenant_id", "channels.id"],
            name="fk_channel_escalation_recipients_channel",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    via: Mapped[str] = mapped_column(String(12), nullable=False)
    phone_e164: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    client_user_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class ChannelConfigChange(UUIDPrimaryKey, Base):
    """Spec 047 (0191): the history of a channel's configuration, with undo."""

    __tablename__ = "channel_config_changes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_channel_config_changes_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["channels.tenant_id", "channels.id"],
            name="fk_channel_config_changes_channel",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    actor: Mapped[str] = mapped_column(String(160), nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    undo_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WhatsappLoginBetaCountry(Base):
    """Spec 047 (0191), plataforma: dónde Meta habilitó la beta «WhatsApp login»."""

    __tablename__ = "whatsapp_login_beta_countries"

    country: Mapped[str] = mapped_column(String(2), primary_key=True)
    enabled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    enabled_by: Mapped[str] = mapped_column(String(160), nullable=False)


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
