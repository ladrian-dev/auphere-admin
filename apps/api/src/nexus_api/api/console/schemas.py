"""Response/request models of the partner console (``/console/*``).

Kept apart from ``schemas/`` on purpose. Two rules are enforced by
construction here and pinned by ``tests/isolation/test_console_*``:

- **No internal identifiers of the tenant.** A partner speaks
  ``external_client_ref``; ``tenant_id`` never appears in a response.
- **No message bodies** (decision C8). Conversation models carry volume,
  state, timing and counts. There is no field that could hold the text
  of a message, a transcript, a tool payload or a takeover note.

Field names that would smell like content (``content``, ``text``,
``body``, ``transcript``, ``payload``, ``notes``, ``reason``,
``system_prompt``) are only allowed where the value is the partner's own
configuration (the agent prompt), never a customer's words.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ── principal ──────────────────────────────────────────────────────────


class PartnerBrief(BaseModel):
    slug: str
    name: str
    status: str


class QuotaOut(BaseModel):
    """Client quota (CP-06): what the console shows next to "New client"."""

    max_clients: int
    used_clients: int
    remaining_clients: int
    max_channels_per_client: int


class MeOut(BaseModel):
    user_id: str
    email: str
    display_name: str | None
    role: str
    permissions: list[str]
    membership_id: uuid.UUID
    partner: PartnerBrief
    quota: QuotaOut


# ── clients ────────────────────────────────────────────────────────────

ClientStatus = Literal["provisioning", "active", "paused", "archived"]


class ClientSummaryOut(BaseModel):
    """One row of the client list. Cheap fields only."""

    external_client_ref: str
    name: str
    status: str
    timezone: str
    created_at: datetime
    updated_at: datetime


class ClientHealthOut(BaseModel):
    whatsapp_connected: bool
    display_phone_number: str | None = None
    agent_version: int | None = None
    agent_configured: bool
    ready: bool
    missing: list[str] = Field(default_factory=list)


class ClientOut(ClientSummaryOut):
    """Client detail: summary + health."""

    health: ClientHealthOut


class ClientPageOut(BaseModel):
    items: list[ClientSummaryOut]
    total: int
    limit: int
    offset: int


class ClientCreateIn(BaseModel):
    """Same shape the partner API accepts, minus anything that could name a
    tenant. ``external_client_ref`` is the partner's own id for the client;
    the console suggests one from the name and the partner may edit it."""

    model_config = ConfigDict(extra="forbid")

    external_client_ref: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._:-]+$")
    name: str = Field(min_length=1, max_length=255)
    timezone: str = Field(default="UTC", max_length=64)
    placeholders: dict[str, Any] | None = None
    # CP-10: optionally stage a DRAFT agent (version 1) from this seed right
    # after provisioning — same as calling ``.../agent/from-seed`` next.
    # Ignored when the partner's blueprint already seeded the agent.
    seed_template: str | None = Field(default=None, max_length=80, pattern=r"^[a-z0-9_]+$")


class ClientCreateOut(BaseModel):
    external_client_ref: str
    status: str
    agent_status: str
    whatsapp_connected: bool
    quota: QuotaOut


class ClientUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    timezone: str | None = Field(default=None, max_length=64)


class ClientStatusIn(BaseModel):
    """Lifecycle transitions the partner may drive: suspend (``paused``),
    reactivate (``active``), archive (``archived``). ``provisioning`` is
    system-owned and never settable."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "paused", "archived"]


class ClientDeleteIn(BaseModel):
    """Deleting is irreversible: the partner types the client's name."""

    model_config = ConfigDict(extra="forbid")

    confirm_name: str = Field(min_length=1, max_length=255)


# ── agents ─────────────────────────────────────────────────────────────


class AgentVersionOut(BaseModel):
    """An agent configuration version, as the partner sees it. The
    prompt is the partner's own asset (they wrote it), so it is here;
    what is NOT here is any runtime secret or customer content."""

    version: int
    status: str
    system_prompt: str
    tools: list[str]
    seed_template_ref: str | None
    created_by: str | None
    created_at: datetime
    promoted_at: datetime | None
    promoted_by: str | None


class AgentBundleOut(BaseModel):
    active_version: int | None
    versions: list[AgentVersionOut]


class AgentDraftIn(BaseModel):
    """Stage a new version. Tools must exist in the catalogue (the service
    validates); channels/policies are inherited from the active version
    unless given."""

    model_config = ConfigDict(extra="forbid")

    system_prompt: str = Field(min_length=1, max_length=200_000)
    tools: list[str] | None = None


# ── channels ───────────────────────────────────────────────────────────


class ChannelOut(BaseModel):
    """Channel metadata. Never the credential (``config_encrypted``) and
    never provider tokens — only what a partner needs to see state."""

    id: uuid.UUID
    type: str
    provider: str
    provider_identifier: str
    status: str
    role: str | None = None
    last_health_check_at: datetime | None = None
    created_at: datetime


