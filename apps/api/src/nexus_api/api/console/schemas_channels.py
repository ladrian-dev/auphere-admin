"""Request/response models of the console ``channels`` lane
(CP-17 WhatsApp, CP-18 templates, CP-19 diagnostics).

Same two rules as ``schemas.py`` (no tenant ids, no message bodies).
Everything here is channel *metadata* the partner already knows or
needs to act on: the number, its Meta quality rating, template names
and Meta's own review verdicts. Never ``config_encrypted``, never a
BISUAT, never a phone_number_id.

One deliberate name: ``rejection_reason`` is the literal text Meta
attaches to a rejected template (``whatsapp_template_status.reason``).
It is Meta's review verdict about the partner's own template — not a
customer's words — so it does not fall under C8. It is NOT called
``reason`` because that name is reserved for message-shaped fields by
``tests/isolation/test_console_scope.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from nexus_api.schemas.whatsapp_templates import (
    TemplateButtonIn,
    TemplateCategory,
    TemplateContentIn,
    TemplateContentOut,
    TemplateCreateIn,
)

from .schemas import ChannelOut, ClientHealthOut

# ── channels overview (CP-17) ──────────────────────────────────────────

ChannelRole = Literal["agent", "notifications"]


class CatalogOut(BaseModel):
    """El catálogo de Commerce Manager enlazado a la cuenta del número (spec 022)."""

    id: str
    name: str | None = None
    checked_at: datetime | None = None


class CatalogErrorOut(BaseModel):
    """Lo último que Meta rechazó sobre el catálogo, traducido a un código."""

    code: str
    message: str | None = None
    at: datetime | None = None


class CatalogSummaryOut(BaseModel):
    id: str
    name: str | None = None
    product_count: int | None = None


class CatalogListOut(BaseModel):
    """Los catálogos del negocio dueño del token del canal, y cuál está enlazado."""

    items: list[CatalogSummaryOut]
    linked_id: str | None = None


class CatalogSetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Meta's catalogue ids are digits. Checked here too, not only in the
    #: console: the id goes into a Graph path (QA 2026-10-30, INC-27).
    catalog_id: str = Field(min_length=1, max_length=32, pattern=r"^[0-9]+$")
    #: Only read on a coexistence number when Meta will not list the
    #: catalogues: the name the partner typed, shown on the card as is.
    catalog_name: str | None = Field(default=None, max_length=120)


#: ``coexistence`` (2026-10-01): the number keeps using the WhatsApp Business
#: app, and Meta refuses the catalogue edge for that account type. The
#: catalogue is whatever the app has connected; the console records it and
#: cannot verify it with Meta.
CatalogState = Literal["none", "linked", "permission_missing", "unchecked", "coexistence"]


class ChannelDetailOut(ChannelOut):
    """A channel row plus the Meta health snapshot kept in ``config``
    (written at signup; refreshed by the quality cron when it runs).
    Only descriptive keys are lifted out of ``config`` — never the ids."""

    quality_rating: str | None = None
    messaging_tier: str | None = None
    verified_name: str | None = None
    mode: str | None = None
    agent_enabled: bool = True
    #: El logotipo de la aplicación del canal, tomado del catálogo de
    #: conectores (``whatsapp_meta.provider_meta.icon_url``). Viaja aquí
    #: porque el canal es lo que la tarjeta pinta, y porque el catálogo de
    #: conectores **no** lista los que son solo canal: sin esto, la consola no
    #: tendría de dónde sacarlo.
    logo_url: str | None = None
    #: Spec 021: lo que quedó por deshacer en Meta al desvincular. Vacío en el
    #: caso bueno. La tarjeta lo lee para decir «queda pendiente» y reintentar.
    unlink_pending: list[str] = Field(default_factory=list)
    #: Spec 022: el catálogo enlazado, o nada; y en qué estado está la verdad
    #: («linked» coincide con Meta; «unchecked» no se pudo comprobar;
    #: «permission_missing» la conexión no trajo el permiso).
    catalog: CatalogOut | None = None
    catalog_state: CatalogState = "none"
    catalog_error: CatalogErrorOut | None = None
    #: Las habilidades que conectar este catálogo encendió en el borrador del agente.
    catalog_skills_added: list[str] = Field(default_factory=list)
    #: Spec 049 — Instagram / Messenger: the account or Page as the business
    #: knows it, and why it needs attention (``token_revoked``,
    #: ``messages_disabled``, …), if it does.
    display_name: str | None = None
    username: str | None = None
    picture_url: str | None = None
    needs_attention: str | None = None
    needs_attention_help: str | None = None
    comments_enabled: bool | None = None
    comment_public_reply: str | None = None
    #: Spec 063 (2.3): a quién responde el número. ``unset`` es «Sin configurar»:
    #: no responde a nadie, y la tarjeta del cliente lo dice.
    audience_mode: Literal["unset", "team_only", "everyone"] = "unset"


class MetaSocialChannelOfferOut(BaseModel):
    kind: Literal["instagram", "messenger"]
    config_id: str
    #: Spec 081: Instagram only — the Facebook-only configuration that also
    #: asks for the linked Page, so its direct messages reach the agent.
    page_config_id: str | None = None


class MetaSocialOfferOut(BaseModel):
    app_id: str
    graph_version: str
    channels: list[MetaSocialChannelOfferOut] = Field(default_factory=list)


class ChannelsOverviewOut(BaseModel):
    """What the channels tab renders in one round-trip."""

    channels: list[ChannelDetailOut]
    max_channels: int
    used_channels: int
    #: False when the quota is full — the UI disables "Connect" with the reason.
    can_connect: bool
    #: True when >1 active WhatsApp channel and at least one is untagged:
    #: sends by role would be REFUSED (services/channel_routing.py).
    roles_required: bool
    #: True when this deployment has Meta credentials for the tenant.
    meta_connected: bool
    #: Spec 049 — Instagram / Messenger this partner may connect, with the
    #: Facebook Login for Business configuration each opens. Empty when the
    #: partner does not have them (the console then draws nothing).
    meta_social: MetaSocialOfferOut | None = None


class ChannelRoleIn(BaseModel):
    """Assign or clear (``null``) the routing role of a channel."""

    model_config = ConfigDict(extra="forbid")

    role: ChannelRole | None


# ── WhatsApp Embedded Signup (CP-17) ───────────────────────────────────


class WhatsAppSignupIn(BaseModel):
    """Same envelope the admin panel posts (``api/admin/meta_signup.py``):
    the single-use OAuth ``code`` from ``FB.login`` and the ids Meta posts
    back. ``connect-owned`` (permanent System User token) is deliberately
    NOT available to partners."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=512)
    waba_id: str = Field(min_length=1, max_length=64)
    phone_number_id: str | None = Field(default=None, max_length=64)
    business_id: str | None = Field(default=None, max_length=64)
    mode: Literal["cloud_api", "coexistence"] = "cloud_api"


