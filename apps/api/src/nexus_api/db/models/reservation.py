"""Reservas — spec 043 (migración 0172).

Un módulo, dos formas de reservar: **Servicios** (una cita con una persona del
equipo) y **Aforo** (sitio para N personas a una hora, sin mesas). El modo lo
elige el admin; el negocio ajusta el resto.

Todas las tablas son por cliente, con RLS FORCE, y **toda referencia entre
tablas de cliente es una clave foránea compuesta** ``(tenant_id, x_id)``: la
comprobación de una FK no pasa por la RLS, así que una de una sola columna
dejaría que una reserva del cliente A apuntara a una persona del equipo del B.

Los estados y orígenes son ``String`` con su ``CHECK`` (como ``client_phones``):
el vocabulario es el del contrato (``specs/043-reservas/contracts/lite-api.md``).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TenantScopedMixin, TimestampMixin, UUIDPrimaryKey

MODES: tuple[str, ...] = ("services", "capacity")
#: Spec 047 (0183): how a service's price is said.
PRICE_KINDS: tuple[str, ...] = ("none", "free", "amount")
CAPACITY_KINDS: tuple[str, ...] = ("restaurant", "bar", "classes", "tours", "rooms", "spa")
CONFIRM_WHEN: tuple[str, ...] = ("24h", "same_day_12", "3h")
STATUSES: tuple[str, ...] = ("pending", "confirmed", "arrived", "done", "noshow", "cancelled")
#: Ocupan sitio y bloquean huecos.
LIVE_STATUSES: tuple[str, ...] = ("pending", "confirmed", "arrived")
ORIGINS: tuple[str, ...] = ("agent", "person", "waitlist", "walkin")
CHANNELS: tuple[str, ...] = ("whatsapp", "phone", "in_person")
ACTOR_KINDS: tuple[str, ...] = ("agent", "person", "system", "customer")
CANCELLED_BY: tuple[str, ...] = ("customer", "business", "system")
WAITLIST_STATUSES: tuple[str, ...] = ("waiting", "offered", "accepted", "removed", "expired")
JOINED_BY: tuple[str, ...] = ("agent", "person", "in_person")
OFFER_STATUSES: tuple[str, ...] = ("running", "filled", "empty", "stopped")
CANDIDATE_STATUSES: tuple[str, ...] = (
    "queued",
    "waiting",
    "noreply",
    "accepted",
    "late_taken",
    "late_won",
    "skipped",
    "stopped",
)
OUTBOX_KINDS: tuple[str, ...] = (
    "confirmation",
    "ask_confirmation",
    "reminder",
    "moved",
    "cancelled",
    "offer",
    "offer_won",
    "offer_lost",
)
OUTBOX_STATUSES: tuple[str, ...] = ("pending", "sent", "failed", "skipped")
EVENT_KINDS: tuple[str, ...] = (
    "created",
    "confirmed",
    "confirmation_requested",
    "reminder_sent",
    "replied_yes",
    "replied_no",
    "moved",
    "cancelled",
    "arrived",
    "noshow",
    "undone",
    "done",
    "waitlist_joined",
    "waitlist_accepted",
    "notified",
    "notify_failed",
    "released",
)


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _tenant_fk(column: str, table: str, name: str, *, ondelete: str | None = None) -> Any:
    return ForeignKeyConstraint(
        ["tenant_id", column],
        [f"{table}.tenant_id", f"{table}.id"],
        name=name,
        ondelete=ondelete,
    )


class ReservationSettings(Base):
    __tablename__ = "reservation_settings"
    __table_args__ = (
        CheckConstraint(f"mode IN ({_in(MODES)})", name="ck_reservation_settings_mode"),
        CheckConstraint(
            f"capacity_kind IS NULL OR capacity_kind IN ({_in(CAPACITY_KINDS)})",
            name="ck_reservation_settings_kind",
        ),
        CheckConstraint(
            f"confirm_when IN ({_in(CONFIRM_WHEN)})", name="ck_reservation_settings_confirm_when"
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    capacity_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    slot_step_minutes: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=30)
    waitlist_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    waitlist_lead_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    agent_min_notice_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    agent_max_days_ahead: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    reminder_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    confirm_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    confirm_when: Mapped[str] = mapped_column(String(16), nullable=False, default="24h")
    release_unconfirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    seats: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stay_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_party: Mapped[int | None] = mapped_column(Integer, nullable=True)
    walkin_hold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schedule: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )


class ReservationStaff(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "reservation_staff"
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_reservation_staff_tenant_id"),)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    hours: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReservationService(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "reservation_services"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_reservation_services_tenant_id"),
        # Spec 047 (0183): a service may not be bookable (a product, a menu) and
        # then has no duration; a bookable one runs 5 to 480 minutes in steps of 5.
        CheckConstraint(
            "(bookable AND duration_minutes IS NOT NULL "
            "AND duration_minutes BETWEEN 5 AND 480 AND duration_minutes % 5 = 0) "
            "OR (NOT bookable AND duration_minutes IS NULL)",
            name="ck_reservation_services_duration",
        ),
        CheckConstraint(
            "price_minor IS NULL OR price_minor >= 0", name="ck_reservation_services_price"
        ),
        CheckConstraint(
            f"price_kind IN ({_in(PRICE_KINDS)}) "
            "AND (price_kind <> 'amount' OR price_minor IS NOT NULL)",
            name="ck_reservation_services_price_kind",
        ),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: ``None`` only when the service is not bookable (spec 047).
    duration_minutes: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    bookable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    #: ``none`` (no price said), ``free`` or ``amount`` (``price_minor``).
    price_kind: Mapped[str] = mapped_column(
        String(8), nullable=False, default="none", server_default="none"
    )
    price_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CLP")
    all_staff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReservationServiceStaff(Base):
    __tablename__ = "reservation_service_staff"
    __table_args__ = (
        _tenant_fk("service_id", "reservation_services", "fk_rss_service", ondelete="CASCADE"),
        _tenant_fk("staff_id", "reservation_staff", "fk_rss_staff", ondelete="CASCADE"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    service_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    staff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)


class Reservation(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "reservations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_reservations_tenant_id"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_reservations_idempotency"),
        CheckConstraint(f"mode IN ({_in(MODES)})", name="ck_reservations_mode"),
        CheckConstraint(f"status IN ({_in(STATUSES)})", name="ck_reservations_status"),
        CheckConstraint(f"origin IN ({_in(ORIGINS)})", name="ck_reservations_origin"),
        CheckConstraint(f"channel IN ({_in(CHANNELS)})", name="ck_reservations_channel"),
        CheckConstraint(
            f"created_by_kind IN ({_in(ACTOR_KINDS)})", name="ck_reservations_created_by"
        ),
        CheckConstraint(
            f"cancelled_by IS NULL OR cancelled_by IN ({_in(CANCELLED_BY)})",
            name="ck_reservations_cancelled_by",
        ),
        CheckConstraint("ends_at > starts_at", name="ck_reservations_span"),
        CheckConstraint("party_size >= 1", name="ck_reservations_party"),
        CheckConstraint(
            "mode <> 'services' OR (staff_id IS NOT NULL AND service_id IS NOT NULL)",
            name="ck_reservations_services_refs",
        ),
        _tenant_fk("staff_id", "reservation_staff", "fk_reservations_staff"),
        _tenant_fk("service_id", "reservation_services", "fk_reservations_service"),
        # Lo que la retención de datos puede borrar no bloquea: se suelta la
        # columna, no ``tenant_id`` (Postgres 15+: ``SET NULL (col)``).
        _tenant_fk(
            "customer_id",
            "customers",
            "fk_reservations_customer",
            ondelete="SET NULL (customer_id)",
        ),
        _tenant_fk(
            "conversation_id",
            "conversations",
            "fk_reservations_conversation",
            ondelete="SET NULL (conversation_id)",
        ),
        _tenant_fk("agent_id", "agents", "fk_reservations_agent", ondelete="SET NULL (agent_id)"),
        Index("ix_reservations_tenant_starts", "tenant_id", "starts_at"),
        Index(
            "ix_reservations_staff_live",
            "tenant_id",
            "staff_id",
            "starts_at",
            postgresql_where=text("status IN ('pending', 'confirmed')"),
        ),
        Index("ix_reservations_customer", "tenant_id", "customer_id", "starts_at"),
    )

    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    party_size: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    service_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    service_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    price_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    wants_earlier: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    any_staff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cancel_cause: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confirmation_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: P3 — el evento «Ocupado» escrito en el Google Calendar de la persona.
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ReservationEvent(UUIDPrimaryKey, TenantScopedMixin, Base):
    __tablename__ = "reservation_events"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_in(EVENT_KINDS)})", name="ck_reservation_events_kind"),
        CheckConstraint(f"actor_kind IN ({_in(ACTOR_KINDS)})", name="ck_reservation_events_actor"),
        _tenant_fk(
            "reservation_id",
            "reservations",
            "fk_reservation_events_reservation",
            ondelete="CASCADE",
        ),
        Index("ix_reservation_events_reservation", "tenant_id", "reservation_id", "created_at"),
    )

    reservation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class ReservationBlock(UUIDPrimaryKey, TenantScopedMixin, Base):
    __tablename__ = "reservation_blocks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_reservation_blocks_tenant_id"),
        CheckConstraint("until_time >= from_time", name="ck_reservation_blocks_span"),
        CheckConstraint("length(label) BETWEEN 1 AND 120", name="ck_reservation_blocks_label"),
        Index("ix_reservation_blocks_day", "tenant_id", "day"),
    )

    day: Mapped[date] = mapped_column(Date, nullable=False)
    from_time: Mapped[time] = mapped_column(Time, nullable=False)
    until_time: Mapped[time] = mapped_column(Time, nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    created_by_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class ReservationWaitlist(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "reservation_waitlist"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_reservation_waitlist_tenant_id"),
        CheckConstraint(f"mode IN ({_in(MODES)})", name="ck_reservation_waitlist_mode"),
        CheckConstraint(
            f"status IN ({_in(WAITLIST_STATUSES)})", name="ck_reservation_waitlist_status"
        ),
        CheckConstraint(
            f"joined_by_kind IN ({_in(JOINED_BY)})", name="ck_reservation_waitlist_joined"
        ),
        _tenant_fk(
            "customer_id",
            "customers",
            "fk_reservation_waitlist_customer",
            ondelete="SET NULL (customer_id)",
        ),
        _tenant_fk("service_id", "reservation_services", "fk_reservation_waitlist_service"),
        _tenant_fk("staff_id", "reservation_staff", "fk_reservation_waitlist_staff"),
        _tenant_fk(
            "reservation_id",
            "reservations",
            "fk_reservation_waitlist_reservation",
            ondelete="CASCADE",
        ),
    )

    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="waiting")
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    party_size: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    desired_day: Mapped[date | None] = mapped_column(Date, nullable=True)
    desired_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    desired_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    service_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    joined_by_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    joined_by_name: Mapped[str | None] = mapped_column(String(120), nullable=True)


class ReservationOffer(UUIDPrimaryKey, TenantScopedMixin, Base):
    __tablename__ = "reservation_offers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_reservation_offers_tenant_id"),
        CheckConstraint(f"mode IN ({_in(MODES)})", name="ck_reservation_offers_mode"),
        CheckConstraint(f"status IN ({_in(OFFER_STATUSES)})", name="ck_reservation_offers_status"),
        _tenant_fk("staff_id", "reservation_staff", "fk_reservation_offers_staff"),
        _tenant_fk("service_id", "reservation_services", "fk_reservation_offers_service"),
        _tenant_fk(
            "source_reservation_id",
            "reservations",
            "fk_reservation_offers_source",
            ondelete="SET NULL (source_reservation_id)",
        ),
        _tenant_fk(
            "filled_reservation_id",
            "reservations",
            "fk_reservation_offers_filled",
            ondelete="SET NULL (filled_reservation_id)",
        ),
        Index(
            "uq_reservation_offers_running",
            "tenant_id",
            "starts_at",
            text("COALESCE(staff_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )

    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    service_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    seats: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    source_reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    cancelled_by_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    window_minutes: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    max_candidates: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    filled_reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReservationOfferCandidate(Base):
    __tablename__ = "reservation_offer_candidates"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_in(CANDIDATE_STATUSES)})", name="ck_reservation_candidates_status"
        ),
        _tenant_fk(
            "offer_id", "reservation_offers", "fk_reservation_candidates_offer", ondelete="CASCADE"
        ),
        _tenant_fk(
            "waitlist_id",
            "reservation_waitlist",
            "fk_reservation_candidates_entry",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    offer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    waitlist_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReservationOutbox(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "reservation_outbox"
    __table_args__ = (
        UniqueConstraint("tenant_id", "dedupe_key", name="uq_reservation_outbox_dedupe"),
        CheckConstraint(f"kind IN ({_in(OUTBOX_KINDS)})", name="ck_reservation_outbox_kind"),
        CheckConstraint(f"status IN ({_in(OUTBOX_STATUSES)})", name="ck_reservation_outbox_status"),
        _tenant_fk(
            "reservation_id",
            "reservations",
            "fk_reservation_outbox_reservation",
            ondelete="CASCADE",
        ),
        _tenant_fk(
            "offer_id", "reservation_offers", "fk_reservation_outbox_offer", ondelete="CASCADE"
        ),
        _tenant_fk(
            "waitlist_id", "reservation_waitlist", "fk_reservation_outbox_entry", ondelete="CASCADE"
        ),
        Index(
            "ix_reservation_outbox_due",
            "tenant_id",
            "next_attempt_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    reservation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    offer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    waitlist_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    skip_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)


__all__ = [
    "CAPACITY_KINDS",
    "LIVE_STATUSES",
    "MODES",
    "STATUSES",
    "Reservation",
    "ReservationBlock",
    "ReservationEvent",
    "ReservationOffer",
    "ReservationOfferCandidate",
    "ReservationOutbox",
    "ReservationService",
    "ReservationServiceStaff",
    "ReservationSettings",
    "ReservationStaff",
    "ReservationWaitlist",
]
