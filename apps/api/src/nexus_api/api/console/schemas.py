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
    #: CO-08 §10 — la bandera por partner del Companion. La puerta real es
    #: ``companion:use`` **Y** esta bandera, comprobadas en el backend; esto
    #: es solo lo que la consola mira para montar o no la burbuja.
    companion_enabled: bool = False


# ── clients ────────────────────────────────────────────────────────────

ClientStatus = Literal["provisioning", "active", "paused", "archived"]


SetupStep = Literal["agent", "channel", "quota", "activation"]


class ClientSetupOut(BaseModel):
    """Spec 017 (R1.1): the four steps between a client and «atendiendo».
    A READING of what exists — active version, a customer-facing channel,
    the ledger, the tenant status — never a state machine. The list carries
    this shape; the record adds ``next``."""

    agent: bool
    channel: bool
    quota: bool
    active: bool


class ClientSetupDetailOut(ClientSetupOut):
    """The record's reading: ``next`` is the first pending step in the fixed
    order agent → channel → quota → activation; ``None`` when serving."""

    next: SetupStep | None = None


class ClientQuotaOut(BaseModel):
    """Spec 017 (R1.2): the client's cap and what is left, in credits."""

    cap: int
    remaining: int


class ClientSummaryOut(BaseModel):
    """One row of the client list. Cheap fields only."""

    external_client_ref: str
    name: str
    status: str
    timezone: str
    created_at: datetime
    updated_at: datetime
    #: Spec 016 (R2.1): the list shows the «sin cupo» dot without one scoped
    #: transaction per row — it is ``quota_state`` read once per page.
    out_of_quota: bool = False
    #: Spec 017 (R9.1): the list says who is ready and how much is left,
    #: read once per page (snapshots + ledger), never per row.
    setup: ClientSetupOut | None = None
    quota: ClientQuotaOut | None = None
    conversations_7d: int = 0


class ClientHealthOut(BaseModel):
    whatsapp_connected: bool
    display_phone_number: str | None = None
    agent_version: int | None = None
    agent_configured: bool
    ready: bool
    missing: list[str] = Field(default_factory=list)


class ClientOut(ClientSummaryOut):
    """Client detail: summary + health (+ spec 017: sector, setup with
    ``next``, quota)."""

    health: ClientHealthOut
    #: Spec 017 (R1, R5): the sector of the template the agent was seeded
    #: from; ``None`` for a hand-written agent.
    sector: str | None = None
    setup: ClientSetupDetailOut | None = None


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
    #: Spec 017 R3.1: qué pantallas de la ficha difieren entre el borrador y
    #: la versión activa, para que la pestaña lleve su punto. Vacío sin
    #: borrador.
    draft_screens: list[Literal["settings", "capabilities", "knowledge", "prompt"]] = Field(
        default_factory=list
    )


class AgentPublishIn(BaseModel):
    """Spec 017 R3.3: de dónde salió el clic. Publicar desde la barra del
    borrador y desde la pestaña «Agente» es el mismo acto, pero la auditoría
    los distingue — sin eso no hay forma de saber si la barra sirve."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    origin: Literal["draft_bar", "agent_tab"] = Field(default="agent_tab", alias="from")


class DraftSettingChangeOut(BaseModel):
    """Un ajuste que cambia, en su clave: la frase la pone la consola."""

    field: str
    before: Any = None
    after: Any = None


class DraftCapabilityChangeOut(BaseModel):
    name: str
    kind: Literal["tool", "skill"]
    change: Literal["enabled", "disabled"]
    before: Any = None
    after: Any = None


class DraftKnowledgeChangeOut(BaseModel):
    id: str
    title: str
    change: Literal["added", "removed"]


class DraftPromptChangeOut(BaseModel):
    before: str
    after: str


class DraftVersionsOut(BaseModel):
    draft: int
    active: int | None


class DraftDiffOut(BaseModel):
    """Spec 017 R3.2: qué cambia el borrador respecto a la versión que
    atiende ahora. Claves, no frases; el orden es el de lectura de la ficha."""

    version: DraftVersionsOut
    settings: list[DraftSettingChangeOut]
    capabilities: list[DraftCapabilityChangeOut]
    knowledge: list[DraftKnowledgeChangeOut]
    prompt: DraftPromptChangeOut


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


class TierOut(BaseModel):
    """A tier as the partner sees it.

    ``weekly_pool_tokens`` is deliberately absent. What describes a tier here
    are its **hard caps** — numbers that do not move, because moving them
    changes the product — and ``consumption_multiple``, computed server-side
    from the pool size. The figure itself is provisional (ADR-037) and will be
    adjusted; printing it turns every capacity change into a visible cut or
    gift, which is what Spec A R7.3 forbids (research D9).
    """

    code: str
    display_name: str
    monthly_price_cents: int
    max_teammates: int
    max_members: int
    #: ``None`` on the free tier and on any ratio that is not whole: saying
    #: "4x" for something that is 3.7x is a false commercial promise.
    consumption_multiple: int | None


class MembershipUsageOut(BaseModel):
    """What the partner is using right now.

    Ships with the membership object rather than behind another call: without
    it the screen would have to fetch the teammate list just to know whether
    the create button is disabled, and there would be a moment where it shows
    a button that is about to fail (principle V).
    """

    teammates: int
    members: int


class MembershipOut(BaseModel):
    tier: TierOut
    state: str
    state_changed_at: datetime | None
    current_period_end: datetime | None
    pending_tier: str | None
    usage: MembershipUsageOut
    purchased_expires_at: datetime | None
    catalog: list[TierOut]


class CheckoutIn(BaseModel):
    tier_code: str


class CheckoutOut(BaseModel):
    """``url`` is ``None`` when no payment page was needed.

    An upgrade does not open one — the subscription is modified and the
    difference prorated — and a downgrade does not either, because it is
    scheduled. Returning ``applied`` separately keeps the console from having
    to infer which of the three happened.
    """

    url: str | None = None
    applied: bool = False
    effective_at: datetime | None = None


class CreditIn(BaseModel):
    """Cuánto crédito se compra, en centavos de dólar.

    Los dos límites son deliberados. El **máximo** protege de un cero de más
    tecleado convirtiéndose en un cargo real —el error más caro que puede
    cometer alguien en esta pantalla— y el **mínimo** evita compras cuya
    comisión del proveedor se come el importe.

    Sólo USD en esta versión: la moneda de un cliente es irreversible en el
    proveedor, así que abrir otras sin decidirlo sería difícil de deshacer.
    """

    model_config = ConfigDict(extra="forbid")

    amount_cents: int = Field(ge=500, le=500_000)


class CancelOut(BaseModel):
    """Lo que se le dice a quien acaba de cancelar.

    Las dos cifras que necesita ahora mismo: qué pasa con el dinero que ya
    puso y hasta cuándo. Sin ellas lo pregunta por soporte, y mientras tanto
    cree que lo ha perdido.
    """

    state: str
    effective_at: datetime | None
    purchased_remaining: int
    purchased_expires_at: datetime | None


class PortalOut(BaseModel):
    url: str


class BillingOut(BaseModel):
    billing_email: str | None
    contact_email: str | None
    receipts: list[ReceiptSummaryOut]
