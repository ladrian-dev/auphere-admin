"""El teléfono de una persona de cliente y sus avisos — spec 031.

Tres tablas de tenant, con RLS forzada (data-model §0158, §0160, §0161):

* ``client_phones``: cada teléfono donde una persona de cliente ha entrado. Es
  identidad: la comprobación de la credencial, el canje y el registro del
  destino la leen sin el rol ``nexus_app`` (research D3), igual que
  ``resolve_client_principal`` lee las membresías. Todo lo demás la lee bajo
  la RLS de su cliente.
* ``client_push_events``: el outbox. Un hecho que puede producir avisos, escrito
  en la misma transacción que el hecho (R8.5). **Sin contenido**: referencias.
* ``client_push_deliveries``: un aviso a un teléfono, creado al repartir.

Nada se borra: un teléfono revocado se queda como constancia (constitución §IV).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import UUIDPrimaryKey

#: Los tipos de aviso (spec 031 R8.1; los de Reservas, spec 043). El orden es el
#: de Ajustes. Los de Reservas solo llegan a clientes con el módulo.
NOTICE_KINDS: tuple[str, ...] = (
    "inbox.waiting",
    "inbox.message_for_you",
    "client.balance",
    "reservas.agent_change",
    "reservas.cancelled_today",
    "reservas.waitlist_accepted",
)
#: Los que nacen encendidos en un teléfono nuevo: «alguien de la lista de
#: espera aceptó» nace apagado (diseño).
DEFAULT_NOTICE_KINDS: tuple[str, ...] = tuple(
    k for k in NOTICE_KINDS if k != "reservas.waitlist_accepted"
)

PHONE_PLATFORMS: frozenset[str] = frozenset({"ios", "android"})

#: Por qué se cerró un teléfono. Cerrado a propósito: la auditoría lo traduce.
REVOKE_REASONS: tuple[str, ...] = (
    "signed_out",
    "closed_by_person",
    "closed_by_auphere",
    "access_disabled",
    "member_removed",
    "password_reset",
    "abandoned",
    "refresh_reused",
)

DELIVERY_SKIP_REASONS: tuple[str, ...] = (
    "phone_revoked",
    "kind_disabled",
    "no_push_token",
    "module_missing",
    "no_longer_true",
    "token_owned_elsewhere",
    # Spec 045 (R5.3): fuera del horario del negocio, con el silencio puesto.
    "quiet_hours",
)


def _in(values: tuple[str, ...] | frozenset[str]) -> str:
    return ", ".join(f"'{v}'" for v in sorted(values))


class ClientPhone(UUIDPrimaryKey, Base):
    __tablename__ = "client_phones"
    __table_args__ = (
        CheckConstraint(f"platform IN ({_in(PHONE_PLATFORMS)})", name="ck_client_phones_platform"),
        CheckConstraint(
            "push_provider IS NULL OR push_provider IN ('apns', 'fcm')",
            name="ck_client_phones_push_provider",
        ),
        CheckConstraint(
            "apns_environment IS NULL OR apns_environment IN ('sandbox', 'production')",
            name="ck_client_phones_apns_environment",
        ),
        CheckConstraint(
            f"notice_kinds <@ ARRAY[{_in(NOTICE_KINDS)}]::varchar[]",
            name="ck_client_phones_notice_kinds",
        ),
        CheckConstraint("locale IN ('es', 'en')", name="ck_client_phones_locale"),
        CheckConstraint(
            f"revoked_reason IS NULL OR revoked_reason IN ({_in(REVOKE_REASONS)})",
            name="ck_client_phones_revoked_reason",
        ),
        CheckConstraint("length(display_name) <= 80", name="ck_client_phones_display_name"),
        UniqueConstraint("tenant_id", "id", name="uq_client_phones_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "client_membership_id"],
            ["client_memberships.tenant_id", "client_memberships.id"],
            name="fk_client_phones_membership",
            ondelete="CASCADE",
        ),
        Index(
            "uq_client_phones_install_live",
            "install_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "ix_client_phones_principal_live",
            "tenant_id",
            "principal_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "ix_client_phones_push_token_live",
            "push_token",
            postgresql_where=text("revoked_at IS NULL AND push_token IS NOT NULL"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    client_membership_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    #: La cuenta (``console_auth.principals``), por valor como en la membresía.
    principal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    platform: Mapped[str] = mapped_column(String(10), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    install_id: Mapped[str] = mapped_column(String(64), nullable=False)
    app_version: Mapped[str] = mapped_column(String(32), nullable=False)
    refresh_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    refresh_prev_hash: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    refresh_rotated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    credential_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    push_provider: Mapped[str | None] = mapped_column(String(8), nullable=True)
    push_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    push_token_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    apns_environment: Mapped[str | None] = mapped_column(String(12), nullable=True)
    notice_kinds: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)),
        nullable=False,
        default=lambda: list(DEFAULT_NOTICE_KINDS),
        server_default=text(
            "ARRAY['inbox.waiting','inbox.message_for_you','client.balance',"
            "'reservas.agent_change','reservas.cancelled_today']::varchar[]"
        ),
    )
    locale: Mapped[str] = mapped_column(String(2), nullable=False, default="es")
    #: Spec 045 (R5): fuera del horario del negocio no salen los avisos que no
    #: son urgentes. Por teléfono, encendido por defecto.
    quiet_outside_hours: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(24), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(320), nullable=True)

    @property
    def active(self) -> bool:
        return self.revoked_at is None


class ClientPushEvent(UUIDPrimaryKey, Base):
    __tablename__ = "client_push_events"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_in(NOTICE_KINDS)})", name="ck_client_push_events_kind"),
        CheckConstraint(
            "status IN ('pending', 'fanned_out', 'failed')", name="ck_client_push_events_status"
        ),
        UniqueConstraint("tenant_id", "id", name="uq_client_push_events_tenant_id_id"),
        UniqueConstraint("tenant_id", "dedupe_key", name="uq_client_push_events_dedupe"),
        Index(
            "ix_client_push_events_pending",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Spec 043: los avisos de Reservas nombran la reserva (sin clave foránea:
    #: el aviso es una cola, y la reserva puede cancelarse antes de repartir).
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    notification_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    #: Solo para ``inbox.message_for_you``: la persona que tiene el control.
    target_principal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="pending", server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    fanned_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClientPushDelivery(UUIDPrimaryKey, Base):
    __tablename__ = "client_push_deliveries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'sent', 'failed', 'skipped')",
            name="ck_client_push_deliveries_status",
        ),
        CheckConstraint(
            f"skip_reason IS NULL OR skip_reason IN ({_in(DELIVERY_SKIP_REASONS)})",
            name="ck_client_push_deliveries_skip_reason",
        ),
        UniqueConstraint(
            "tenant_id", "event_id", "phone_id", name="uq_client_push_deliveries_event_phone"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "event_id"],
            ["client_push_events.tenant_id", "client_push_events.id"],
            name="fk_client_push_deliveries_event",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "phone_id"],
            ["client_phones.tenant_id", "client_phones.id"],
            name="fk_client_push_deliveries_phone",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    phone_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    skip_reason: Mapped[str | None] = mapped_column(String(24), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = [
    "DEFAULT_NOTICE_KINDS",
    "DELIVERY_SKIP_REASONS",
    "NOTICE_KINDS",
    "PHONE_PLATFORMS",
    "REVOKE_REASONS",
    "ClientPhone",
    "ClientPushDelivery",
    "ClientPushEvent",
]
