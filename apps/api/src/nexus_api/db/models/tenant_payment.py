"""A client's monthly fee, collected outside the payment provider.

Auphere's own collection records. RLS like ``invoices``: enabled, not forced —
the runtime sees one client's rows, the platform path sees every client's.

Since 2026-10-20 (owner) a payment of a partner's client also credits the
partner's recharged balance (``credit_manual``), once; voiding it takes it
back. It still grants no tier and moves no client's state.

One live payment per client and month (partial unique index). A payment
recorded by mistake is voided, never deleted, and the month is free again.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import UUIDPrimaryKey

#: How the money arrived. Closed on purpose: a free-text method turns
#: «transferencia», «Transf.» and «banco» into three different things.
PAYMENT_METHODS: frozenset[str] = frozenset(
    {"transfer", "cash", "zelle", "paypal", "crypto", "other"}
)


#: Payments recorded from this moment on credit the partner's balance
#: (migration 0163). Earlier rows stay a record: the owner chose not to credit
#: them retroactively (2026-10-20).
CREDIT_SINCE = datetime(2026, 10, 20, tzinfo=UTC)


class TenantPayment(UUIDPrimaryKey, Base):
    """One month's fee of one client, as received by hand."""

    __tablename__ = "tenant_payments"
    __table_args__ = (
        CheckConstraint("period_month BETWEEN 1 AND 12", name="ck_tenant_payments_period_month"),
        CheckConstraint("amount_cents > 0", name="ck_tenant_payments_amount_positive"),
        CheckConstraint(
            "method IN ('transfer', 'cash', 'zelle', 'paypal', 'crypto', 'other')",
            name="ck_tenant_payments_method",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="USD")
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    #: The bank's operation number, the Zelle confirmation — whatever lets
    #: someone find this payment in the account statement later.
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: The day the money arrived, which is not the day it was written down.
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recorded_by: Mapped[str] = mapped_column(String(120), nullable=False)
    #: Owner, 2026-10-20: what this payment credited to the partner's balance.
    #: NULL on rows recorded before the change, or when the client has no
    #: partner (a direct client of Auphere has no balance to credit).
    credited_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