# ── conversations (metadata only — C8) ─────────────────────────────────


class ConversationMetaOut(BaseModel):
    """What a partner may know about a conversation: that it exists, on
    which channel, its state and its shape. Never what was said."""

    id: uuid.UUID
    channel_id: uuid.UUID
    channel_type: str | None = None
    status: str
    agent_active: bool
    started_at: datetime
    last_activity_at: datetime
    turns: int
    inbound_messages: int
    outbound_messages: int
    failed_messages: int
    escalated: bool
    avg_latency_ms: int | None = None
    duration_seconds: int | None = None


class ConversationPageOut(BaseModel):
    items: list[ConversationMetaOut]
    total: int
    limit: int
    offset: int


class ConversationStatsOut(BaseModel):
    """Aggregate for a period. Volume, states, errors, latency."""

    since: datetime
    until: datetime
    conversations: int
    open: int
    escalated: int
    closed: int
    turns: int
    failed_messages: int
    avg_latency_ms: int | None = None


# ── usage (units, never our cost — C9) ─────────────────────────────────


class UsageBucketOut(BaseModel):
    external_client_ref: str | None
    client_name: str | None
    meter: str
    source: str
    quantity: float
    billable_qty: float
    records: int


class UsageReportOut(BaseModel):
    since: datetime
    until: datetime
    buckets: list[UsageBucketOut]
    totals_by_meter: dict[str, float]
    total_records: int


# ── audit ──────────────────────────────────────────────────────────────


class AuditEntryOut(BaseModel):
    """One row a human can read: who did what to which client, when."""

    id: uuid.UUID
    at: datetime
    actor: str
    action: str
    target: str
    external_client_ref: str | None
    client_name: str | None
    summary: str


class AuditPageOut(BaseModel):
    items: list[AuditEntryOut]
    next_cursor: str | None


# ── team ───────────────────────────────────────────────────────────────

RoleLiteral = Literal["owner", "admin", "builder", "analyst", "billing"]


class MemberOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    role: str
    status: str
    accepted_at: datetime | None
    created_at: datetime
    is_you: bool = False


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    created_at: datetime


class InvitationCreatedOut(InvitationOut):
    """Returned once, to the inviter: the accept link. E-mail delivery is
    best-effort; the link lets the inviter share it by hand."""

    accept_path: str
    email_sent: bool


class TeamOut(BaseModel):
    members: list[MemberOut]
    invitations: list[InvitationOut]


class InviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    role: RoleLiteral


class MemberRoleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: RoleLiteral


class MemberStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "suspended"]


# ── invitations (pre-membership, service token) ────────────────────────


class InvitationLookupOut(BaseModel):
    partner_name: str
    email: str
    role: str
    expires_at: datetime


class InvitationAcceptOut(BaseModel):
    """Aceptar una invitación crea la cuenta Y abre sesión (auto-login):
    la persona ya demostró quién es al recibir el enlace y acaba de elegir
    contraseña, así que mandarla a la pantalla de login sería ceremonia.
    ``token`` es el mismo token opaco que devuelve ``/console/auth/login``."""

    membership_id: uuid.UUID
    partner: PartnerBrief
    role: str
    token: str
    expires_at: datetime


# ── api keys ───────────────────────────────────────────────────────────

# ``widget_sessions`` is deliberately absent: the embedded widget is out of
# scope (the embed service was retired from the repo on 2026-08-04 and the
# integration story is API/MCP). ``messages_send`` needs a tenant-bound key.
KeyScopeLiteral = Literal["provision", "broadcasts"]


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    prefix_snippet: str
    scopes: list[str]
    allowed_origins: list[str]
    last_used_at: datetime | None
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    grace_expires_at: datetime | None


class ApiKeyCreatedOut(ApiKeyOut):
    """The plaintext, exactly once."""

    plaintext: str


class ApiKeyCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["live", "test"] = "live"
    # Partner-level scopes only. ``messages_send`` needs a tenant-bound key
    # and is created from the client page (later package).
    scopes: list[KeyScopeLiteral] = Field(
        default_factory=lambda: list[KeyScopeLiteral](["provision", "broadcasts"])
    )
    allowed_origins: list[str] = Field(default_factory=list, max_length=20)
    expires_at: datetime | None = None


class ApiKeyRotateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grace_hours: int = Field(default=24, ge=0, le=336)


# ── billing (read) ─────────────────────────────────────────────────────


class ReceiptSummaryOut(BaseModel):
    invoice_id: uuid.UUID
    period_year: int
    period_month: int
    total_usd: float
    currency: str
    status: str
    issued_at: datetime | None
    due_date: date


class BillingOut(BaseModel):
    billing_email: str | None
    contact_email: str | None
    receipts: list[ReceiptSummaryOut]
