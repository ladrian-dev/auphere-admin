"""Request/response models of the console playground (CP-16, lane B).

Same rules as ``schemas.py``: no internal tenant ids, no message bodies
(C8), no ``cost_usd`` (C9 — the partner sees tokens, never dollars).

The playground is the ONE place where the partner writes and reads its
own test text — but that text travels only over the SSE stream
(``GET …/playground/threads/{id}/stream``, a ``StreamingResponse`` with
no OpenAPI response schema). No REST response here carries a transcript:
the console keeps the session transcript in browser memory and the
thread list is metadata only. That is what keeps
``tests/isolation/test_console_scope.py`` (structural body check) green
without an allow-list entry.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# ── threads ────────────────────────────────────────────────────────────


class PlaygroundThreadCreateIn(BaseModel):
    title: str = Field(default="Untitled", min_length=1, max_length=200)


class PlaygroundThreadPatchIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    archived: bool | None = None


class PlaygroundThreadOut(BaseModel):
    """A test thread of the calling member against this client's agent.

    Always ``dry_run`` (side effects blocked) — there is no toggle in the
    console, so the flag is not even exposed. ``turn_count`` is the number
    of turns sent so far (not the messages themselves).
    """

    id: uuid.UUID
    title: str
    archived_at: datetime | None
    last_run_at: datetime | None
    turn_count: int
    created_at: datetime
    updated_at: datetime


# ── runs ───────────────────────────────────────────────────────────────


class PlaygroundRunStartIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


class PlaygroundRunStartOut(BaseModel):
    run_id: uuid.UUID
    thread_id: uuid.UUID
    status: str


# ── budget ─────────────────────────────────────────────────────────────


class PlaygroundBudgetOut(BaseModel):
    """Month-to-date playground spend of the partner, in LLM tokens.

    ``used`` = input + output tokens of every finished playground turn of
    the partner (all clients, all members) since the first day of the
    current UTC month; ``cap`` = ``partners.qa_monthly_token_cap``;
    ``resets_at`` = first instant of next month (UTC).
    """

    used: int
    cap: int
    remaining: int
    percent: float
    exhausted: bool
    period: str = Field(description="UTC calendar month, YYYY-MM")
    resets_at: datetime


__all__ = [
    "PlaygroundBudgetOut",
    "PlaygroundRunStartIn",
    "PlaygroundRunStartOut",
    "PlaygroundThreadCreateIn",
    "PlaygroundThreadOut",
    "PlaygroundThreadPatchIn",
]
