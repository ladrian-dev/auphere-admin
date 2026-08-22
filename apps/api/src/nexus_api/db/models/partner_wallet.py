"""Libro Fase 3: wallet, asignación por tenant y ledger.

RLS por ``partner_id`` (migración 0094). FORCE. El cliente nunca envía
``partner_id``; lo pone el principal de consola o el mapa partner_tenants.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TimestampMixin, UUIDPrimaryKey

BUCKET_INCLUDED = "included"
BUCKET_PURCHASED = "purchased"
LEDGER_BUCKETS: frozenset[str] = frozenset({BUCKET_INCLUDED, BUCKET_PURCHASED})


class PartnerWallet(TimestampMixin, Base):
    """Un libro por partner. ``included`` caduca; ``purchased`` no."""

    __tablename__ = "partner_wallets"
    __table_args__ = (
        CheckConstraint("included_remaining >= 0", name="ck_partner_wallets_included_nonneg"),
        CheckConstraint("purchased_remaining >= 0", name="ck_partner_wallets_purchased_nonneg"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="CASCADE"),
        primary_key=True,
    )
    included_remaining: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    included_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    purchased_remaining: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class PartnerAllocation(UUIDPrimaryKey, TimestampMixin, Base):
    """Tope de un tenant dentro del wallet del partner.

    La suma de ``cap`` no puede superar included efectivo + purchased.
    """

    __tablename__ = "partner_allocations"
    __table_args__ = (
        UniqueConstraint("partner_id", "tenant_id", name="uq_partner_allocations_partner_tenant"),
        CheckConstraint("cap >= 0", name="ck_partner_allocations_cap_nonneg"),
        CheckConstraint(
            "remaining >= 0 AND remaining <= cap",
            name="ck_partner_allocations_remaining_range",
        ),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    cap: Mapped[int] = mapped_column(BigInteger, nullable=False)
    remaining: Mapped[int] = mapped_column(BigInteger, nullable=False)


class UsageLedger(UUIDPrimaryKey, Base):
    """Asiento de débito. ``idempotency_key`` UNIQUE: el mismo turno no dobla."""

    __tablename__ = "usage_ledger"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_usage_ledger_idempotency"),
        CheckConstraint("qty > 0", name="ck_usage_ledger_qty_pos"),
        CheckConstraint("bucket IN ('included', 'purchased')", name="ck_usage_ledger_bucket"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
    )
    qty: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bucket: Mapped[str] = mapped_column(String(16), nullable=False)
    usage_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    companion_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    fx: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
