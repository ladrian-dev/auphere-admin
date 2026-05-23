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

Activation is per ``agent_config`` via ``runtime_outcome_grader BOOLEAN``
(migration 0035). The grader node checks
``state["agent_runtime_flags"]["outcome_grader"]`` populated by the
handler from the bundle. No env vars per-tenant.

Public surface:

- :class:`OutcomeGrader` — async grader callable.
- :class:`GraderVerdict` — JSON-shaped verdict the grader returns.
- :func:`load_rubric_text` — read the bundled markdown rubrics.
- :func:`available_rubric_intents` — for admin UI / validation.
"""

from __future__ import annotations

from nexus_worker.guardrails.outcome_grader import (
    GRADER_FALLBACK_RESPONSE,
    GraderVerdict,
    OutcomeGrader,
)
from nexus_worker.guardrails.rubric_loader import (
    available_rubric_intents,
    load_rubric_text,
)

__all__ = [
    "GRADER_FALLBACK_RESPONSE",
    "GraderVerdict",
    "OutcomeGrader",
    "available_rubric_intents",
    "load_rubric_text",
]
