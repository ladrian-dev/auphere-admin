"""Partner platform models (migration 0047, ADR-028).

A *partner* is a SaaS company that embeds ``@auphere/embed`` in its own
web app so that its end clients (each one = a Nexus tenant) can send
WhatsApp template broadcasts from their own number.

These are PLATFORM tables — not tenant-scoped, no RLS — following the
same trust model as ``tenants``: they are only reachable from the
``/v1/partners/*`` surface (secret API key), the embed JWT verifier and
the admin panel. ``partner_tenants`` is the isolation boundary: the
``(partner_id, external_client_ref) → tenant_id`` mapping is the ONLY
place where a tenant_id is ever chosen for a widget session, and it is
keyed by the partner's identity (proven by its API key), never by
browser input.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TimestampMixin, UUIDPrimaryKey


class PartnerStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class ApiKeyType(str, enum.Enum):
    LIVE = "live"
    TEST = "test"


class ApiKeyScope(str, enum.Enum):
    """What a key is allowed to do. Stored as plain strings in
    ``api_keys.scopes`` — this enum is the vocabulary, not a DB type.

    ``PROVISION``, ``WIDGET_SESSIONS`` and ``BROADCASTS`` are
    partner-level: they act across the partner's clients.
    ``MESSAGES_SEND`` is tenant-level and only meaningful on a key that
    carries ``tenant_id`` (see migration 0052) — sending needs one
    unambiguous WhatsApp channel to send from.

    ``PROVISION`` and ``BROADCASTS`` are deliberately separate: creating
    clients and configuring who administers them is an integration-time
    capability, while messaging a client's end customers is an operational
    one with real-world reach. A partner can hold a key for each, so a
    leaked provisioning key cannot message anyone's debtors.
    """

    PROVISION = "provision"
    WIDGET_SESSIONS = "widget_sessions"
    MESSAGES_SEND = "messages_send"
    BROADCASTS = "broadcasts"


#: Scopes that require the key to be bound to a single tenant.
TENANT_SCOPED_API_KEY_SCOPES = frozenset({ApiKeyScope.MESSAGES_SEND.value})


class Partner(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "partners"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended')",
            name="ck_partners_status",
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Public, non-secret identifier. The embed app passes it as ``?p=<slug>``
    # so the CSP middleware can resolve the frame-ancestors allow-list.
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PartnerStatus.ACTIVE.value, server_default="active"
    )
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Migration 0054 — where this agency's monthly invoice is sent. NULL
    # until billing is set up for the partner.
    billing_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Hard cap on recipients per broadcast. Default 250 — Meta starts new
    # WABAs at the 250 unique-conversations/24h tier; blasting past it
    # degrades the client's number quality rating.
    broadcast_recipient_cap: Mapped[int] = mapped_column(
        Integer, nullable=False, default=250, server_default="250"
    )
    rate_limit_mint_per_min: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, server_default="60"
    )
    rate_limit_embed_per_min: Mapped[int] = mapped_column(
        Integer, nullable=False, default=600, server_default="600"
    )
    # Auto-provisioning blueprint (migration 0050). A partner with a
    # ``default_seed_template`` gets a rendered + promoted agent_config v1
    # for every client it provisions; ``default_connector_slug`` names the
    # ``api_key`` connector installed with the credentials sent at
    # provision time. NULL = assisted onboarding (operator does it).
    default_seed_template: Mapped[str | None] = mapped_column(String(80), nullable=True)
    default_connector_slug: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Flip the tenant PROVISIONING → ACTIVE when its WhatsApp signup
    # completes and an active agent_config exists. False = operator
    # reviews and activates by hand.
    auto_activate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # Migration 0080 — per-partner switch for the partner console
    # (PLAN-CONSOLE-V1 rule 4). False = members exist but cannot enter;
    # Auphere flips it per partner once the pilot is ready.
    console_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Migration 0081 — provisioning quota (PLAN-CONSOLE-V1 CP-06). Checked
    # BEFORE anything is created, under a row lock on the partner.
    max_clients: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")
    max_channels_per_client: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2, server_default="2"
    )
    # Operator-only note ("raised to 30 on 2026-09-01, contract X").
    quota_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Migration 0082 — playground spend cap (CP-16): LLM tokens (in + out)
    # the partner's console playground may burn per UTC calendar month,
    # across all its clients and members. Tokens, not USD (C9). Checked
    # BEFORE every turn; ``qa_cap_notes`` is operator-only.
    qa_monthly_token_cap: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=2_000_000, server_default="2000000"
    )
    qa_cap_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Migration 0086 — activation metric (CP-29): first moment the partner
    # had an ACTIVE client with a published agent. NULL = not yet.
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Migration 0087 — usage alerts (CP-24). Monthly cap of channel messages
    # across all the partner's clients (NULL = no cap; v1 only WARNS at 80 %
    # and 100 %, never cuts service), e-mail recipients, and the switch.
    usage_cap_messages_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_alert_recipients: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    usage_alerts_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Partner {self.slug}>"


class PartnerApiKey(UUIDPrimaryKey, Base):
    """Secret API key (``ak_live_…``) — stored as SHA-256 only.

    The key is high-entropy (160 bits) so a fast unsalted hash is the
    correct storage (bcrypt/argon2 would add per-request cost without a
    security win — there is nothing to brute-force). The plaintext is
    shown exactly once at creation/rotation time.

    Rotation keeps the old key alive until ``grace_expires_at`` so the
    partner can swap secrets without a hard cutover. Revocation
    (``revoked_at``) is immediate and fail-closed: the embed JWT
    verifier re-checks the key row on every request, so even unexpired
    session tokens die with the key.
    """

    __tablename__ = "api_keys"
    __table_args__ = (
        CheckConstraint("type IN ('live', 'test')", name="ck_api_keys_type"),
        CheckConstraint(
            "tenant_id IS NULL OR NOT ('provision' = ANY(scopes))",
            name="ck_api_keys_tenant_scope_no_provision",
        ),
        Index("ix_api_keys_partner_revoked", "partner_id", "revoked_at"),
        Index(
            "ix_api_keys_tenant_revoked",
            "tenant_id",
            "revoked_at",
            postgresql_where=text("tenant_id IS NOT NULL"),
        ),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Set → the key IS this tenant and resolves without an
    # ``external_client_ref`` in the request. NULL → partner-scoped key,
    # tenant resolved per request via ``partner_tenants`` as before.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(
        String(10), nullable=False, default=ApiKeyType.LIVE.value, server_default="live"
    )
    # First chars of the plaintext (``ak_live_4f9c…``) for display and
    # support ("which key is this?") — never enough to reconstruct it.
    prefix_snippet: Mapped[str] = mapped_column(String(16), nullable=False)
    # SHA-256 hex of the full plaintext key. UNIQUE → O(1) lookup on auth.
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)),
        nullable=False,
        server_default=text("ARRAY['provision','widget_sessions']::varchar[]"),
    )
    # Origins allowed to embed the widget for sessions minted with this
    # key. Feeds the CSP frame-ancestors header AND the iframe-side
    # postMessage origin check (via the session JWT claims).
    allowed_origins: Mapped[list[str]] = mapped_column(
        ARRAY(String(255)),
        nullable=False,
        server_default=text("ARRAY[]::varchar[]"),
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set by rotation: the revoked key keeps authenticating until this
    # instant so the partner can deploy the replacement without downtime.
    grace_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PartnerTenant(Base):
    """The isolation boundary: partner's client ref ↔ Nexus tenant.

    ``external_client_ref`` is the partner's own id for its client —
    opaque to us. A widget session can only ever be minted for a tenant
    reachable through this table under the authenticated partner's id,
    which makes cross-tenant escalation structurally impossible.
    """

    __tablename__ = "partner_tenants"
    __table_args__ = (
        UniqueConstraint("partner_id", "tenant_id", name="uq_partner_tenants_partner_tenant"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="CASCADE"),
        primary_key=True,
    )
    external_client_ref: Mapped[str] = mapped_column(String(255), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class EmbedAuditLog(Base):
    """Append-only audit trail for the partner/embed surface.

    Everything security-relevant lands here: key lifecycle, session
    mints (with jti), rejected origins, accepted broadcasts. The DB role
    only gets SELECT + INSERT — no UPDATE/DELETE — so rows can't be
    silently rewritten.
    """

    __tablename__ = "embed_audit_log"
    __table_args__ = (
        Index("ix_embed_audit_partner_created", "partner_id", "created_at"),
        Index("ix_embed_audit_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    partner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="SET NULL"),
        nullable=True,
    )
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # e.g. key.created / key.rotated / key.revoked / session.minted /
    # session.rejected / client.provisioned / broadcast.accepted /
    # origin.rejected
    event: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    origin: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # jti of the session token involved, when applicable — lets us chase
    # every action a specific minted token performed.
    jti: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
