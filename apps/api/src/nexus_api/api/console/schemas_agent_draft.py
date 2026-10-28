"""Schemas of the agent's one draft — spec 047, historia 2 (requisito 3).

``contracts/console-api.md`` §4: ``GET/PATCH/DELETE
/console/clients/{ref}/agents/{agent_id}/draft`` and the history
``GET …/agents/{agent_id}/versions``. Metadata and the partner's own words
about its agent; never a customer's (C8), never an internal tenant id. The
change note travels as ``change_note`` in the answers: it is the partner's
note about a version, not a note about anyone.

The AgentSpec, the compiled preview and the state of the tests join the
draft with the builder (ola 3); today the draft is the fields the editors
of the agent write.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nexus_api.services.agent_console_policy import ConsolePolicy

from .schemas_agent_tools import AudienceIn, AudienceOut, PaymentReviewIn, PaymentReviewOut

DraftScreen = Literal["settings", "capabilities", "knowledge", "prompt"]
DraftAction = Literal["edit", "discard"]
VersionStatus = Literal["staged", "active", "archived"]


class DraftTestsOut(BaseModel):
    """How many tests the agent has and how many must run again (17.7)."""

    total: int
    stale: int
    case: int
    sector: int


class AgentDraftOut(BaseModel):
    """The draft of one agent — or, without one, the version it would start
    from — with the revision every write has to send back in ``If-Match``.

    ``number`` is «v{n} de {agente}» (per agent); ``version`` is the
    client-wide number the routes of today still take."""

    agent_id: uuid.UUID
    agent_name: str
    revision: int
    exists: bool
    number: int | None
    version: int | None
    status: VersionStatus | None
    base_number: int | None
    active_number: int | None
    active_version: int | None
    author: str | None
    created_at: datetime | None
    updated_at: datetime | None
    change_note: str | None
    system_prompt: str
    tools: list[str]
    skills: list[str]
    settings: ConsolePolicy
    audience: AudienceOut
    payment_review: PaymentReviewOut
    #: The screens of the agent where the draft differs from the active version.
    screens: list[DraftScreen] = Field(default_factory=list)
    allowed: list[DraftAction] = Field(default_factory=list)
    # Spec 047 (T080, requisito 16): the version's AgentSpec — a version of
    # before the 047 reads in «instructions» mode — and the state of its tests.
    spec: dict[str, Any] | None = None
    tests: DraftTestsOut | None = None


class AgentDraftPatchIn(BaseModel):
    """What changes in the draft. Only what is sent changes; ``settings``
    replaces ``policies.console`` whole, as the settings form sends it."""

    model_config = ConfigDict(extra="forbid")

    system_prompt: str | None = Field(default=None, min_length=1, max_length=200_000)
    tools: list[str] | None = Field(default=None, max_length=200)
    settings: ConsolePolicy | None = None
    audience: AudienceIn | None = None
    payment_review: PaymentReviewIn | None = None
    #: The change note of this version (R3.6); ``""`` clears it.
    note: str | None = Field(default=None, max_length=500)
    # Spec 047: the whole AgentSpec, validated without a model (15.4). It is
    # compiled into ``system_prompt`` and wins over ``system_prompt``/``tools``.
    spec: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _says_something(self) -> AgentDraftPatchIn:
        sent = (
            self.system_prompt,
            self.tools,
            self.settings,
            self.audience,
            self.payment_review,
            self.note,
            self.spec,
        )
        if all(value is None for value in sent):
            raise ValueError("send at least one change")
        return self


class DraftChangeOut(BaseModel):
    """One write on the draft after the revision a stale writer read: who,
    when, and which fields (``settings.tone``, ``system_prompt``…). The
    console turns the keys into words."""

    revision: int
    kind: Literal["edit", "publish", "rollback", "discard"]
    by: str
    at: datetime
    fields: list[str]


class DraftConflictOut(BaseModel):
    """The ``detail`` of a ``412``: the draft as it is now and what changed
    since the revision in ``If-Match``. Nothing of the refused write landed."""

    code: Literal["revision_conflict"]
    current: AgentDraftOut
    changes: list[DraftChangeOut]


class AgentVersionEntryOut(BaseModel):
    """One version of the agent's history (R3.4, R3.6)."""

    number: int
    version: int
    status: VersionStatus
    author: str | None
    created_at: datetime
    published_at: datetime | None
    published_by: str | None
    change_note: str | None
    base_number: int | None


__all__ = [
    "AgentDraftOut",
    "AgentDraftPatchIn",
    "AgentVersionEntryOut",
    "DraftChangeOut",
    "DraftConflictOut",
    "DraftScreen",
]
