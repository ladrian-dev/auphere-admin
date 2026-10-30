"""Las pasadas de la suite de un agente — spec 047, T086 (requisitos 21.4 a 21.7; research D18).

- Cada prueba corre **3 veces**: pasa con 3 de 3; con 1 o 2 es «Inestable»; con 0,
  falla; si ninguna pasada se pudo decidir, «No sé».
- Una prueba del sector marcada «No aplica» no corre y no cuenta (21.6).
- Las que fallan llevan «Por qué falló», con lo que se comprobó (21.5).
- La nota de la suite (de 0 a 100) es la de las pasadas decididas, y alimenta la puerta
  (requisito 23) y la certificación por agente (``certification.agent_verdict``).

Una pasada corre en el worker (``nexus_worker.jobs.handlers.agent_tests``); aquí se
crea, se apuntan sus resultados y se resume. Todo con el cliente del contexto.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import AgentConfig, AgentConfigStatus
from nexus_api.db.models.agent_spec import TEST_STOPS, AgentTest, AgentTestResult, AgentTestRun
from nexus_api.services.testing.suites import ensure_suite, list_tests

RUNS: Final = 3
TestStatus = Literal["passed", "flaky", "failed", "unknown", "not_run", "not_applicable"]


@dataclass(frozen=True)
class TestOutcome:
    test_id: uuid.UUID
    status: TestStatus
    passes: int
    decided: int
    why_failed: str | None = None
    #: Spec 047, enmienda (61.6): cada pasada de la última ejecución, con su
    #: conversación turno a turno y por qué terminó (``served_attempt``).
    attempts: tuple[dict[str, Any], ...] = ()


def status_of(attempts: Sequence[bool | None]) -> TestStatus:
    if not attempts:
        return "not_run"
    decided = [a for a in attempts if a is not None]
    if not decided:
        return "unknown"
    passes = sum(1 for a in decided if a)
    if passes == len(attempts):
        return "passed"
    if passes == 0:
        return "failed"
    return "flaky"


def why_failed(results: Sequence[AgentTestResult]) -> str | None:
    """«Por qué falló»: la primera explicación de una pasada que falló."""
    for r in sorted(results, key=lambda r: r.attempt):
        if r.passed is False and r.explanation:
            return r.explanation
    return None


async def latest_results(
    session: AsyncSession, agent_id: uuid.UUID
) -> dict[uuid.UUID, list[AgentTestResult]]:
    """Los resultados de la última pasada de cada prueba del agente."""
    tenant_id = require_current_tenant()
    rows = (
        await session.execute(
            sa.select(AgentTestResult, AgentTestRun.created_at)
            .join(
                AgentTestRun,
                sa.and_(
                    AgentTestRun.tenant_id == AgentTestResult.tenant_id,
                    AgentTestRun.id == AgentTestResult.run_id,
                ),
            )
            .where(
                AgentTestRun.tenant_id == tenant_id,
                AgentTestRun.agent_id == agent_id,
                # Spec 047 (39.9): una comprobación de calidad corre con otra
                # política de modelo; no es el estado de la suite del agente.
                AgentTestRun.reason != "certification",
            )
            .order_by(AgentTestRun.created_at.desc())
        )
    ).all()
    newest_run: dict[uuid.UUID, uuid.UUID] = {}
    out: dict[uuid.UUID, list[AgentTestResult]] = {}
    for result, _at in rows:
        run = newest_run.setdefault(result.test_id, result.run_id)
        if result.run_id == run:
            out.setdefault(result.test_id, []).append(result)
    return out


def served_turns(transcript: Sequence[Any]) -> list[dict[str, Any]]:
    """La conversación de una pasada como la enseña «Por qué falló»:
    ``[{"role": "customer" | "agent", "text", "actions": [frase]}]``. Las de antes
    de la enmienda solo traían ``bubbles``."""
    out: list[dict[str, Any]] = []
    for turn in transcript or ():
        if not isinstance(turn, Mapping) or turn.get("role") not in {"customer", "agent"}:
            continue
        text = turn.get("text")
        if not isinstance(text, str):
            text = " ".join(str(b) for b in turn.get("bubbles") or [])
        actions = [str(a) for a in turn.get("actions") or [] if isinstance(a, str)]
        out.append({"role": turn["role"], "text": text, "actions": actions})
    return out


def served_attempt(result: AgentTestResult) -> dict[str, Any]:
    return {
        "attempt": result.attempt,
        "passed": result.passed,
        "transcript": served_turns(result.transcript),
        "stop": result.stop,
    }


def outcome_of(test: AgentTest, results: Sequence[AgentTestResult]) -> TestOutcome:
    if test.not_applicable_reason:
        return TestOutcome(test.id, "not_applicable", 0, 0)
    ordered = sorted(results, key=lambda r: r.attempt)
    attempts = [r.passed for r in ordered]
    status = status_of(attempts)
    return TestOutcome(
        test.id,
        status,
        passes=sum(1 for a in attempts if a),
        decided=sum(1 for a in attempts if a is not None),
        why_failed=why_failed(results) if status in {"failed", "flaky"} else None,
        attempts=tuple(served_attempt(r) for r in ordered),
    )


def summarize(
    tests: Sequence[AgentTest], outcomes: Mapping[uuid.UUID, TestOutcome]
) -> dict[str, Any]:
    counts = {k: 0 for k in ("passed", "flaky", "failed", "unknown", "not_run", "not_applicable")}
    critical_failed: list[str] = []
    passes = decided = 0
    for test in tests:
        out = outcomes.get(test.id) or TestOutcome(test.id, "not_run", 0, 0)
        counts[out.status] += 1
        if out.status == "not_applicable":
            continue
        passes += out.passes
        decided += out.decided
        if test.critical and out.status != "passed":
            critical_failed.append(str(test.id))
    rate = round(100.0 * passes / decided, 2) if decided else None
    return {
        **counts,
        "total": len(tests),
        "stale": sum(1 for t in tests if t.stale and not t.not_applicable_reason),
        "critical_failed": critical_failed,
        "rate": rate,
    }


async def suite_view(
    session: AsyncSession, agent_id: uuid.UUID
) -> tuple[list[AgentTest], dict[uuid.UUID, TestOutcome], dict[str, Any]]:
    suite = await ensure_suite(session, agent_id)
    tests = await list_tests(session, suite)
    latest = await latest_results(session, agent_id)
    outcomes = {t.id: outcome_of(t, latest.get(t.id, [])) for t in tests}
    return tests, outcomes, summarize(tests, outcomes)


# ── una pasada ─────────────────────────────────────────────────────────────


async def target_version(session: AsyncSession, agent_id: uuid.UUID) -> AgentConfig | None:
    """Lo que se prueba: el borrador si lo hay; si no, la versión activa."""
    rows = (
        await session.scalars(
            sa.select(AgentConfig).where(
                AgentConfig.tenant_id == require_current_tenant(), AgentConfig.agent_id == agent_id
            )
        )
    ).all()
    staged = next((r for r in rows if r.status is AgentConfigStatus.STAGED), None)
    active = next((r for r in rows if r.status is AgentConfigStatus.ACTIVE), None)
    return staged or active


def tests_in_scope(
    tests: Iterable[AgentTest], *, scope: str, test_id: uuid.UUID | None = None
) -> list[AgentTest]:
    live = [t for t in tests if not t.not_applicable_reason and t.archived_at is None]
    if scope == "one":
        return [t for t in live if t.id == test_id]
    if scope == "affected":
        return [t for t in live if t.stale]
    return live


async def live_run(session: AsyncSession, agent_id: uuid.UUID) -> AgentTestRun | None:
    """La pasada viva del agente, si la hay: la de un trabajo ``tests`` en cola o en
    marcha, con la caducidad perezosa de ``jobs.get_job``. Spec 047, T217: como
    mucho una a la vez por agente; quien pide otra recibe esta."""
    from nexus_api.db.models.jobs import LIVE_JOB_STATUSES, Job
    from nexus_api.services import jobs as jobs_service

    tenant_id = require_current_tenant()
    candidates = (
        await session.scalars(
            sa.select(Job.id)
            .where(
                Job.tenant_id == tenant_id,
                Job.agent_id == agent_id,
                Job.kind == "tests",
                Job.status.in_(LIVE_JOB_STATUSES),
            )
            .order_by(Job.created_at.desc(), Job.id.desc())
        )
    ).all()
    for job_id in candidates:
        job = await jobs_service.get_job(session, job_id)
        if job is None or job.status not in LIVE_JOB_STATUSES:
            continue
        run = await session.scalar(
            sa.select(AgentTestRun).where(
                AgentTestRun.tenant_id == tenant_id, AgentTestRun.job_id == job.id
            )
        )
        if run is not None:
            return run
    return None


async def create_run(
    session: AsyncSession,
    *,
    agent_id: uuid.UUID,
    scope: str = "all",
    reason: str = "manual",
    paid_by: str = "partner",
    created_by: str | None = None,
    job_id: uuid.UUID | None = None,
    version: AgentConfig | None = None,
) -> AgentTestRun:
    version = version or await target_version(session, agent_id)
    run = AgentTestRun(
        id=uuid.uuid4(),
        tenant_id=require_current_tenant(),
        agent_id=agent_id,
        agent_config_id=version.id if version else None,
        model_policy=dict((version.policies or {}).get("model_policy") or {}) if version else None,
        scope=scope,
        reason=reason,
        status="queued",
        paid_by=paid_by,
        created_by=created_by,
        job_id=job_id,
    )
    session.add(run)
    await session.flush()
    return run


async def record_attempt(
    session: AsyncSession,
    *,
    run: AgentTestRun,
    test: AgentTest,
    attempt: int,
    passed: bool | None,
    dimensions: list[dict[str, Any]],
    explanation: str | None,
    final_state: dict[str, Any],
    transcript: list[dict[str, Any]],
    stop: str | None = None,
) -> None:
    """Una pasada, con su conversación y por qué terminó (61.3, 61.6)."""
    session.add(
        AgentTestResult(
            tenant_id=run.tenant_id,
            run_id=run.id,
            test_id=test.id,
            attempt=attempt,
            passed=passed,
            dimensions=dimensions,
            explanation=explanation,
            final_state=final_state,
            transcript=transcript,
            stop=stop if stop in TEST_STOPS else None,
        )
    )
    await session.flush()


async def finish_run(
    session: AsyncSession, run: AgentTestRun, *, ran: Sequence[AgentTest], cost_micros: int = 0
) -> dict[str, Any]:
    """Cierra la pasada: las pruebas corridas dejan de estar desactualizadas y la
    pasada guarda su resumen. Una comprobación de calidad (``certification``) se
    resume con sus propios resultados y no toca la suite del agente."""
    if run.reason == "certification":
        summary = await _own_summary(session, run, ran)
        run.summary = {**dict(run.summary or {}), **summary}
        run.status = "done"
        run.cost_micros = cost_micros
        run.finished_at = datetime.now(UTC)
        await session.flush()
        return dict(run.summary)
    for test in ran:
        test.stale = False
    _tests, _outcomes, summary = await suite_view(session, run.agent_id)
    run.summary = summary
    run.status = "done"
    run.cost_micros = cost_micros
    run.finished_at = datetime.now(UTC)
    await session.flush()
    return summary


async def _own_summary(
    session: AsyncSession, run: AgentTestRun, ran: Sequence[AgentTest]
) -> dict[str, Any]:
    rows = (
        await session.scalars(
            sa.select(AgentTestResult).where(
                AgentTestResult.tenant_id == run.tenant_id, AgentTestResult.run_id == run.id
            )
        )
    ).all()
    by_test: dict[uuid.UUID, list[AgentTestResult]] = {}
    for row in rows:
        by_test.setdefault(row.test_id, []).append(row)
    outcomes = {t.id: outcome_of(t, by_test.get(t.id, [])) for t in ran}
    return summarize(list(ran), outcomes)


__all__ = [
    "RUNS",
    "TestOutcome",
    "TestStatus",
    "create_run",
    "finish_run",
    "latest_results",
    "live_run",
    "outcome_of",
    "record_attempt",
    "status_of",
    "suite_view",
    "summarize",
    "target_version",
    "tests_in_scope",
    "why_failed",
]
