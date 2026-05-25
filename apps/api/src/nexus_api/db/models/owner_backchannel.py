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
from nexus_api.db.types import FernetEncrypted as _FernetEncrypted

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

    # Migration 0042 (Phase 2) — fanout durability. Set by the worker
    # ``owner_fanout`` consumer once the pipeline re-invocation finished
    # successfully. NULL on rows that were answered but the fanout did
    # not complete (worker crash, Redis loss). The sweep cron
    # re-publishes such rows after ``owner_response_at + 5min``.
    result_applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


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
    # Migration 0038 — optionally pin this owner to a specific Auphere
    # backchannel number. NULL = the resolver picks the default channel
    # for the provider (with optional country_code matching). Useful for
    # multi-country setups (CL owner → +56 Auphere; AR owner → +54).
    auphere_channel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auphere_owner_channels.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Migration 0043 — Phase 2 TOFU. Set on the first ``/yes`` from the
    # registered phone after admin registration. Until this is non-NULL
    # the webhook refuses to drive consultations or apply slash side
    # effects — only an instructions reply goes out. Existing Phase 1
    # owners were backfilled to ``added_at`` by the migration so they
    # stay operational.
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# Allowed provider values for ``AuphereOwnerChannel.provider`` — kept as
# a tuple of literals (not a Postgres enum) to mirror the CHECK
# constraint without paying for enum-migration ceremony. Add a value
# here when a new BSP is plumbed.
AUPHERE_CHANNEL_PROVIDERS: tuple[str, ...] = ("ycloud", "meta")


class AuphereOwnerChannel(UUIDPrimaryKey, TimestampMixin, Base):
    """Global registry of Auphere backchannel numbers (migration 0038).

    Replaces the hardcoded ``settings.auphere_owner_phone`` /
    ``auphere_owner_number_id`` / ``auphere_owner_webhook_secret``
    trio. Each row represents one outbound number Auphere owns at a BSP
    (YCloud today, Meta when we migrate). Resolver order at runtime:

    1. If the ``OwnerPhoneIndex`` row carries an explicit
       ``auphere_channel_id`` → use that channel (when ``active``).
    2. Else use the row with ``is_default=true`` AND ``active=true``
       for the relevant provider — the partial unique index guarantees
       at most one default per provider.
    3. Else fall back to ``settings.auphere_owner_phone`` (Phase 1
       compatibility — empty registry behaves like the legacy
       single-number setup).

    ``webhook_secret_encrypted`` is optional: when NULL the webhook
    falls back to ``settings.ycloud_webhook_secret`` (or the
    provider-equivalent), which matches the operational reality where
    YCloud uses ONE HMAC secret per WABA — many phone numbers share it.
    Per-number secrets only kick in when an operator needs to rotate
    one number's secret without disrupting the others.
    """

    __tablename__ = "auphere_owner_channels"

    # ``id``, ``created_at`` and ``updated_at`` come from the mixins
    # (server-default UUID + ``now()``) — same pattern the rest of the
    # codebase uses, so tests + admin endpoints don't need to set them.
    phone_e164: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True
    )
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    country_code: Mapped[str | None] = mapped_column(
        String(2), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_phone_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
    # Fernet-encrypted at rest; NULL = use shared provider secret from
    # settings. See ``db.types.FernetEncrypted``.
    webhook_secret_encrypted: Mapped[bytes | None] = mapped_column(
        _FernetEncrypted(), nullable=True
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
