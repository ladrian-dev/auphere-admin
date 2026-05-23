"""Block P — eval suite services.

Roadmap E2: the runner drives each case through the REAL production
graph (``build_pipeline`` + dry-run MCP registry), not the Bloque O
sandbox. See :mod:`services.evals.pipeline_driver`.

Public surface:

- :func:`run_eval` — the runner the admin endpoint dispatches to. Takes
  a dataset + agent_config version and orchestrates: run each case
  through the real pipeline, apply assertions, persist results, update
  the run aggregate.
- :func:`build_eval_driver` / :func:`set_eval_llm_router` — the real-
  pipeline driver and its LLM-router test hook.
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
    JudgeReply,
    LiteLLMJudgeProvider,
)
from nexus_api.services.evals.pipeline_driver import (
    EvalDriverError,
    EvalPipelineDriver,
    PipelineTurnResult,
    build_eval_driver,
    set_eval_llm_router,
)
from nexus_api.services.evals.runner import (
    EvalRunOutcome,
    has_passing_recent_run,
    run_eval,
)

__all__ = [
    "AssertionResult",
    "AssertionValidationError",
    "EvalDriverError",
    "EvalPipelineDriver",
    "EvalRunOutcome",
    "FakeJudgeProvider",
    "JudgeError",
    "JudgeProvider",
    "JudgeReply",
    "LiteLLMJudgeProvider",
    "PipelineTurnResult",
    "build_eval_driver",
    "evaluate_assertions",
    "has_passing_recent_run",
    "run_eval",
    "set_eval_llm_router",
    "validate_assertions",
]
