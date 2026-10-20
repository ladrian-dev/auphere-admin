"""Libro Fase 3: wallet, asignación por tenant y ledger.

RLS por ``partner_id`` (migración 0094). FORCE. El cliente nunca envía
``partner_id``; lo pone el principal de consola o el mapa partner_tenants.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
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

# Spec 033: what each ledger entry is. Spend is ``debit`` and nothing else.
KIND_DEBIT = "debit"
KIND_CREDIT_ADMIN = "credit_admin"
KIND_CREDIT_STRIPE = "credit_stripe"
KIND_EXPIRY = "expiry"
KIND_ALLOCATION_LEGACY = "allocation_legacy"
#: Written once by migration 0158: the difference between the stored balance
#: and the book at that moment (balances written by hand before 2026-09-08).
KIND_OPENING_CREDIT = "opening_credit"
KIND_OPENING_DEBIT = "opening_debit"
#: Owner, 2026-10-20: a partner's payment received outside Stripe and
#: recorded in the Admin credits its balance; voiding it takes that back.
KIND_CREDIT_MANUAL = "credit_manual"
KIND_CREDIT_REVERSAL = "credit_reversal"
LEDGER_KINDS: tuple[str, ...] = (
    KIND_DEBIT,
    KIND_CREDIT_ADMIN,
    KIND_CREDIT_STRIPE,
    KIND_EXPIRY,
    KIND_ALLOCATION_LEGACY,
    KIND_OPENING_CREDIT,
    KIND_OPENING_DEBIT,
    KIND_CREDIT_MANUAL,
    KIND_CREDIT_REVERSAL,
)
#: Kinds that add to the purchased balance.
CREDIT_KINDS: tuple[str, ...] = (KIND_CREDIT_ADMIN, KIND_CREDIT_STRIPE, KIND_CREDIT_MANUAL)
LEDGER_BUCKETS: frozenset[str] = frozenset({BUCKET_INCLUDED, BUCKET_PURCHASED})


class PartnerWallet(TimestampMixin, Base):
    """Un libro por partner. ``included`` caduca; ``purchased`` no."""

    __tablename__ = "partner_wallets"
    __table_args__ = (
        CheckConstraint("included_remaining >= 0", name="ck_partner_wallets_included_nonneg"),
        # Spec 041: the purchased balance may go as far below zero as the
        # partner's postpaid credit line — and the database is what stops it.
        CheckConstraint(
            "purchased_remaining >= -credit_limit", name="ck_partner_wallets_purchased_floor"
        ),
        CheckConstraint("credit_limit >= 0", name="ck_partner_wallets_credit_limit_nonneg"),
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
    #: Spec 041: credits of postpaid line Auphere granted; 0 = prepaid only.
    credit_limit: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    #: Spec 005 (research D8). ``NULL`` while the account is alive — that is
    #: the invariant "purchased credit does not expire while the account
    #: lives", written so it CANNOT be violated by accident: there is no date
    #: to compare against. Set to now + 12 months on cancellation; back to
    #: ``NULL`` if the partner comes back.
    #:
    #: Not to be confused with ``included_expires_at`` above, which is weekly.
    #: Two pockets, two clocks (ADR-037 D1).
    purchased_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


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
    #: Spec 033 (R6.1): the calendar month (UTC, first day) ``remaining``
    #: belongs to. The cap refills when the month changes, once.
    period_month: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        server_default=text("(date_trunc('month', timezone('UTC', now())))::date"),
    )


class UsageLedger(UUIDPrimaryKey, Base):
    """Asiento de débito. ``idempotency_key`` UNIQUE: el mismo turno no dobla."""

    __tablename__ = "usage_ledger"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_usage_ledger_idempotency"),
        CheckConstraint("qty > 0", name="ck_usage_ledger_qty_pos"),
        CheckConstraint("bucket IN ('included', 'purchased')", name="ck_usage_ledger_bucket"),
        CheckConstraint(
            "kind IN ('debit', 'credit_admin', 'credit_stripe', 'expiry', 'allocation_legacy', "
            "'opening_credit', 'opening_debit')",
            name="ck_usage_ledger_kind",
        ),
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
    #: Spec 033 (R2.1). No default: every writer says what the entry is.
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    usage_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Spec 030: the agent the debit belongs to (spend per agent).
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    companion_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    fx: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
