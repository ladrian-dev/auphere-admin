"""Pydantic schemas for the partner platform (ADR-028).

Two families:
- ``/v1/partners/*`` (public, secret-key auth) — responses NEVER expose
  internal tenant ids; the partner only ever sees its own
  ``external_client_ref``.
- ``/admin/partners/*`` (operator panel) — full detail, including the
  one-time plaintext key at creation/rotation.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, field_validator

#: The scope vocabulary, mirrored from ``ApiKeyScope`` so the admin
#: surface rejects unknown values at the edge instead of storing them.
ApiKeyScopeLiteral = Literal["provision", "widget_sessions", "messages_send", "broadcasts"]

# ── /v1/partners (public, server-to-server) ─────────────────────────────────


class ClientAgentIn(BaseModel):
    """Inputs for the partner's agent blueprint (``default_seed_template``).

    ``placeholders`` uses the seed template's dotted keys — e.g.
    ``{"agent.name": "Sofía", "policies.admin_access.admin_phones":
    ["+58424…"]}``. ``tenant.name`` / ``tenant.timezone`` are always taken
    from the tenant row; sending them here has no effect.
    """

    model_config = ConfigDict(extra="forbid")

    placeholders: dict[str, Any] = Field(default_factory=dict)


class ClientConnectorIn(BaseModel):
    """Credentials for the partner's connector blueprint
    (``default_connector_slug``). ``credentials`` carries the secret
    fields (Fernet-encrypted at rest); ``meta`` carries non-secret
    routing info (e.g. ``business_uuid``)."""

    model_config = ConfigDict(extra="forbid")

    credentials: dict[str, str] = Field(min_length=1)
    meta: dict[str, Any] = Field(default_factory=dict)


class ClientProvisionIn(BaseModel):
    external_client_ref: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    timezone: str = Field(default="UTC", max_length=64)
    agent: ClientAgentIn | None = None
    connector: ClientConnectorIn | None = None


class WhatsAppStatusOut(BaseModel):
    status: Literal["connected", "not_connected"]
    display_phone_number: str | None = None


class ClientAgentOut(BaseModel):
    status: Literal["provisioned", "already_provisioned", "not_configured"]


class ClientProvisionOut(BaseModel):
    external_client_ref: str
    status: Literal["provisioned"]
    whatsapp: WhatsAppStatusOut
    agent: ClientAgentOut
    connector_connected: bool = False


class WidgetSessionIn(BaseModel):
    external_client_ref: str = Field(min_length=1, max_length=255)


class WidgetSessionOut(BaseModel):
    session_token: str
    expires_in: int
    whatsapp: WhatsAppStatusOut


# ── /admin/partners ──────────────────────────────────────────────────────────


_ADDRESS_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normal_address(value: object) -> object:
    """Trimmed and lower-cased, like every invitation. On purpose not ``EmailStr``,
    which refuses special-use domains: here the shape is enough, and the real
    proof is that the link arrives and the person opens it. No spaces also means
    no header injection."""
    if not isinstance(value, str):
        return value
    value = value.strip().lower()
    if not _ADDRESS_SHAPE.match(value):
        raise ValueError("invalid e-mail")
    return value


OwnerAddress = Annotated[str, BeforeValidator(_normal_address), Field(max_length=255)]


class PartnerCreateIn(BaseModel):
    """Spec 052: a partner is born with its owner invited. The address also
    becomes its contact, so no separate one is asked for (decision D2)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    owner_email: OwnerAddress


class OwnerInviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: OwnerAddress


class OwnerInvitationActionIn(BaseModel):
    """Resend and revoke take nothing but the path. The empty model is what makes
    a ``tenant_id`` or a ``partner_id`` in the body a 422 instead of being ignored."""

    model_config = ConfigDict(extra="forbid")


class PartnerUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: Literal["active", "suspended"] | None = None
    contact_email: EmailStr | None = None
    # Spec 031: the operator edits where receipts go from the partner's page.
    billing_email: EmailStr | None = None
    broadcast_recipient_cap: int | None = Field(default=None, ge=1, le=10_000)
    rate_limit_mint_per_min: int | None = Field(default=None, ge=1, le=10_000)
    rate_limit_embed_per_min: int | None = Field(default=None, ge=1, le=100_000)
    # Blueprint (Fase 2b). Empty string clears the field.
    default_seed_template: str | None = Field(default=None, max_length=80)
    default_connector_slug: str | None = Field(default=None, max_length=80)
    auto_activate: bool | None = None


class PartnerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: str
    contact_email: str | None
    billing_email: str | None
    broadcast_recipient_cap: int
    rate_limit_mint_per_min: int
    rate_limit_embed_per_min: int
    default_seed_template: str | None
    default_connector_slug: str | None
    auto_activate: bool
    created_at: datetime
    updated_at: datetime
    # Spec 031 — what the operator needs to read a partner at a glance. The
    # flags and caps are columns; the counts and the balance are filled by
    # the list/get handlers (None when a handler does not compute them).
    console_enabled: bool = False
    companion_enabled: bool = False
    #: Spec 032: read-only here; written by PUT /admin/partners/{id}/access.
    console_modules: list[str] = []
    max_clients: int | None = None
    max_channels_per_client: int | None = None
    weekly_pool_tokens: int | None = None
    activated_at: datetime | None = None
    clients_count: int | None = None
    members_count: int | None = None
    #: Available balance in US$ cents, rounded down like the console shows it:
    #: what was recharged, without the weekly pool (spec 047, 46.1).
    #: None when the ledger could not be read (fail-closed, never a guess).
    available_cents: int | None = None
    #: Spec 041: how the partner is charged and its card (never more than the
    #: brand and the last four). None when it could not be read.
    billing_mode: str | None = None
    card_brand: str | None = None
    card_last4: str | None = None
    card_saved_at: datetime | None = None
    charges_paused: bool | None = None


class PartnerMemberOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    role: str
    status: str
    accepted_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime


class PartnerInvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    created_at: datetime
    #: Spec 052: the last send the provider accepted; null is «not known to
    #: have gone out». Only recorded for Auphere's invitations.
    last_sent_at: datetime | None = None
    #: An owner invitation no person of the partner issued. Only these have
    #: actions in the panel.
    from_auphere: bool = False


class OwnerStateOut(BaseModel):
    """Spec 052: what the Team tab and the header of the partner's file paint."""

    has_active_owner: bool
    #: R3.1: no active owner, no live invitation of Auphere, active, console on.
    can_invite: bool
    #: R4.1, R4.4: no active owner, active, console on.
    can_resend: bool
    #: Why neither can happen, when the reason is the partner's state.
    block: Literal["suspended", "console_off"] | None = None
    #: R3.10: the last invitation of Auphere, if it expired and nobody is in.
    expired_email: str | None = None
    expired_at: datetime | None = None
    #: R3.2, R3.10: what the form offers already written. Nothing is sent until
    #: the operator presses.
    suggested_email: str | None = None


class PartnerMembersOut(BaseModel):
    """Spec 031 (R4.6): the partner's people and its live invitations."""

    members: list[PartnerMemberOut]
    invitations: list[PartnerInvitationOut]
    owner: OwnerStateOut


class OwnerInvitationResultOut(BaseModel):
    """Spec 052: what happened to one send. Once, and only here, the link: the
    token is not stored, so this is the single time it exists outside the mail."""

    id: uuid.UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    created_at: datetime
    last_sent_at: datetime | None
    #: What the provider said. Never «delivered»: that is not known.
    email_sent: bool
    accept_url: str


class PartnerCreatedOut(PartnerOut):
    """Spec 052: the partner, and what became of its owner's invitation."""

    invitation: OwnerInvitationResultOut


class OwnerInvitationRevokedOut(BaseModel):
    id: uuid.UUID
    email: str
    status: str
    #: False if this call changed nothing (R5.4). It matters: the row may be
    #: dead because it was resent, and then there is another link alive.
    changed: bool


class PartnerAuditLineOut(BaseModel):
    """One platform audit row of a partner, as a sentence. Only the sentence: the
    raw before/after stay in the base."""

    id: uuid.UUID
    action: str
    actor: str
    summary: str
    created_at: datetime


class ApiKeyCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["live", "test"] = "live"
    # Validated against the vocabulary: a typo used to mint a key that
    # silently authorises nothing (or, worse, reads as authorising more
    # than it does on the partner's side).
    scopes: list[ApiKeyScopeLiteral] = Field(default=["provision", "broadcasts"])
    allowed_origins: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


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
    """Returned ONLY at creation/rotation — the single time the plaintext
    exists outside the partner's own storage."""

    plaintext: str


class ApiKeyRotateIn(BaseModel):
    grace_hours: int = Field(default=24, ge=0, le=24 * 14)


class OriginsUpdateIn(BaseModel):
    allowed_origins: list[str] = Field(max_length=20)


class PartnerTenantLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_client_ref: str = Field(min_length=1, max_length=255)
    tenant_id: uuid.UUID
    client_name: str | None = Field(default=None, max_length=255)


class PartnerTenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    partner_id: uuid.UUID
    external_client_ref: str
    tenant_id: uuid.UUID
    client_name: str | None
    created_at: datetime


class PartnerClientUsageOut(BaseModel):
    """Per-client (per-tenant) usage line — the billing/metrics unit."""

    external_client_ref: str
    client_name: str | None
    tenant_id: uuid.UUID
    tenant_status: str
    whatsapp_connected: bool
    agent_version: int | None
    agent_seed_template: str | None
    broadcasts: int
    broadcast_recipients: int
    messages_inbound: int
    messages_outbound: int
    #: Auphere's own model cost (``messages.cost_usd``). Not what the client
    #: pays. Kept as a float for old readers; ``internal_cost_usd`` is exact.
    cost_usd: float
    #: Spec 033 (R7.2): Auphere's cost, summed as a decimal, as a string.
    internal_cost_usd: str = "0"
    #: Spec 033 (R7.2): what the client spent at sale price, from the book.
    spend_cents: int = 0


class PartnerUsageOut(BaseModel):
    """Aggregated usage for one partner over a window (default 30 days).

    Everything an invoice or a health check needs: how many clients are
    live, what each one consumed, and the model cost incurred."""

    partner_id: uuid.UUID
    window_days: int
    clients_total: int
    clients_active: int
    clients_whatsapp_connected: int
    clients_with_agent: int
    broadcasts: int
    broadcast_recipients: int
    messages_inbound: int
    messages_outbound: int
    cost_usd: float
    internal_cost_usd: str = "0"
    #: Sale price from the book: the clients' spend plus the Companion's.
    spend_cents: int = 0
    spend_outside_clients_cents: int = 0
    clients: list[PartnerClientUsageOut]


class EmbedAuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_id: uuid.UUID | None
    api_key_id: uuid.UUID | None
    tenant_id: uuid.UUID | None
    event: str
    payload: dict[str, Any]
    ip: str | None
    origin: str | None
    jti: str | None
    created_at: datetime

    @field_validator("ip", mode="before")
    @classmethod
    def _ip_as_text(cls, v: object) -> object:
        # The column is INET: asyncpg hands back an ``ipaddress`` object, not
        # the string that was written.
        return None if v is None else str(v)
