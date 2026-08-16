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

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .schemas import ChannelOut

# ── channels overview (CP-17) ──────────────────────────────────────────

ChannelRole = Literal["agent", "notifications"]


class ChannelDetailOut(ChannelOut):
    """A channel row plus the Meta health snapshot kept in ``config``
    (written at signup; refreshed by the quality cron when it runs).
    Only descriptive keys are lifted out of ``config`` — never the ids."""

    quality_rating: str | None = None
    messaging_tier: str | None = None
    verified_name: str | None = None
    mode: str | None = None
    agent_enabled: bool = True


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


# ── templates (CP-18) ──────────────────────────────────────────────────

_TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9_]{1,512}$")

TemplateCategory = Literal["MARKETING", "UTILITY", "AUTHENTICATION"]

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


class TemplateRowOut(BaseModel):
    """One template as Meta reports it, joined with the last review
    verdict the webhook mirrored locally."""

    id: str | None = None
    name: str
    language: str
    category: str | None = None
    status: str | None = None
    quality_score: str | None = None
    components: list[dict[str, Any]] = Field(default_factory=list)
    #: Meta's literal rejection text (see module docstring). ``None`` unless
    #: the webhook recorded a REJECTED/PAUSED/DISABLED event with a reason.
    rejection_reason: str | None = None
    suggested_action: SuggestedAction = "none"
    last_event_at: datetime | None = None


class TemplateListOut(BaseModel):
    items: list[TemplateRowOut]
    approved: int
    rejected: int
    pending: int


class TemplateButtonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["QUICK_REPLY", "URL", "PHONE_NUMBER"]
    label: str = Field(min_length=1, max_length=25)
    url: str | None = Field(default=None, max_length=2000)
    phone_number: str | None = Field(default=None, max_length=20)


class TemplateCreateIn(BaseModel):
    """Minimal authoring form: header/body/footer text + up to 3 buttons.
    Server builds the Cloud API ``components`` array."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=512)
    language: str = Field(default="es", min_length=2, max_length=15)
    category: TemplateCategory = "UTILITY"
    header_text: str | None = Field(default=None, max_length=60)
    body_text: str = Field(min_length=1, max_length=1024)
    footer_text: str | None = Field(default=None, max_length=60)
    buttons: list[TemplateButtonIn] = Field(default_factory=list, max_length=3)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not _TEMPLATE_NAME_RE.match(v):
            raise ValueError(
                "name must be lowercase letters, digits and underscores (e.g. reminder_24h)"
            )
        return v

    def to_components(self) -> list[dict[str, Any]]:
        components: list[dict[str, Any]] = []
        if self.header_text:
            components.append({"type": "HEADER", "format": "TEXT", "text": self.header_text})
        components.append({"type": "BODY", "text": self.body_text})
        if self.footer_text:
            components.append({"type": "FOOTER", "text": self.footer_text})
        if self.buttons:
            buttons: list[dict[str, Any]] = []
            for b in self.buttons:
                btn: dict[str, Any] = {"type": b.type, "text": b.label}
                if b.type == "URL" and b.url:
                    btn["url"] = b.url
                if b.type == "PHONE_NUMBER" and b.phone_number:
                    btn["phone_number"] = b.phone_number
                buttons.append(btn)
            components.append({"type": "BUTTONS", "buttons": buttons})
        return components


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