class WhatsAppSignupOut(BaseModel):
    status: str
    channel_id: uuid.UUID
    display_phone_number: str
    mode: str
    used_channels: int
    max_channels: int
    #: Spec 016 (R1.2): what the number changed for the client — activated
    #: when the partner auto-activates and an agent is published — and the
    #: health the card will show, so the screen does not have to guess.
    client_status: str
    health: ClientHealthOut


# ── templates (CP-18) ──────────────────────────────────────────────────

#: Short, stable codes the UI translates. Mapped from Meta's rejection
#: reasons in ``api/console/templates.py::suggested_action_for``.
SuggestedAction = Literal[
    "fix_format",
    "change_category",
    "rewrite_content",
    "remove_promotional",
    "add_variables_samples",
    "contact_support",
    "wait_review",
    "none",
]


class SystemVariablesOut(BaseModel):
    mode: Literal["exact", "subset_keep"]
    variables: list[str]


class TemplateRowOut(BaseModel):
    """One template as Meta reports it, joined with the last review
    verdict the webhook mirrored locally."""

    id: str | None = None
    name: str
    language: str
    category: str | None = None
    status: str | None = None
    quality_score: str | None = None
    #: Spec 050: Meta announced a new category (``template_category_update``)
    #: and applies it in about a day. ``None`` when nothing is pending.
    pending_category: str | None = None
    components: list[dict[str, Any]] = Field(default_factory=list)
    #: Meta's literal rejection text (see module docstring). ``None`` unless
    #: the webhook recorded a REJECTED/PAUSED/DISABLED event with a reason.
    rejection_reason: str | None = None
    suggested_action: SuggestedAction = "none"
    last_event_at: datetime | None = None
    #: Spec 075: why the template cannot be edited here (closed codes, the
    #: UI writes the sentence), or ``None`` when it can.
    edit_blocker: str | None = None
    #: The content split into the editor's parts; ``None`` when a part of it
    #: cannot be painted (the edit would drop it).
    draft: TemplateContentOut | None = None
    #: Fingerprint of ``{category, components}``, sent back on save (7.1).
    version: str | None = None
    #: Set for the templates Auphere sends by name (075, requisito 4).
    system_variables: SystemVariablesOut | None = None


