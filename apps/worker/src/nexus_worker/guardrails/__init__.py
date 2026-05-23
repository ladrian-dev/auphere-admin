"""Output guardrails — Fase C of claude-platform-integration.

The pipeline's ReAct loop produces a draft response. Before that draft
reaches the customer, a separate grader LLM validates it against an
intent-specific markdown rubric. If the verdict is ``fail``, the
pipeline re-prompts the original model with the grader's feedback and
tries again — up to two retries. After that, the customer gets a
neutral "we couldn't complete this; a human will follow up" message
and the operator gets alerted.

This is the *Outcomes* mechanic from Anthropic's Managed Agents,
replicated client-side because we run on our own LangGraph runtime.
See [[architecture/outcome-grader]].

Public surface:

- :class:`OutcomeGrader` — async grader callable.
- :class:`GraderVerdict` — JSON-shaped verdict the grader returns.
- :func:`load_rubric` / :func:`load_rubric_text` — read the bundled
  markdown rubrics for an intent + vertical.
- :func:`outcome_grader_enabled_tenants` — feature flag helper.
- :func:`is_outcome_grader_enabled_for` — convenience.
"""

from __future__ import annotations

import os
import uuid

from nexus_worker.guardrails.outcome_grader import (
    GRADER_FALLBACK_RESPONSE,
    GraderVerdict,
    OutcomeGrader,
)
from nexus_worker.guardrails.rubric_loader import (
    available_rubric_intents,
    load_rubric_text,
)


def outcome_grader_enabled_tenants() -> frozenset[uuid.UUID]:
    """Parse ``NEXUS_OUTCOME_GRADER_ENABLED_TENANTS``.

    Comma-separated UUIDs. Empty / unset = feature OFF for every tenant,
    so the pipeline is unchanged for any tenant not explicitly opted in.

    Re-read on every call so operations can flip the var without a
    redeploy. A malformed UUID is dropped silently rather than crashing
    the worker for unrelated tenants.
    """
    raw = os.getenv("NEXUS_OUTCOME_GRADER_ENABLED_TENANTS", "")
    if not raw:
        return frozenset()
    out: set[uuid.UUID] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            out.add(uuid.UUID(token))
        except ValueError:
            continue
    return frozenset(out)


def is_outcome_grader_enabled_for(tenant_id: uuid.UUID) -> bool:
    """Whether the outcome grader runs for this tenant right now."""
    return tenant_id in outcome_grader_enabled_tenants()


__all__ = [
    "GRADER_FALLBACK_RESPONSE",
    "GraderVerdict",
    "OutcomeGrader",
    "available_rubric_intents",
    "is_outcome_grader_enabled_for",
    "load_rubric_text",
    "outcome_grader_enabled_tenants",
]
