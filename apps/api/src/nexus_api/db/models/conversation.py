from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._enum import pg_enum
from nexus_api.db.models._mixins import TenantScopedMixin, TimestampMixin, UUIDPrimaryKey


class ConversationStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    ESCALATED = "escalated"


class MessageDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class MediaKind(str, enum.Enum):
    """WhatsApp native message media types. Mirrors Meta Cloud API ``type``
    field on inbound messages (``audio``, ``image``, ``document``, ``video``,
    ``sticker``) plus the structured non-media types we now persist
    (``location``, ``contacts``). Stored as a plain ``String(20)`` with a
    CHECK constraint rather than a PG enum so adding values in the future
    doesn't need an ALTER TYPE dance."""

    AUDIO = "audio"
    IMAGE = "image"
    DOCUMENT = "document"
    VIDEO = "video"
    STICKER = "sticker"
    LOCATION = "location"
    CONTACTS = "contacts"


class Customer(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "identifier", name="uq_customers_tenant_identifier"),
    )

    identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    kg_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kg_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )


class Conversation(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "conversations"

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[ConversationStatus] = mapped_column(
        pg_enum(ConversationStatus, name="conversation_status"),
        nullable=False,
        default=ConversationStatus.OPEN,
        index=True,
    )
    # Block M.3 — per-thread human takeover. When false, the dispatcher
    # persists the inbound message but does NOT invoke the pipeline; the
    # operator answers manually until they reactivate the agent. Defaults
    # to true so existing flows are unchanged.
    agent_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    # Migration 0018 — owner backchannel. ``awaiting_owner_response`` is a
    # persistent flag so that the pipeline knows a customer turn is paused
    # on an owner reply even after a worker restart between the
    # ``operator.consult_owner`` call and the owner's WhatsApp response.
    awaiting_owner_response: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    awaiting_owner_correlation_id: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )
    # Migration 0019 — last inbound timestamp so notification.send_text can
    # enforce the 24h customer-service window server-side. Backfilled from
    # MAX(messages.created_at WHERE direction='inbound') by 0019.
    last_inbound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Message(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    direction: Mapped[MessageDirection] = mapped_column(
        pg_enum(MessageDirection, name="message_direction"),
        nullable=False,
    )
    status: Mapped[MessageStatus] = mapped_column(
        pg_enum(MessageStatus, name="message_status"),
        nullable=False,
        default=MessageStatus.SENT,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    # Block F: outbound retry bookkeeping. Populated only by the outbound
    # dispatcher; inbound rows leave them untouched.
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Migration 0019 — WhatsApp native fields ─────────────────────────────
    # Durable Meta/YCloud wamid. UNIQUE index (partial: where not null) so
    # the webhook can ``ON CONFLICT DO NOTHING`` the dedupe. Populated for
    # both inbound (parsed from webhook) and outbound (recorded once YCloud
    # accepts the send).
    provider_message_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # Status callback lifecycle. ``status`` advances through SENT →
    # DELIVERED → READ on the receiver side; ``failed_at`` + ``failure_code``
    # capture a terminal failure from Meta (e.g. 131026 recipient unable,
    # 131047 outside 24h window, 132xxx template paused).
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # WhatsApp pricing.category (MARKETING / UTILITY / AUTHENTICATION /
    # SERVICE) returned in the ``conversation`` block of the delivered/read
    # callback, and ``conversation.id`` which uniquely identifies the
    # 24h-conversation window Meta opens for billing.
    pricing_category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    conversation_provider_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )

    # Media (audio/image/document/video/sticker) stored in S3 + metadata.
    # ``media_transcript`` is filled by the LLM multimodal pipeline (Whisper
    # for audio, Claude vision for images, OCR/PDF text for documents).
    media_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    media_s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    media_mime: Mapped[str | None] = mapped_column(String(120), nullable=True)
    media_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    media_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Reactions: ``reaction_emoji`` is the emoji the customer (or the agent)
    # placed, ``reaction_target_wamid`` is the wamid of the message being
    # reacted to. For outbound reactions we set both before sending; for
    # inbound the webhook fills them when ``type=reaction``.
    reaction_emoji: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reaction_target_wamid: Mapped[str | None] = mapped_column(String(160), nullable=True)

    # Quoted reply: when the customer (or the agent) cites a previous
    # message, this column holds the cited wamid. The pipeline uses it to
    # surface context that would otherwise be lost.
    context_message_id: Mapped[str | None] = mapped_column(String(160), nullable=True)


class WhatsAppOptOut(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    """Per-tenant per-recipient opt-out registry.

    Created when the inbound webhook detects a stop keyword (STOP, BAJA,
    UNSUBSCRIBE, CANCELAR), when the operator manually opts a number out,
    or when Meta returns a 131026 (recipient unable to receive). The
    outbound dispatcher consults this table BEFORE every send; an active
    opt-out blocks the send and parks the row as ``failed`` with
    ``failure_code='opted_out'``.

    ``opted_in_at`` is set if the user later re-engages or the operator
    manually re-opts them in — the row is preserved for audit.
    """

    __tablename__ = "whatsapp_opt_outs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "channel_id", "recipient_phone", name="uq_optout_tenant_channel_phone"
        ),
    )

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipient_phone: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    trigger_keyword: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_wamid: Mapped[str | None] = mapped_column(String(160), nullable=True)
    opted_out_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    opted_in_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WhatsAppTemplateStatus(UUIDPrimaryKey, TimestampMixin, Base):
    """WhatsApp template approval state mirror (NOT tenant-scoped).

    The ``message_template_status_update`` webhook from YCloud / Meta
    advances rows here through APPROVED → PAUSED → DISABLED or
    REJECTED → APPROVED. The ``notification.send_template`` tool reads
    the row before queueing; non-APPROVED templates are refused with a
    descriptive ToolError so the agent can fall back to free-form text.

    ``tenant_id`` is nullable because Auphere also maintains internal
    templates (owner backchannel) that belong to the BSP-level WABA, not
    a specific tenant. The lookup is by ``(waba_id, template_name,
    language)`` which is what Meta keys templates on.
    """

    __tablename__ = "whatsapp_template_status"
    __table_args__ = (
        UniqueConstraint(
            "waba_id", "template_name", "language", name="uq_tplstatus_waba_name_lang"
        ),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
    )
    waba_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    template_name: Mapped[str] = mapped_column(String(120), nullable=False)
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_event_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    last_event_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
