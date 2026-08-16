"""Schemas of the ``onboarding`` lane (CP-10 wizard, CP-29 notifications +
onboarding checklist). Metadata only: no tenant ids, no message bodies.

``NotificationOut.data`` (not ``payload`` — that name is reserved for
message content by the structural test) is the small dict the console
renders in the viewer's language.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ── seed templates (CP-10) ─────────────────────────────────────────────


class SeedPlaceholderOut(BaseModel):
    """One value the wizard asks for. ``key`` is the seed's dotted key
    (``owner.first_name``, ``policies.no_show.fee_pct``)."""

    key: str
    required: bool
    #: ``secret`` = the UI asks for it without echo and the API never
    #: returns it (bank details of the cobranza seed, admin phones…).
    secret: bool = False
    kind: Literal["text", "number", "list"] = "text"
    example: str | None = None


class SeedTemplateOut(BaseModel):
    name: str
    display_name: str
    version: str
    vertical: str
    tools_count: int
    placeholders: list[SeedPlaceholderOut]


class FromSeedIn(BaseModel):
    seed_template: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+$")
    placeholders: dict[str, Any] = Field(default_factory=dict)


# ── notifications (CP-29) ─────────────────────────────────────────────


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    severity: str  # info | warning | critical (DB CHECK)
    data: dict[str, Any]
    external_client_ref: str | None = None
    read: bool
    created_at: datetime


class NotificationPageOut(BaseModel):
    items: list[NotificationOut]
    next_cursor: str | None = None
    unread: int


class UnreadCountOut(BaseModel):
    unread: int


class ReadAllOut(BaseModel):
    marked: int


# ── onboarding checklist (CP-29) ──────────────────────────────────────


class OnboardingStepOut(BaseModel):
    key: Literal[
        "team", "first_client", "agent_published", "channel_connected", "first_conversation"
    ]
    done: bool
    href: str


class OnboardingOut(BaseModel):
    steps: list[OnboardingStepOut]
    done_count: int
    total: int
    complete: bool
    partner_created_at: datetime
    activated_at: datetime | None
    time_to_first_active_client_seconds: int | None


__all__ = [
    "FromSeedIn",
    "NotificationOut",
    "NotificationPageOut",
    "OnboardingOut",
    "OnboardingStepOut",
    "ReadAllOut",
    "SeedPlaceholderOut",
    "SeedTemplateOut",
    "UnreadCountOut",
]
