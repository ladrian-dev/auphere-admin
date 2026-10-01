"""Payment reviews — the business team confirms or rejects a payment (spec 025).

A ``PaymentReview`` is opened by the agent (``payments.request_review``)
when a customer sends a bank-transfer receipt or says they paid through the
store link. Each reviewer of the business gets a ``PaymentReviewNotice``:
the receipt and a message with two buttons whose ids carry the review's
``token``. The first tap resolves the review (see
``services/payment_reviews.py``). Both tables are tenant-scoped with forced
RLS (migration 0137).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TenantScopedMixin, TimestampMixin, UUIDPrimaryKey

REVIEW_PENDING = "pending"
REVIEW_CONFIRMED = "confirmed"
REVIEW_REJECTED = "rejected"
#: A link payment the store already shows as paid: the team is told, no buttons.
REVIEW_INFORMED = "informed"

METHOD_TRANSFER = "transfer"
METHOD_LINK = "link"

DELIVERY_INTERACTIVE = "interactive"
DELIVERY_UNDELIVERED = "undelivered"


class PaymentReview(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "payment_reviews"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=REVIEW_PENDING, server_default=REVIEW_PENDING
    )
    summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    order_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    order_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    receipt_message_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list, server_default=text("'{}'")
    )
    resolved_by_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resolved_by_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: ``True`` the answer to the customer was queued · ``False`` their 24h
    #: window was closed, nothing was sent · ``None`` not resolved yet.
    customer_notified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class PaymentReviewNotice(UUIDPrimaryKey, TenantScopedMixin, Base):
    __tablename__ = "payment_review_notices"

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_reviews.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewer_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewer_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    delivery: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    #: The outbound message with the buttons. ``messages`` is partitioned, so no FK.
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


__all__ = [
    "DELIVERY_INTERACTIVE",
    "DELIVERY_UNDELIVERED",
    "METHOD_LINK",
    "METHOD_TRANSFER",
    "REVIEW_CONFIRMED",
    "REVIEW_INFORMED",
    "REVIEW_PENDING",
    "REVIEW_REJECTED",
    "PaymentReview",
    "PaymentReviewNotice",
]
