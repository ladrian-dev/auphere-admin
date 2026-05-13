"""Eval runner — drives a dataset against an agent_config version.

Per case:

1. Drive the Bloque O sandbox (``run_test_turn``) to produce the
   transcript + planned tool calls.
2. Apply deterministic assertions
   (:func:`services.evals.assertions.evaluate_assertions`).
3. For each ``judge_questions`` entry, ask the LLM judge and record
   the result. A judge failure (LLM error / malformed JSON) becomes
   an ``error`` assertion result.
4. The case ``status`` is ``pass`` if every assertion passed; ``fail``
   if any returned ``passed=False``; ``error`` if any was an error
   AND no fail dominated (errors are surfaced explicitly so the
   operator distinguishes "agent broke" from "judge broke").

The runner is synchronous-ish (await-driven) — cases are processed
serially. With ~20 cases per dataset and 2-3 LLM calls per case this
is ~30-60s end-to-end, acceptable for v1. Concurrency comes later
behind a flag.

Persistence: the caller (the endpoint) creates the :class:`EvalRun`
in ``running`` state, hands it to the runner, and the runner appends
:class:`EvalRunResult` rows + flips the run status at the end. We
break this into a small handful of helpers so each step is testable
in isolation.
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
    ToolCatalog,
)
from nexus_api.services.evals.assertions import (
    AssertionResult,
    evaluate_assertions,
)
from nexus_api.services.evals.judge import JudgeError, JudgeProvider
from nexus_api.services.test_agent import (
    PlannedToolCall,
    TestAgentProvider,
    TestTurnResult,
    run_test_turn,
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


def _planned_to_jsonable(planned: tuple[PlannedToolCall, ...]) -> list[dict[str, Any]]:
    return [
        {
            "name": p.name,
            "arguments": p.arguments,
            "iteration": p.iteration,
            "tool_call_id": p.tool_call_id,
        }
        for p in planned
    ]


def _transcript_to_jsonable(
    *,
    case_idx: int,
    case_name: str,
    user_message: str,
    history: list[dict[str, str]],
    turn_result: TestTurnResult,
) -> dict[str, Any]:
    return {
        "case_idx": case_idx,
        "case_name": case_name,
        "history": history,
        "user_message": user_message,
        "assistant_message": turn_result.assistant_message,
        "planned_tool_calls": _planned_to_jsonable(turn_result.planned_tool_calls),
        "iterations": turn_result.iterations,
        "model": turn_result.model,
        "latency_ms": turn_result.latency_ms,
    }


def _case_status(results: list[AssertionResult]) -> EvalCaseResultStatus:
    """Pass requires every assertion to pass. Otherwise: ``fail`` if
    any deterministic check failed; ``error`` if only judge errors
    showed up (the agent might be fine but the judge broke)."""
    any_fail = False
    any_error = False
    for r in results:
        if r.passed:
            continue
        if r.kind == "judge_error":
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


async def _build_tool_defs(session: AsyncSession, whitelist: list[str]) -> list[dict[str, Any]]:
    if not whitelist:
        return []
    rows = (
        (await session.execute(sa.select(ToolCatalog).where(ToolCatalog.name.in_(whitelist))))
        .scalars()
        .all()
    )
    by_name = {t.name: t for t in rows}
    defs: list[dict[str, Any]] = []
    for name in whitelist:
        tool = by_name.get(name)
        if tool is None:
            continue
        defs.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema or {"type": "object"},
                },
            }
        )
    return defs


async def _run_single_case(
    *,
    tenant_id: uuid.UUID,
    case: EvalCase,
    config: AgentConfig,
    tool_defs: list[dict[str, Any]],
    test_provider: TestAgentProvider,
    judge_provider: JudgeProvider,
    test_model: str,
    test_timeout_s: float,
    test_max_output_tokens: int,
    judge_timeout_s: float,
) -> tuple[EvalCaseResultStatus, dict[str, Any], list[dict[str, Any]], int]:
    """Drive one case. Returns ``(status, transcript_json,
    assertion_results_json, latency_ms)``.

    Wraps the sandbox call in a try/except so a single broken case
    (LLM 500, timeout, …) becomes an ``error`` row instead of taking
    the whole run down.
    """
    started = time.perf_counter()
    history = [dict(item) for item in case.history]

    try:
        turn_result = await run_test_turn(
            tenant_id=tenant_id,
            system_prompt=config.system_prompt_rendered,
            history=history,
            user_message=case.user_message,
            tool_defs=tool_defs,
            provider=test_provider,
            model=test_model,
            timeout_s=test_timeout_s,
            max_output_tokens=test_max_output_tokens,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        log.warning(
            "evals.case.sandbox_failed",
            tenant_id=str(tenant_id),
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
                    "kind": "sandbox_error",
                    "pass": False,
                    "detail": f"sandbox crashed: {exc}",
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
        planned_tool_calls=transcript["planned_tool_calls"],
    )

    for question in case.assertions.get("judge_questions") or []:
        try:
            reply = await judge_provider.judge(
                tenant_id=tenant_id,
                question=question,
                assistant_message=turn_result.assistant_message,
                planned_tool_calls=transcript["planned_tool_calls"],
                timeout_s=judge_timeout_s,
            )
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
    test_provider: TestAgentProvider,
    judge_provider: JudgeProvider,
    test_model: str = "anthropic/claude-sonnet-4-6",
    test_timeout_s: float = 30.0,
    test_max_output_tokens: int = 4_000,
    judge_timeout_s: float = 30.0,
    progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> EvalRunOutcome:
    """Execute the run. Updates the ``EvalRun`` row in place and
    inserts ``EvalRunResult`` rows as we go (one transaction per
    case) so a crash mid-run leaves partial results visible instead
    of nothing."""
    # The endpoint manages a single transaction for the request. We flush
    # progressively but NEVER commit mid-loop — committing here would
    # close the caller's begin()/commit() bracket and crash subsequent
    # SELECTs. The trade-off: partial results aren't visible to a
    # concurrent GET until the run finishes. Acceptable for the
    # synchronous v1 path; revisit when we move to async/queued runs.
    run.status = EvalRunStatus.RUNNING.value
    run.case_count = len(cases)
    await session.flush()

    tool_defs = await _build_tool_defs(session, list(agent_config.tools))

    pass_count = 0
    fail_count = 0
    error_count = 0

    for i, case in enumerate(cases):
        case_status, transcript, assertion_jsonable, latency_ms = await _run_single_case(
            tenant_id=tenant_id,
            case=case,
            config=agent_config,
            tool_defs=tool_defs,
            test_provider=test_provider,
            judge_provider=judge_provider,
            test_model=test_model,
            test_timeout_s=test_timeout_s,
            test_max_output_tokens=test_max_output_tokens,
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

        # Update aggregate columns so the UI can poll progress mid-run
        # (visible only within the same transaction in v1 — see comment
        # at the top of this function).
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
