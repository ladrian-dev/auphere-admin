"""Spec 005 · the membership catalogue and each partner's subscription state.

Two tables with two different jobs: ``membership_tiers`` says **what is sold**,
``partner_subscriptions`` says **where each partner stands**.

Not to be confused with ``billing.py``'s ``BillingPlan``, which predates this
and means something else entirely: the monthly price of the managed service
charged to a *tenant*. That is the Auphere ↔ partner's-client relationship.
This one is Auphere ↔ partner.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TimestampMixin

#: The four tier codes. Ours, never the provider's — see ``stripe_price_id``.
TIER_FREE = "free"
TIER_PRO = "pro"
TIER_TEAM = "team"
TIER_BUSINESS = "business"
TIER_CODES: frozenset[str] = frozenset({TIER_FREE, TIER_PRO, TIER_TEAM, TIER_BUSINESS})

#: The tier the published consumption multiple is relative to (research D9).
#: Free is not it: a multiple of the free tier would read "0.2x" on the paid
#: ones, which says nothing useful to someone choosing a plan.
BASE_PAID_TIER = TIER_PRO

#: ADR-037 D6. The ladder, in order. Nothing is archived on any of these
#: steps — the only thing that changes is whether the weekly pool refills.
STATE_CURRENT = "current"
STATE_PAYMENT_FAILED = "payment_failed"
STATE_UNPAID = "unpaid"
STATE_CANCELED = "canceled"
SUBSCRIPTION_STATES: frozenset[str] = frozenset(
    {STATE_CURRENT, STATE_PAYMENT_FAILED, STATE_UNPAID, STATE_CANCELED}
)


class MembershipTier(TimestampMixin, Base):
    """A tier of the catalogue. Platform-level: same for everyone, no RLS."""

    __tablename__ = "membership_tiers"
    __table_args__ = (
        CheckConstraint(
            "code IN ('free', 'pro', 'team', 'business')", name="ck_membership_tiers_code"
        ),
        CheckConstraint("monthly_price_cents >= 0", name="ck_membership_tiers_price_nonneg"),
        CheckConstraint("weekly_pool_tokens >= 0", name="ck_membership_tiers_pool_nonneg"),
        CheckConstraint("max_teammates >= 0", name="ck_membership_tiers_teammates_nonneg"),
        CheckConstraint("max_members >= 1", name="ck_membership_tiers_members_min"),
    )

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(40), nullable=False)
    monthly_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    #: INTERNAL. Never published to the partner — the plans screen shows the
    #: tier's hard caps and a computed multiple instead (research D9). These
    #: figures are provisional by product decision (ADR-037) and will be
    #: adjusted; a number printed on a pricing page turns every capacity
    #: adjustment into a visible cut or gift.
    weekly_pool_tokens: Mapped[int] = mapped_column(nullable=False)
    max_teammates: Mapped[int] = mapped_column(Integer, nullable=False)
    max_members: Mapped[int] = mapped_column(Integer, nullable=False)
    #: A replaceable REFERENCE, not a key. Nullable, no unique, no FK: the
    #: Stripe account will be migrated and this gets recreated (research D5).
    stripe_price_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    #: A retired tier stops being offered WITHOUT being deleted (principle IV).
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


class PartnerSubscription(TimestampMixin, Base):
    """Where a partner stands. One row per partner — history lives in the audit.

    ``partners.status`` is NOT this. It only admits ``active``/``suspended``
    and means whether the partner is operational; an unpaid partner is still
    operational for reading their own history.

    **A partner with no row is Free.** Absence is a valid state and is designed
    as one (principle V): nothing has to be seeded for the system to work.
    """

    __tablename__ = "partner_subscriptions"
    __table_args__ = (
        CheckConstraint(
            "state IN ('current', 'payment_failed', 'unpaid', 'canceled')",
            name="ck_partner_subscriptions_state",
        ),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tier_code: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("membership_tiers.code"),
        nullable=False,
        default=TIER_FREE,
        server_default=TIER_FREE,
    )
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=STATE_CURRENT, server_default=STATE_CURRENT
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: A downgrade scheduled for the end of the period (ADR-037 D7). Shown to
    #: the partner on purpose: one who already asked to downgrade and cannot
    #: see it asks again.
    pending_tier_code: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("membership_tiers.code"), nullable=True
    )
    #: References, not keys. See ``MembershipTier.stripe_price_id``.
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
