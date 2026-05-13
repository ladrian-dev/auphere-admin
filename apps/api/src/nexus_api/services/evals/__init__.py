"""Block P — eval suite services.

Public surface:

- :func:`run_eval` — the runner the admin endpoint dispatches to. Takes
  a dataset id + agent_config version and orchestrates: run each case
  through the Bloque O sandbox, apply assertions, persist results,
  update the run aggregate.
- :class:`JudgeProvider` — Protocol for the LLM-as-judge call. Production
  uses :class:`LiteLLMJudgeProvider` (Haiku); tests inject
  :class:`FakeJudgeProvider`.
- :func:`evaluate_assertions` — pure-Python applicator for deterministic
  checks. Exposed for unit tests and for the runner.
- :func:`has_passing_recent_run` — promotion-gate helper.
"""

from __future__ import annotations

from nexus_api.services.evals.assertions import (
    AssertionResult,
    AssertionValidationError,
    evaluate_assertions,
    validate_assertions,
)
from nexus_api.services.evals.judge import (
    FakeJudgeProvider,
    JudgeError,
    JudgeProvider,
    LiteLLMJudgeProvider,
)
from nexus_api.services.evals.runner import (
    EvalRunOutcome,
    has_passing_recent_run,
    run_eval,
)

__all__ = [
    "AssertionResult",
    "AssertionValidationError",
    "EvalRunOutcome",
    "FakeJudgeProvider",
    "JudgeError",
    "JudgeProvider",
    "LiteLLMJudgeProvider",
    "evaluate_assertions",
    "has_passing_recent_run",
    "run_eval",
    "validate_assertions",
]