class TemplateListOut(BaseModel):
    items: list[TemplateRowOut]
    approved: int
    rejected: int
    pending: int


class TemplateEditIn(TemplateContentIn):
    """Spec 075: the whole content again (Meta replaces it as a whole), the
    fingerprint the editor opened (7.1) and whether the person already
    confirmed what the server warned about (2.2, 5.1). ``extra="forbid"``
    (inherited) keeps a Meta ``template_id`` or ``waba_id`` out (8.1)."""

    version: str = Field(min_length=16, max_length=16, pattern=r"^[0-9a-f]{16}$")
    confirm: bool = False


class TemplateEditOut(BaseModel):
    name: str
    language: str
    changed: bool
    status: str | None
    category: str | None


class TemplateCreateOut(BaseModel):
    id: str | None
    name: str
    status: str | None
    category: str | None


class TemplateDeleteOut(BaseModel):
    name: str
    deleted: bool


# ── diagnostics (CP-19) ────────────────────────────────────────────────

DiagnosticState = Literal["ok", "warn", "fail", "unknown"]

#: Codes the UI translates into "what to do". Kept as an enum so the
#: frontend test can assert every code has an ES/EN string.
WhatToDo = Literal[
    "connect_whatsapp",
    "reconnect_whatsapp",
    "assign_roles",
    "check_webhook",
    "wait_health_check",
    "review_templates",
    "create_template",
    "improve_quality",
    "check_meta_billing",
    "activate_channel",
    "none",
]


class DiagnosticRowOut(BaseModel):
    key: str
    state: DiagnosticState
    what_to_do: WhatToDo = "none"
    #: Short value shown next to the state (a count, a rating, a date).
    detail: str | None = None
    #: External link the partner can open (Meta Business Manager, docs).
    link: str | None = None


class DiagnosticsOut(BaseModel):
    rows: list[DiagnosticRowOut]
    checked_at: datetime
    healthy: bool


class TestSendIn(BaseModel):
    """Send the pre-approved ``hello_world`` template to one number.
    Deliberately narrower than the admin's ``MetaTestSendIn``: no free
    text, no arbitrary template — this is a reachability probe."""

    model_config = ConfigDict(extra="forbid")

    to: str = Field(min_length=5, max_length=20, pattern=r"^\+?[0-9]{5,20}$")
    language: str = Field(default="en_US", max_length=16)


class TestSendOut(BaseModel):
    status: str
    wamid: str
    to: str


__all__ = [
    "ChannelDetailOut",
    "ChannelRole",
    "ChannelRoleIn",
    "ChannelsOverviewOut",
    "DiagnosticRowOut",
    "DiagnosticState",
    "DiagnosticsOut",
    "SuggestedAction",
    "TemplateButtonIn",
    "TemplateCategory",
    "TemplateCreateIn",
    "TemplateCreateOut",
    "TemplateDeleteOut",
    "TemplateListOut",
    "TemplateRowOut",
    "TestSendIn",
    "TestSendOut",
    "WhatToDo",
    "WhatsAppSignupIn",
    "WhatsAppSignupOut",
]
