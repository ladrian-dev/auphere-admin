"""``tests`` — la suite de un agente (spec 047, T086; requisitos 21.3 a 21.8).

Corre cada prueba **3 veces** contra el mundo simulado (``nexus_worker.simulation``),
con el mismo grafo que el canal y la versión que se prueba (el borrador o la
activa). Cada pasada:

1. un cliente simulado escribe el primer mensaje y el agente contesta;
2. se comprueba el **estado final** (que la cita existe, que se pasó al equipo);
3. si hay juez, juzga **una dimensión por criterio**, con «No sé». Solo bloquea si
   está calibrado (``testing.judge.judge_calibrated``).

Las pruebas corren en paralelo dentro del lote del cliente, nunca mezcladas con
otro cliente (garantía 7). Se mide en «Construcción y pruebas» (``source=tests``)
o fuera de las partidas si la paga Auphere (``certification``).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.agent_spec import AgentTest, AgentTestRun
from nexus_api.services.testing import judge as judge_service
from nexus_api.services.testing import runs as runs_service
from nexus_api.services.testing.suites import ensure_suite, list_tests

from nexus_worker.jobs.registry import (
    JobContext,
    JobFailed,
    JobHandler,
    JobOutcome,
    JobRegistry,
    default_registry,
)
from nexus_worker.metering.collector import usage_turn
from nexus_worker.simulation.runner import (
    close_conversation,
    default_router,
    open_conversation,
    run_turn,
)
from nexus_worker.simulation.world import seed_world

log = structlog.get_logger(__name__)

KIND = "tests"
TIMEOUT_S = 600.0
#: Cuántas pasadas a la vez dentro del lote del cliente.
PARALLEL = 4

Judge = Callable[[list[dict[str, str]]], Awaitable[str]]
JudgeFactory = Callable[[uuid.UUID], Judge | None]


def default_judge(tenant_id: uuid.UUID) -> Judge | None:
    """El juez, de otra familia que el agente; sin él en local (en memoria)."""
    from nexus_worker.config import get_worker_settings
    from nexus_worker.runtime.llm import LiteLLMProvider

    settings = get_worker_settings()
    if settings.llm_use_inmemory:
        return None
    provider = LiteLLMProvider(context_management=None)
    model = os.environ.get("NEXUS_LLM_JUDGE_MODEL") or settings.llm_classify_model

    async def judge(messages: list[dict[str, str]]) -> str:
        return await provider.acomplete(
            tenant_id=tenant_id, role="judge", model=model, messages=messages
        )

    return judge


async def _attempt(
    *,
    ctx: JobContext,
    run: AgentTestRun,
    test: AgentTest,
    attempt: int,
    judge: Judge | None,
    judge_blocks: bool,
    router: Any,
) -> bool | None:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, ctx.tenant_id):
        world = await seed_world(session, run.agent_id)
    conv = await open_conversation(ctx.tenant_id)
    transcript: list[dict[str, Any]] = [{"role": "customer", "bubbles": [test.first_message]}]
    try:
        assert run.agent_config_id is not None
        outcome = await run_turn(
            tenant_id=ctx.tenant_id,
            version_id=run.agent_config_id,
            world=world,
            conv=conv,
            text=test.first_message,
            llm_router=router,
            model_policy=run.model_policy if run.reason == "certification" else None,
        )
        transcript.append({"role": "agent", "bubbles": outcome.bubbles})
    except Exception as exc:  # una pasada que revienta falla, con su motivo
        log.warning("jobs.tests.attempt_failed", test_id=str(test.id), error=type(exc).__name__)
        passed: bool | None = False
        explanation: str | None = f"El agente no terminó el turno ({type(exc).__name__})."
        state = world.final_state()
        dims: list[dict[str, Any]] = []
    else:
        state = world.final_state()
        state_ok, checked = judge_service.check_state(test.expected_state or {}, state)
        verdict: judge_service.JudgeResult | None = None
        if judge is not None and test.criteria:
            raw = await judge(
                judge_service.judge_messages(
                    criteria=test.criteria,
                    transcript=transcript,
                    actions=[a.phrase for a in world.actions],
                )
            )
            verdict = judge_service.parse_judge(raw, test.criteria)
        passed = judge_service.attempt_passed(state_ok, verdict, judge_blocks=judge_blocks)
        dims = [d.to_json() for d in verdict.dimensions] if verdict else []
        reasons = [c for c in checked if not c.endswith(": ok")]
        if verdict is not None:
            reasons += [f"{d.key}: {d.why}" for d in verdict.dimensions if d.verdict == "fail"]
        explanation = "Se comprobó " + "; ".join(reasons) if passed is False and reasons else None
    finally:
        await close_conversation(ctx.tenant_id, conv)
    async with sm() as session, tenant_scoped_session(session, ctx.tenant_id):
        await runs_service.record_attempt(
            session,
            run=run,
            test=test,
            attempt=attempt,
            passed=passed,
            dimensions=dims,
            explanation=explanation,
            final_state=state,
            transcript=transcript,
        )
    return passed


async def run_suite(
    ctx: JobContext,
    run_id: uuid.UUID,
    *,
    judge: Judge | None,
    router: Any,
) -> dict[str, Any]:
    """Corre la pasada ``run_id`` entera y devuelve su resumen. La usan el
    trabajo ``tests`` y el de publicar (que prueba el borrador antes de decidir)."""
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, ctx.tenant_id):
        run = await session.get(AgentTestRun, run_id)
        if run is None or run.agent_config_id is None:
            raise JobFailed("no_version")
        run.status = "running"
        suite = await ensure_suite(session, run.agent_id)
        scope_test = None
        if run.scope == "one":
            scope_test = uuid.UUID(str((run.summary or {}).get("test_id")))
        tests = runs_service.tests_in_scope(
            await list_tests(session, suite), scope=run.scope, test_id=scope_test
        )
        judge_blocks = await judge_service.judge_calibrated(session)
        session.expunge_all()
    source = "tests" if run.paid_by == "partner" else "certification"
    gate = asyncio.Semaphore(PARALLEL)

    async def one(test: AgentTest, attempt: int) -> None:
        async with gate:
            await _attempt(
                ctx=ctx,
                run=run,
                test=test,
                attempt=attempt,
                judge=judge,
                judge_blocks=judge_blocks,
                router=router,
            )
            await ctx.progress(
                step="running", block={"key": f"{test.id}:{attempt}", "test_id": str(test.id)}
            )

    async with usage_turn(
        tenant_id=ctx.tenant_id,
        turn_id=f"job:{ctx.job_id}",
        source=source,
        agent_id=run.agent_id,
    ):
        await asyncio.gather(*(one(t, n) for t in tests for n in range(1, runs_service.RUNS + 1)))
    async with sm() as session, tenant_scoped_session(session, ctx.tenant_id):
        fresh = await session.get(AgentTestRun, run.id)
        assert fresh is not None
        live = [await session.get(AgentTest, t.id) for t in tests]
        summary = await runs_service.finish_run(
            session, fresh, ran=[t for t in live if t is not None]
        )
        if fresh.reason == "certification":
            # Spec 047 (39.9): la comprobación de calidad decide y, si pasa,
            # certifica para el agente los modelos con los que conversaría.
            from nexus_api.services.agent_quality import finish_check

            summary = {**summary, "quality_check": await finish_check(session, fresh, summary)}
        reason, sections = fresh.reason, list((fresh.summary or {}).get("sections", []))
    await tell_failing(
        ctx.tenant_id, run.agent_id, reason=reason, failed=summary.get("failed"), sections=sections
    )
    log.info(
        "suite.run",
        tenant_id=str(ctx.tenant_id),
        agent_id=str(run.agent_id),
        run_id=str(run.id),
        version_id=str(run.agent_config_id) if run.agent_config_id else None,
        passed=summary.get("passed"),
        failed=summary.get("failed"),
        flaky=summary.get("flaky"),
    )
    return dict(summary)


async def tell_failing(
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    reason: str | None,
    failed: Any,
    sections: list[str],
) -> None:
    """Requisito 13.7: la pasada en segundo plano que lanzó un cambio de la ficha
    deja pruebas en rojo → ``agent.tests.failing`` al partner, una por agente y
    día (``events.md`` §3). Las demás pasadas las lanzó alguien que ya mira."""
    if reason != "business_change" or not failed:
        return
    from nexus_api.services.channel_config import announce

    await announce(
        tenant_id=tenant_id,
        kind="agent.tests.failing",
        severity="warning",
        data={"agent_id": str(agent_id), "failed": int(failed), "sections": sections},
        dedupe_key=f"agent.tests.failing:{agent_id}:{datetime.now(UTC).date().isoformat()}",
    )


def make_agent_tests_handler(
    *, judge_factory: JudgeFactory | None = None, router_factory: Callable[[], Any] | None = None
) -> JobHandler:
    make_judge = judge_factory or default_judge
    make_router = router_factory or default_router

    async def handle(ctx: JobContext) -> JobOutcome:
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, ctx.tenant_id):
            run_id = await session.scalar(
                sa.select(AgentTestRun.id).where(
                    AgentTestRun.tenant_id == ctx.tenant_id, AgentTestRun.job_id == ctx.job_id
                )
            )
        if run_id is None:
            raise JobFailed("no_version")
        summary = await run_suite(
            ctx, run_id, judge=make_judge(ctx.tenant_id), router=make_router()
        )
        return JobOutcome(result={"run_id": str(run_id), "summary": summary})

    return handle


def register(registry: JobRegistry = default_registry) -> None:
    if registry.get(KIND) is None:
        registry.register(KIND, make_agent_tests_handler(), timeout_s=TIMEOUT_S)


register()


__all__ = [
    "KIND",
    "PARALLEL",
    "default_judge",
    "make_agent_tests_handler",
    "register",
    "run_suite",
    "tell_failing",
]
