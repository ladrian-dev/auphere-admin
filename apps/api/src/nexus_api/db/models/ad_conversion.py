"""Clics de anuncio, medición por número y cola de eventos de conversión — spec 076.

- ``CustomerAdReferral``: un clic de anuncio o de publicación de un contacto (el
  ``referral`` del mensaje de WhatsApp). El ``ctwa_clid`` se borra a los 90 días;
  nunca sale en logs ni en respuestas de la API.
- ``ChannelAdMeasurement``: si un número envía sus resultados a Meta y a qué
  conjunto de datos. Vive aparte de las credenciales para que una reconexión no
  lo borre. ``meta_dataset_id`` no se llama ``dataset_id`` porque ese nombre ya
  es de los conjuntos de evaluación.
- ``AdConversionEvent``: la cola que vacía el despachador de ``egress``. No
  guarda el teléfono, ni cifrado: se lee y se cifra al enviar.

Garantía 1: RLS forzada y FK compuestas ``(tenant_id, x)``; una FK de una sola
columna no pasa por la RLS. Garantía 8: el contacto de un clic lo fija el
servidor con el mensaje entrante, y un evento solo usa clics de su contacto y de
su número. La migración es la 0241.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TenantScopedMixin, TimestampMixin, UUIDPrimaryKey

#: Los dos orígenes que manda Meta en ``referral.source_type``.
SOURCE_TYPES: Final = ("ad", "post")
#: Los eventos que Auphere envía. Meta admite más; estos son los de la spec.
EVENT_NAMES: Final = ("Purchase", "LeadSubmitted", "OrderCreated", "OrderCanceled")
EVENT_STATUSES: Final = ("pending", "sent", "failed", "discarded")
SOURCE_KINDS: Final = ("reservation", "woo_order")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class CustomerAdReferral(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "customer_ad_referrals"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "provider_message_id", name="uq_customer_ad_referrals_message"
        ),
        UniqueConstraint("tenant_id", "id", name="uq_customer_ad_referrals_tenant_id"),
        CheckConstraint(
            _in("source_type", SOURCE_TYPES), name="ck_customer_ad_referrals_source_type"
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_customer_ad_referrals_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_customer_ad_referrals_customer",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_customer_ad_referrals_conversation",
            ondelete="SET NULL (conversation_id)",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["channels.tenant_id", "channels.id"],
            name="fk_customer_ad_referrals_channel",
            ondelete="CASCADE",
        ),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider_message_id: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(String(8), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    headline: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ad_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ctwa_clid: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    clicked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChannelAdMeasurement(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "channel_ad_measurement"
    __table_args__ = (
        UniqueConstraint("tenant_id", "channel_id", name="uq_channel_ad_measurement_channel"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_channel_ad_measurement_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["channels.tenant_id", "channels.id"],
            name="fk_channel_ad_measurement_channel",
            ondelete="CASCADE",
        ),
    )

    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    meta_dataset_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enabled_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AdConversionEvent(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "ad_conversion_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "event_id", name="uq_ad_conversion_events_event_id"),
        UniqueConstraint("tenant_id", "id", name="uq_ad_conversion_events_tenant_id"),
        CheckConstraint(
            _in("source_kind", SOURCE_KINDS), name="ck_ad_conversion_events_source_kind"
        ),
        CheckConstraint(_in("event_name", EVENT_NAMES), name="ck_ad_conversion_events_event_name"),
        CheckConstraint(_in("status", EVENT_STATUSES), name="ck_ad_conversion_events_status"),
        ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_ad_conversion_events_tenant", ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["channels.tenant_id", "channels.id"],
            name="fk_ad_conversion_events_channel",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_ad_conversion_events_customer",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "referral_id"],
            ["customer_ad_referrals.tenant_id", "customer_ad_referrals.id"],
            name="fk_ad_conversion_events_referral",
            ondelete="SET NULL (referral_id)",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "cancels_event_id"],
            ["ad_conversion_events.tenant_id", "ad_conversion_events.id"],
            name="fk_ad_conversion_events_cancels",
            ondelete="CASCADE",
        ),
    )

    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    referral_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    cancels_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_name: Mapped[str] = mapped_column(String(24), nullable=False)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="pending", server_default=text("'pending'")
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
