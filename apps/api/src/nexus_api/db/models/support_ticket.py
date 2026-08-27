"""Partner support tickets (F4). FORCE RLS by ``app.partner_id``.

Opened from the existing ``POST /console/support/tickets``. Admin inbox
lists them unscoped via ``app.is_admin``. A partner session never sees
another partner's rows.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import UUIDPrimaryKey

TICKET_STATUSES: tuple[str, ...] = ("open", "pending", "closed")
TICKET_CATEGORIES: tuple[str, ...] = ("help", "capability")
EVENT_KINDS: tuple[str, ...] = ("open", "status")
STATUS_OPEN = "open"
EVENT_OPEN = "open"
EVENT_STATUS = "status"


class SupportTicket(UUIDPrimaryKey, Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint("category IN ('help','capability')", name="ck_tickets_category"),
        CheckConstraint("status IN ('open','pending','closed')", name="ck_tickets_status"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="CASCADE", name="fk_tickets_partner"),
        nullable=False,
        index=True,
    )
    ticket_ref: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    topic: Mapped[str] = mapped_column(String(60), nullable=False)
    client_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    need: Mapped[str] = mapped_column(Text, nullable=False)
    checked: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    alternative: Mapped[str | None] = mapped_column(Text, nullable=True)
    bridge: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sla: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_OPEN)
    opened_by: Mapped[str] = mapped_column(String(255), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )


class SupportTicketEvent(UUIDPrimaryKey, Base):
    __tablename__ = "ticket_events"
    __table_args__ = (CheckConstraint("kind IN ('open','status')", name="ck_ticket_events_kind"),)

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tickets.id", ondelete="CASCADE", name="fk_ticket_events_ticket"),
        nullable=False,
        index=True,
    )
    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="CASCADE", name="fk_ticket_events_partner"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


__all__ = [
    "EVENT_KINDS",
    "EVENT_OPEN",
    "EVENT_STATUS",
    "STATUS_OPEN",
    "TICKET_CATEGORIES",
    "TICKET_STATUSES",
    "SupportTicket",
    "SupportTicketEvent",
]
