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
from typing import Any

from pydantic import BaseModel, Field

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


__all__ = [
    "CompanionBudgetOut",
    "CompanionEventOut",
    "CompanionEventsOut",
    "CompanionRunStartIn",
    "CompanionRunStartOut",
    "CompanionThreadCreateIn",
    "CompanionThreadOut",
    "CompanionThreadPatchIn",
]
