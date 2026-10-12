"""A client's monthly fee, collected outside the payment provider.

Auphere's own collection records. RLS like ``invoices``: enabled, not forced —
the runtime sees one client's rows, the platform path sees every client's.

A row is a **record and nothing else**. It grants no tier, credits no balance
and moves nobody's state — writing one never touches the service.

One live payment per client and month (partial unique index). A payment
recorded by mistake is voided, never deleted, and the month is free again.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

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
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
