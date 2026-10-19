"""A partner's card on file and its automatic charges (spec 041).

Both tables are partner-scoped with FORCE RLS (``app.partner_id``), like the
wallet. The card is Stripe's: only its ids, brand, last four digits and expiry
are kept here — never the number, which never reaches Auphere.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import UUIDPrimaryKey

BILLING_MANUAL = "manual"
BILLING_AUTO_RECHARGE = "auto_recharge"
BILLING_POSTPAID = "postpaid"
BILLING_MODES: tuple[str, ...] = (BILLING_MANUAL, BILLING_AUTO_RECHARGE, BILLING_POSTPAID)

CHARGE_AUTO_RECHARGE = "auto_recharge"
CHARGE_POSTPAID = "postpaid"
CHARGE_PENDING = "pending"
#: The bank asked for authentication (3D Secure): the partner confirms it on
#: Stripe's page (``action_url``). Not a decline.
CHARGE_ACTION_REQUIRED = "action_required"
CHARGE_PAID = "paid"
CHARGE_FAILED = "failed"

#: After this many failed automatic charges in a row, they stop until the
#: partner fixes the card — a declined card is not retried forever.
MAX_FAILED_ATTEMPTS = 3
#: The smallest automatic recharge, the same floor as a manual purchase.
MIN_RECHARGE_CENTS = 500


class PartnerBilling(Base):
    __tablename__ = "partner_billing"

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partners.id", ondelete="CASCADE"), primary_key=True
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_method_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    card_brand: Mapped[str | None] = mapped_column(String(24), nullable=True)
    card_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    card_exp_month: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    card_exp_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    card_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default=BILLING_MANUAL)
    recharge_threshold_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recharge_amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    #: Why automatic charges are stopped (``card_declined``…); ``None`` = running.
    paused_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: The postpaid line Auphere granted (credits). The wallet's ``credit_limit``
    #: equals it, except while frozen.
    granted_credit_limit: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    #: When a failed postpaid charge froze the line at what was already owed.
    credit_frozen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @property
    def has_card(self) -> bool:
        return bool(self.stripe_customer_id and self.payment_method_id)


class PartnerCharge(UUIDPrimaryKey, Base):
    __tablename__ = "partner_charges"

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partners.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[str | None] = mapped_column(String(7), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=CHARGE_PENDING)
    stripe_invoice_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Stripe's page where the partner confirms a charge that needs it.
    action_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
