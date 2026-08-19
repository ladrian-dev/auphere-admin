"""Request/response models of the console Companion (CO-01).

Same rules as the rest of ``/console/*``: no internal tenant ids, no
``partner_id`` in, no ``cost_usd`` out (C9 — the partner sees tokens, never
dollars). A client is named by its ``client_ref``.

Where this lane differs from every other one, and why it is legitimate
-----------------------------------------------------------------------
Decision C8 says no ``/console/*`` response carries the body of a message.
The Companion **does** serve its own transcript: it is the partner's own
work — what Auphere said to them and what they said to Auphere — and it has
to survive an F5, a closed laptop and an API restart, so it cannot live in
browser memory the way the playground's does.

:class:`CompanionEventOut` therefore models the payload as an untyped
``data`` object. That is not a way around the structural check in
``tests/isolation/test_console_scope.py`` — it is the honest shape: the
payloads are heterogeneous by design (``text.delta``, ``cost.updated``,
``phase.changed``…) and a discriminated union would force ``text`` to be a
declared property, which is exactly what that check forbids.

The real guard is stronger and lives where the events are written:
``api/companion_streaming.py::COMPANION_EVENTS`` is a **closed catalogue**
of event → allowed payload keys, applied by the publisher, and
``tests/isolation/test_companion_no_customer_bodies.py`` proves that no key
in it can carry an end customer's message body.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ── threads ────────────────────────────────────────────────────────────


class CompanionThreadCreateIn(BaseModel):
    title: str = Field(default="Nueva conversación", min_length=1, max_length=200)
    # The partner's own reference for a client. Optional: a thread can start
    # with no client at all ("créame un agente para una clínica dental").
    # NEVER a tenant id — it is resolved under the principal's partner.
    client_ref: str | None = Field(default=None, min_length=1, max_length=255)
    mode: str = Field(default="consult", pattern="^(consult|build)$")


class CompanionThreadPatchIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    archived: bool | None = None
    mode: str | None = Field(default=None, pattern="^(consult|build)$")


class CompanionThreadOut(BaseModel):
    """One Companion conversation of the calling member. Metadata only."""

    id: uuid.UUID
    title: str
    mode: str
    client_ref: str | None
    archived_at: datetime | None
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ── runs ───────────────────────────────────────────────────────────────


class CompanionRunStartIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    # What the drawer knows about where the user is standing (route, tab,
    # selection). Travels to the model as a mid-conversation SYSTEM message,
    # never inside the cached system prefix (Parte II, C4). Bounded so a
    # crafted client cannot push a novel through it.
    page_context: dict[str, Any] | None = None


class CompanionRunStartOut(BaseModel):
    """202: the run started and the work continues regardless of what
    happens to this connection. Open the stream (or poll the events) next."""

    run_id: uuid.UUID
    thread_id: uuid.UUID
    status: str


class CompanionEventOut(BaseModel):
    """One event of the durable run log.

    ``seq`` is monotonic per run and is the resume cursor: ask for
    ``since_seq=<last seq you saw>`` and you get exactly what you missed,
    with no duplicates.
    """

    seq: int
    event: str
    data: dict[str, Any]


class CompanionRunSummaryOut(BaseModel):
    """One run of a thread, as the drawer needs it to rebuild the timeline.

    Metadata only — no tokens, no answer, no error text. Everything a
    reader could want beyond this is one ``…/runs/{id}/events`` away, and
    keeping it thin means a thread with fifty runs is still one small
    response.
    """

    run_id: uuid.UUID
    status: str
    started_at: datetime
    ended_at: datetime | None


class CompanionThreadRunsOut(BaseModel):
    """The runs of one thread, oldest first (contract v1.1, §5.2).

    The drawer's timeline belongs to the **thread**, not to a run: one
    conversation spans a turn, a pause for confirmation, and the run that
    continues after it. Rebuilding that view means concatenating each run's
    events in order — and without this endpoint the browser cannot even
    enumerate which runs a thread has.

    The alternative was an index in ``localStorage``, which breaks the
    requirement that a ``?companion=<thread>`` URL be shareable inside the
    team: whoever opens the link on another machine would see an empty
    thread. A local index is not a frontend shortcut, it is a missing
    server-side fact.
    """

    thread_id: uuid.UUID
    runs: list[CompanionRunSummaryOut]


class CompanionEventsOut(BaseModel):
    """History of a run, oldest first.

    ``available_from`` is only set when the log rotated past ``since_seq``:
    the client then knows there IS a hole and where it can pick up, instead
    of a dead-end gap notice.
    """

    run_id: uuid.UUID
    events: list[CompanionEventOut]
    next_seq: int
    available_from: int | None = None


# ── budget ─────────────────────────────────────────────────────────────


class CompanionBudgetOut(BaseModel):
    """Month-to-date Companion spend of the partner, in LLM tokens.

    Its own cap on purpose: sharing the playground's would make testing an
    agent and asking the Companion for help steal budget from each other.
    """

    used: int
    cap: int
    remaining: int
    percent: float
    exhausted: bool
    period: str = Field(description="UTC calendar month, YYYY-MM")
    resets_at: datetime


# ── actions (CO-04) ────────────────────────────────────────────────────


class CompanionResumeIn(BaseModel):
    """The human's decision on a pending action.

    ``note`` is singular on purpose: ``notes`` (plural) is in the forbidden
    property list of ``test_console_scope.py``, and so are ``reason`` and
    ``message`` — the three names this field would naturally have. It is not
    cosmetic either: the note is written by a **partner's own team member**
    about their own work, never by an end customer, which is what the C8
    guard protects.

    With ``edit`` or ``cancel`` the note travels back to the model as the
    reason for the refusal (Managed Agents' ``deny_message``), so it changes
    the next proposal instead of merely stopping this one.
    """

    model_config = ConfigDict(extra="forbid")

    action_id: uuid.UUID
    decision: Literal["confirm", "edit", "cancel"]
    note: str | None = Field(default=None, max_length=2000)


class CompanionResumeOut(BaseModel):
    """202: the decision is recorded and a NEW run continues the thread.

    ``run_id`` is that new run — not the one that paused. The thread is
    continuous for the person; the runs are not, and the drawer has to
    follow the one returned here.
    """

    run_id: uuid.UUID
    thread_id: uuid.UUID
    action_id: uuid.UUID
    status: str


class CompanionActionOut(BaseModel):
    """A proposed change and where its decision stands.

    Reconstructible from ``hitl.requested`` too — this endpoint exists so a
    reload with a pending confirmation can paint the card without depending
    on the Redis run log still being alive.

    No property here is named ``payload``, ``notes``, ``reason``,
    ``message``, ``content``, ``text``, ``body`` or ``tool_calls``.
    ``preview``, ``diff`` and ``impact`` are untyped objects/lists, so the
    OpenAPI walk finds nothing inside — the same honest shape as
    ``CompanionEventOut``, and for the same reason: the contents are
    heterogeneous by design, one shape per action kind.
    """

    action_id: uuid.UUID
    thread_id: uuid.UUID
    run_id: uuid.UUID | None
    kind: str
    title: str
    preview: dict[str, Any]
    diff: list[dict[str, Any]] | None
    impact: list[dict[str, Any]]
    risk: str
    reversible: bool
    status: str
    state_hash: str
    proposed_at: datetime
    expires_at: datetime
    decided_at: datetime | None
    decided_by: str | None
    applied_at: datetime | None
    #: Verification outcome; ``None`` when it has not run. Deliberately
    #: nullable rather than defaulting to ``False`` — "not verified" and
    #: "verified and wrong" are different things and the drawer paints them
    #: differently.
    ok: bool | None


__all__ = [
    "CompanionActionOut",
    "CompanionBudgetOut",
    "CompanionEventOut",
    "CompanionEventsOut",
    "CompanionResumeIn",
    "CompanionResumeOut",
    "CompanionRunStartIn",
    "CompanionRunStartOut",
    "CompanionRunSummaryOut",
    "CompanionThreadCreateIn",
    "CompanionThreadOut",
    "CompanionThreadPatchIn",
    "CompanionThreadRunsOut",
]
