"""Spec 005 · the log of notices received from the payment provider.

Platform-level, no RLS: this is our integration trail, not a partner's data,
and a row may have no partner resolved at all.

The ``provider_event_id`` unique constraint **is** the idempotency. It is
decided at the door, by the database, not by the background job: two
simultaneous deliveries of the same event — which happen — mean one wins the
INSERT and the other gets a 200 having credited nothing.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base

STATUS_RECEIVED = "received"
STATUS_PROCESSED = "processed"
STATUS_FAILED = "failed"
STATUS_IGNORED = "ignored"
EVENT_STATUSES: frozenset[str] = frozenset(
    {STATUS_RECEIVED, STATUS_PROCESSED, STATUS_FAILED, STATUS_IGNORED}
)


class BillingEvent(Base):
    """One notice from the provider, recorded BEFORE it is acted on."""

    __tablename__ = "billing_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('received', 'processed', 'failed', 'ignored')",
            name="ck_billing_events_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_event_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    #: The SECOND idempotency anchor. ``checkout.session.completed`` and
    #: ``checkout.session.async_payment_succeeded`` are different events that
    #: can both arrive for one purchase, so the unique above does not stop
    #: them: what stops them is checking whether that session was fulfilled.
    checkout_session_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    #: No foreign key on purpose: a notice about money from an account we do
    #: not recognise must still be recordable. An orphan row gets investigated;
    #: a lost notice leaves nothing to investigate.
    partner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=STATUS_RECEIVED, server_default=STATUS_RECEIVED
    )
    #: Never carries card data. The provider does not send it; it is filtered
    #: on the way in anyway, and an isolation test checks that it stays out.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
