"""ORM models for the owner backchannel — ``owner_consultations`` and
``owner_phone_index``.

Mirror of migration ``0018``. The two tables play distinct roles:

- :class:`OwnerConsultation` is a tenant-scoped log of every consultation
  the agent (or a cron/admin actor) asked. RLS-protected; every read goes
  through ``app.tenant_id``.
- :class:`OwnerPhoneIndex` is a global lookup of ``phone_e164 → tenant_id``.
  Same role as the ``tenants`` table — readable without a tenant scope so
  the inbound webhook can decide which tenant to switch into BEFORE
  applying RLS.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TenantScopedMixin, TimestampMixin, UUIDPrimaryKey

# String literals (not enums) match the migration's CHECK constraints
# verbatim. Importing from these constants in repos/services keeps the
# textual values DRY without paying for a Postgres enum migration.

OWNER_CONSULTATION_STATUSES: tuple[str, ...] = (
    "pending",
    "sent",
    "answered",
    "timed_out",
    "cancelled",
)

OWNER_CONSULTATION_URGENCIES: tuple[str, ...] = ("low", "normal", "high")

OWNER_CONSULTATION_EXPECTED_REPLY_KINDS: tuple[str, ...] = (
    "free_text",
    "yes_no",
    "action_done",
)

OWNER_COMMAND_KINDS: tuple[str, ...] = (
    "free_text",
    "yes",
    "no",
    "handoff",
    "pause",
    "done",
    "help",
)


class OwnerConsultation(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "owner_consultations"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    correlation_id: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)

    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    context_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    urgency: Mapped[str] = mapped_column(String(10), nullable=False)
    expected_reply_kind: Mapped[str] = mapped_column(String(20), nullable=False)

    template_name: Mapped[str] = mapped_column(String(120), nullable=False)
    template_params_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    ycloud_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    owner_response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_response_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    owner_command_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)

    timed_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[str] = mapped_column(String(60), nullable=False)


class OwnerPhoneIndex(Base):
    """Global ``phone_e164 → tenant_id`` lookup.

    NOT a :class:`TenantScopedMixin` user — this table is read BEFORE the
    inbound webhook knows which tenant to scope into. The UNIQUE primary
    key on ``phone_e164`` enforces that a single phone belongs to exactly
    one tenant; a second tenant trying to register the same phone fails
    fast (admin must resolve manually).
    """

    __tablename__ = "owner_phone_index"

    phone_e164: Mapped[str] = mapped_column(String(20), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
