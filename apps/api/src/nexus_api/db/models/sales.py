"""Agent-attributed sales — WooCommerce orders closed via WhatsApp.

Tenant-scoped (RLS), unlike the platform-level billing tables: a sale is
the tenant's own commercial activity, same trust model as ``messages``.
Feeds the commission a partner is billed (Barber Supply → Facelad, 2.5%).

Money is stored in the store's own currency (``gross_amount`` +
``currency``), captured from WooCommerce verbatim. Conversion to the
USD invoice is a later, explicit step — see migration 0056.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TenantScopedMixin, TimestampMixin, UUIDPrimaryKey


class AgentSale(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    """One WhatsApp-attributed WooCommerce order, with its commission.

    Written by the daily WooCommerce poll (upsert on ``wc_order_id``), so
    a refund or status change on a later poll updates the same row rather
    than adding a second.
    """

    __tablename__ = "agent_sales"

    wc_order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    commission_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    wc_status: Mapped[str] = mapped_column(String(20), nullable=False)
    date_paid: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set once billed, so the commission run never double-charges a sale.
    invoice_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoice_lines.id", ondelete="SET NULL"), nullable=True
    )
    source_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    @property
    def is_paid(self) -> bool:
        return self.date_paid is not None
