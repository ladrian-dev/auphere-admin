"""Eval runner — drives a dataset against an agent_config version.

Roadmap E2: the runner executes each case through the **real production
graph** (``build_pipeline`` with a dry-run MCP registry — the same path
the QA Playground runs), NOT the Bloque O sandbox. The promotion gate
now validates the code that actually runs in production.

Per case:

1. Drive the real compiled graph via :class:`EvalPipelineDriver` — real
   ReAct loop, real tool dispatch, real history. Side-effecting tools
   are intercepted (dry_run); read tools run for real.
2. Apply deterministic assertions
   (:func:`services.evals.assertions.evaluate_assertions`).
3. For each ``judge_questions`` entry, ask the LLM judge. A ``pass`` /
   ``fail`` verdict becomes a ``judge_question`` assertion; an
   ``unknown`` verdict becomes a non-passing ``judge_unknown``
   assertion; an LLM error becomes a ``judge_error`` assertion.
4. The case ``status`` is ``pass`` if every assertion passed; ``fail``
   if any deterministic check failed; ``error`` if only judge
   errors/unknowns showed up (the agent might be fine but the eval was
   inconclusive — surfaced explicitly, never silently passed).

Cases are processed serially. Each case is one real graph turn (up to
``MAX_TOOL_ITERATIONS`` LLM calls), so a dataset run is slower than the
old sandbox path — acceptable for a pre-promotion gate. Concurrency
comes later behind a flag.

Persistence: the caller (the endpoint) creates the :class:`EvalRun`,
hands it to the runner, and the runner appends :class:`EvalRunResult`
rows + flips the run status at the end. The per-case conversation
seeding/cleanup runs in the driver's OWN sessions (it must commit so the
graph — which opens its own sessions — can read the seeded history); the
caller's transaction is only ever used for the run/result rows.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    AgentConfig,
    EvalCase,
    EvalCaseResultStatus,
    EvalDataset,
    EvalRun,
    EvalRunResult,
    EvalRunStatus,
)
from nexus_api.services.evals.assertions import (
    AssertionResult,
    evaluate_assertions,
)
from nexus_api.services.evals.judge import JudgeError, JudgeProvider
from nexus_api.services.evals.pipeline_driver import (
    EvalPipelineDriver,
    PipelineTurnResult,
    build_eval_driver,
)

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class EvalRunOutcome:
    run_id: uuid.UUID
    status: EvalRunStatus
    case_count: int
    pass_count: int
    fail_count: int
    error_count: int
    pass_rate: Decimal


def _transcript_to_jsonable(
    *,
    case_idx: int,
    case_name: str,
    user_message: str,
    history: list[dict[str, str]],
    turn_result: PipelineTurnResult,
) -> dict[str, Any]:
    return {
        "case_idx": case_idx,
        "case_name": case_name,
        "history": history,
        "user_message": user_message,
        "assistant_message": turn_result.assistant_message,
        # Real tool calls executed by the graph (envelopes flattened to
        # ``{name, arguments, status, result}``) — not sandbox plans.
        "tool_calls": list(turn_result.tool_calls),
        "intent": turn_result.intent,
        "model": turn_result.model,
        "latency_ms": turn_result.latency_ms,
    }


def _case_status(results: list[AssertionResult]) -> EvalCaseResultStatus:
    """Pass requires every assertion to pass. Otherwise: ``fail`` if any
    deterministic check failed; ``error`` if only judge errors / unknown
    verdicts showed up (the agent might be fine but the eval was
    inconclusive — surface it, never silently pass)."""
    any_fail = False
    any_error = False
    for r in results:
        if r.passed:
            continue
        if r.kind in ("judge_error", "judge_unknown"):
            any_error = True
        else:
            any_fail = True
    if any_fail:
        return EvalCaseResultStatus.FAIL
    if any_error:
        return EvalCaseResultStatus.ERROR
    return EvalCaseResultStatus.PASS


def _aggregate_status(
    case_count: int,
    pass_count: int,
    fail_count: int,
    error_count: int,
    pass_threshold: Decimal,
) -> tuple[EvalRunStatus, Decimal]:
    if case_count == 0:
        return EvalRunStatus.ERROR, Decimal("0.000")
    pass_rate = (Decimal(pass_count) / Decimal(case_count)).quantize(Decimal("0.001"))
    if error_count > 0 and error_count >= fail_count:
        return EvalRunStatus.ERROR, pass_rate
    if pass_rate >= pass_threshold:
        return EvalRunStatus.PASSED, pass_rate
    return EvalRunStatus.FAILED, pass_rate


async def _run_single_case(
    *,
    case: EvalCase,
    driver: EvalPipelineDriver,
    judge_provider: JudgeProvider,
    judge_timeout_s: float,
) -> tuple[EvalCaseResultStatus, dict[str, Any], list[dict[str, Any]], int]:
    """Drive one case through the real graph. Returns ``(status,
    transcript_json, assertion_results_json, latency_ms)``.

    Wraps the graph call in a try/except so a single broken case (LLM
    500, timeout, …) becomes an ``error`` row instead of taking the
    whole run down.
    """
    started = time.perf_counter()
    history = [dict(item) for item in case.history]

    try:
        turn_result = await driver.run_case(
            history=history,
            user_message=case.user_message,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        log.warning(
            "evals.case.pipeline_failed",
            tenant_id=str(driver.tenant_id),
            case_id=str(case.id),
            error=str(exc),
        )
        return (
            EvalCaseResultStatus.ERROR,
            {
                "case_idx": case.idx,
                "case_name": case.name,
                "user_message": case.user_message,
                "error": str(exc),
            },
            [
                {
                    "kind": "pipeline_error",
                    "pass": False,
                    "detail": f"pipeline crashed: {exc}",
                    "payload": {},
                }
            ],
            latency_ms,
        )

    transcript = _transcript_to_jsonable(
        case_idx=case.idx,
        case_name=case.name,
        user_message=case.user_message,
        history=history,
        turn_result=turn_result,
    )

    assertion_results: list[AssertionResult] = evaluate_assertions(
        assertions=case.assertions,
        assistant_message=turn_result.assistant_message,
        planned_tool_calls=transcript["tool_calls"],
    )

    for question in case.assertions.get("judge_questions") or []:
        try:
            reply = await judge_provider.judge(
                tenant_id=driver.tenant_id,
                question=question,
                assistant_message=turn_result.assistant_message,
                tool_calls=transcript["tool_calls"],
                timeout_s=judge_timeout_s,
            )
            if reply.is_unknown:
                # E2.2 — an "unknown" verdict is NOT a pass. It surfaces
                # as a non-passing assertion so the case lands on
                # ``error``: the eval was inconclusive, not the agent.
                assertion_results.append(
                    AssertionResult(
                        kind="judge_unknown",
                        passed=False,
                        detail=reply.reason or "judge could not decide from the transcript",
                        payload={"question": question},
                    )
                )
            else:
                assertion_results.append(
                    AssertionResult(
                        kind="judge_question",
                        passed=reply.passed,
                        detail=reply.reason or ("pass" if reply.passed else "fail"),
                        payload={"question": question},
                    )
                )
        except JudgeError as exc:
            assertion_results.append(
                AssertionResult(
                    kind="judge_error",
                    passed=False,
                    detail=str(exc),
                    payload={"question": question},
                )
            )

    status = _case_status(assertion_results)
    latency_ms = int((time.perf_counter() - started) * 1000)
    return (
        status,
        transcript,
        [r.to_jsonable() for r in assertion_results],
        latency_ms,
    )


async def run_eval(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    run: EvalRun,
    dataset: EvalDataset,
    cases: list[EvalCase],
    agent_config: AgentConfig,
    judge_provider: JudgeProvider,
    llm_router: Any | None = None,
    judge_timeout_s: float = 30.0,
    case_timeout_s: float = 120.0,
    progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> EvalRunOutcome:
    """Execute the run against the REAL pipeline. Updates the ``EvalRun``
    row in place and inserts ``EvalRunResult`` rows as we go.

    The endpoint manages a single transaction for the request. We flush
    progressively but NEVER commit on ``session`` mid-loop — committing
    here would close the caller's begin()/commit() bracket. The per-case
    conversation seeding/cleanup uses the driver's OWN sessions (which DO
    commit, independently) so the graph can read the seeded history.

    ``llm_router`` is injectable for tests (an ``InMemoryProvider``
    router); production leaves it ``None`` and the driver builds a real
    LiteLLM router.
    """
    run.status = EvalRunStatus.RUNNING.value
    run.case_count = len(cases)
    await session.flush()

    # Build the driver once — the pinned agent_config is fixed for the
    # whole run. A setup failure (empty prompt, graph build) raises here
    # and the endpoint records the run as ``error``.
    driver = await build_eval_driver(
        tenant_id=tenant_id,
        agent_config=agent_config,
        llm_router=llm_router,
        case_timeout_s=case_timeout_s,
    )

    pass_count = 0
    fail_count = 0
    error_count = 0

    for i, case in enumerate(cases):
        case_status, transcript, assertion_jsonable, latency_ms = await _run_single_case(
            case=case,
            driver=driver,
            judge_provider=judge_provider,
            judge_timeout_s=judge_timeout_s,
        )

        result = EvalRunResult(
            tenant_id=tenant_id,
            run_id=run.id,
            case_id=case.id,
            case_idx=case.idx,
            case_name=case.name,
            status=case_status.value,
            transcript=transcript,
            assertion_results=assertion_jsonable,
            latency_ms=latency_ms,
            created_at=datetime.now(UTC),
        )
        session.add(result)

        if case_status is EvalCaseResultStatus.PASS:
            pass_count += 1
        elif case_status is EvalCaseResultStatus.FAIL:
            fail_count += 1
        else:
            error_count += 1

        run.pass_count = pass_count
        run.fail_count = fail_count
        run.error_count = error_count
        await session.flush()

        if progress is not None:
            await progress(i + 1, len(cases))

    run_status, pass_rate = _aggregate_status(
        case_count=run.case_count,
        pass_count=pass_count,
        fail_count=fail_count,
        error_count=error_count,
        pass_threshold=dataset.pass_threshold,
    )
    run.status = run_status.value
    run.pass_rate = pass_rate
    run.finished_at = datetime.now(UTC)
    await session.flush()

    log.info(
        "evals.run.complete",
        tenant_id=str(tenant_id),
        run_id=str(run.id),
        dataset_id=str(run.dataset_id),
        agent_config_version=run.agent_config_version,
        status=run.status,
        case_count=run.case_count,
        pass_count=pass_count,
        fail_count=fail_count,
        error_count=error_count,
        pass_rate=str(pass_rate),
    )

    return EvalRunOutcome(
        run_id=run.id,
        status=run_status,
        case_count=run.case_count,
        pass_count=pass_count,
        fail_count=fail_count,
        error_count=error_count,
        pass_rate=pass_rate,
    )


async def has_passing_recent_run(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    agent_config_version: int,
    window_hours: int = 24,
) -> EvalRun | None:
    """Promotion-gate helper. Returns the most recent ``passed``
    :class:`EvalRun` for this tenant + version within the time
    window, or ``None`` if no qualifying run exists."""
    cutoff = datetime.now(UTC).replace(microsecond=0).timestamp() - (window_hours * 3600)
    cutoff_dt = datetime.fromtimestamp(cutoff, tz=UTC)
    row = (
        await session.execute(
            sa.select(EvalRun)
            .where(EvalRun.tenant_id == tenant_id)
            .where(EvalRun.agent_config_version == agent_config_version)
            .where(EvalRun.status == EvalRunStatus.PASSED.value)
            .where(EvalRun.finished_at.is_not(None))
            .where(EvalRun.finished_at >= cutoff_dt)
            .order_by(EvalRun.finished_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return row
