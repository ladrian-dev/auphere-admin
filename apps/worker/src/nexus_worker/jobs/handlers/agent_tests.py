"""``tests`` — la suite de un agente (spec 047, T086; requisitos 21.3 a 21.8).

Corre cada prueba **3 veces** contra el mundo simulado (``nexus_worker.simulation``),
con el mismo grafo que el canal y la versión que se prueba (el borrador o la
activa). Cada pasada, con la agenda simulada sembrada de nuevo (61.7):

1. **una conversación** con un cliente simulado que sigue la persona y el plan de
   la prueba (``simulation/customer.py``, spec 047, enmienda del 2026-10-29,
   requisito 61): para al cumplir el plan, al despedirse, al pasar a una persona o
   a los 8 turnos del cliente, y ese tope sin cumplir el plan es un fallo;
2. se comprueba el **estado final**: la cita en la agenda de Reservas, el
   escalado y si se pidió un pago (61.4);
3. si hay juez, juzga **una dimensión por criterio**, con «No sé». Solo bloquea si
   está calibrado (``testing.judge.judge_calibrated``). Si es el modelo que
   respondió, no cuenta; si es de su familia, se avisa (61.5).

La conversación y por qué terminó se guardan en el resultado de la pasada
(``transcript`` y ``stop``) para «Por qué falló» (61.6). El cliente simulado y el
juez usan los modelos de la plataforma (``platform_models.py``).

Las pruebas corren en paralelo dentro del lote del cliente, nunca mezcladas con
otro cliente (garantía 7). Se mide en «Construcción y pruebas» (``source=tests``)
o fuera de las partidas si la paga Auphere (``certification``).

**Con tope** (spec 047, T217): «Construcción y pruebas» la paga Auphere hasta el
tope del partner. Antes de empezar cada prueba se vuelve a mirar la partida
(``build_budget.require_room_for_partner``); agotada, las que faltan no empiezan,
la empezada termina sus tres pasadas, la pasada queda ``failed`` con
``stopped = build_budget_exhausted`` y cuántas no empezaron, y el trabajo falla
con ese código. Cada pasada publica su consumo al terminar (un turno de uso por
pasada), así que la partida ve lo gastado por las anteriores.
"""

from __future__ import annotations

import asyncio
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
from nexus_worker.simulation.customer import (
    MAX_CUSTOMER_TURNS,
    Conversation,
    Customer,
    converse,
    judge_warnings,
    other_model,
)
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
#: El estado honesto de una suite que se paró sin partida (T217).
BUDGET_EXHAUSTED = "build_budget_exhausted"
#: Cuántas pasadas a la vez dentro del lote del cliente.
PARALLEL = 4

Judge = Callable[[list[dict[str, str]]], Awaitable[str]]
JudgeFactory = Callable[[uuid.UUID], Judge | None]
CustomerFactory = Callable[[uuid.UUID], Customer | None]


def judge_model() -> str:
    """El de la plataforma (requisito 64.2): ``NEXUS_LLM_JUDGE_MODEL`` o el de clasificar."""
    from nexus_worker.platform_models import platform_model

    return platform_model("judge")


def default_judge(tenant_id: uuid.UUID) -> Judge | None:
    """El juez, de otra familia que el agente; sin él en local (en memoria)."""
    from nexus_worker.config import get_worker_settings
    from nexus_worker.runtime.llm import LiteLLMProvider

    settings = get_worker_settings()
    if settings.llm_use_inmemory:
        return None
    provider = LiteLLMProvider(context_management=None)
    model = judge_model()

    async def judge(messages: list[dict[str, str]]) -> str:
        return await provider.acomplete(
            tenant_id=tenant_id, role="judge", model=model, messages=messages
        )

    return judge


TURN_LIMIT_WHY = (
    f"La conversación llegó a {MAX_CUSTOMER_TURNS} turnos del cliente sin cumplir su plan."
)


async def _attempt(
    *,
    ctx: JobContext,
    run: AgentTestRun,
    test: AgentTest,
    attempt: int,
    judge: Judge | None,
    judge_blocks: bool,
    router: Any,
    customer: Customer | None = None,
    judge_name: str | None = None,
    warnings: set[str] | None = None,
) -> bool | None:
    sm = get_sessionmaker()
    # 61.7: cada pasada empieza con la agenda simulada sembrada de nuevo.
    async with sm() as session, tenant_scoped_session(session, ctx.tenant_id):
        world = await seed_world(session, run.agent_id)
    conv = await open_conversation(ctx.tenant_id)
    assert run.agent_config_id is not None
    version_id = run.agent_config_id

    async def agent_turn(text: str) -> Any:
        return await run_turn(
            tenant_id=ctx.tenant_id,
            version_id=version_id,
            world=world,
            conv=conv,
            text=text,
            llm_router=router,
            model_policy=run.model_policy if run.reason == "certification" else None,
        )

    talk = Conversation(
        transcript=[
            {"role": "customer", "text": test.first_message, "bubbles": [test.first_message]}
        ]
    )
    try:
        talk = await converse(
            first_message=test.first_message,
            persona=test.persona,
            plan=test.plan,
            customer=customer,
            agent_turn=agent_turn,
            world=world,
        )
    except Exception as exc:  # una pasada que revienta falla, con su motivo
        log.warning("jobs.tests.attempt_failed", test_id=str(test.id), error=type(exc).__name__)
        passed: bool | None = False
        explanation: str | None = f"El agente no terminó el turno ({type(exc).__name__})."
        state = world.final_state()
        dims: list[dict[str, Any]] = []
    else:
        state = world.final_state()
        state_ok, checked = judge_service.check_state(test.expected_state or {}, state)
        said = judge_warnings(judge_model=judge_name, responding=talk.responding)
        if warnings is not None:
            warnings.update(said)
        verdict: judge_service.JudgeResult | None = None
        # 61.5: el juez no es el modelo que respondió; si lo es, su veredicto no cuenta.
        if judge is not None and test.criteria and "judge_same_model" not in said:
            raw = await judge(
                judge_service.judge_messages(
                    criteria=test.criteria,
                    transcript=talk.transcript,
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
        if talk.stop == "turn_limit":
            # 61.3: el tope sin cumplir el plan es un fallo, con ese motivo.
            passed = False
            explanation = TURN_LIMIT_WHY + (f" {explanation}" if explanation else "")
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
            transcript=talk.transcript,
            stop=talk.stop,
        )
    return passed


async def _partner_of(tenant_id: uuid.UUID) -> uuid.UUID | None:
    from nexus_api.db.models import Tenant

    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        partner_id: uuid.UUID | None = await session.scalar(
            sa.select(Tenant.partner_id).where(Tenant.id == tenant_id)
        )
    return partner_id


async def _has_room(partner_id: uuid.UUID) -> bool:
    """¿Le queda «Construcción y pruebas» al partner? (T217)."""
    from nexus_api.services.wallet import build_budget
    from nexus_api.services.wallet.bags import WalletError

    try:
        await build_budget.require_room_for_partner(partner_id)
    except WalletError:
        return False
    return True


async def run_suite(
    ctx: JobContext,
    run_id: uuid.UUID,
    *,
    judge: Judge | None,
    router: Any,
    customer: Customer | None = None,
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
    paid = run.paid_by == "partner"
    source = "tests" if paid else "certification"
    partner_id = await _partner_of(ctx.tenant_id) if paid else None
    gate = asyncio.Semaphore(PARALLEL)
    warnings: set[str] = set()
    judge_name = judge_model() if judge is not None else None
    # T217: whether each test may start, decided once (at its first pass to get
    # the gate) and in order; once the budget runs out, no other test starts.
    decisions: dict[uuid.UUID, bool] = {}
    deciding = asyncio.Lock()

    async def may_start(test: AgentTest) -> bool:
        if partner_id is None:
            return True
        async with deciding:
            if test.id not in decisions:
                stopped = any(not ok for ok in decisions.values())
                decisions[test.id] = not stopped and await _has_room(partner_id)
            return decisions[test.id]

    async def one(test: AgentTest, attempt: int) -> None:
        async with gate:
            if not await may_start(test):
                return
            # One usage turn per pass: what it spent reaches the budget before the
            # next test is decided (T217).
            async with usage_turn(
                tenant_id=ctx.tenant_id,
                turn_id=f"job:{ctx.job_id}:{test.id}:{attempt}",
                source=source,
                agent_id=run.agent_id,
            ):
                await _attempt(
                    ctx=ctx,
                    run=run,
                    test=test,
                    attempt=attempt,
                    judge=judge,
                    judge_blocks=judge_blocks,
                    router=router,
                    customer=customer,
                    judge_name=judge_name,
                    warnings=warnings,
                )
            await ctx.progress(
                step="running", block={"key": f"{test.id}:{attempt}", "test_id": str(test.id)}
            )

    await asyncio.gather(*(one(t, n) for t in tests for n in range(1, runs_service.RUNS + 1)))
    not_started = sum(1 for t in tests if decisions.get(t.id) is False)
    async with sm() as session, tenant_scoped_session(session, ctx.tenant_id):
        fresh = await session.get(AgentTestRun, run.id)
        assert fresh is not None
        live = [
            await session.get(AgentTest, t.id) for t in tests if decisions.get(t.id) is not False
        ]
        summary = await runs_service.finish_run(
            session, fresh, ran=[t for t in live if t is not None]
        )
        if not_started:
            # T217: an honest state — what did not start, and why.
            summary = {**summary, "stopped": BUDGET_EXHAUSTED, "not_started": not_started}
            fresh.summary = {
                **(fresh.summary or {}),
                "stopped": BUDGET_EXHAUSTED,
                "not_started": not_started,
            }
            fresh.status = "failed"
        elif fresh.reason == "certification":
            # Spec 047 (39.9): la comprobación de calidad decide y, si pasa,
            # certifica para el agente los modelos con los que conversaría.
            from nexus_api.services.agent_quality import finish_check

            summary = {**summary, "quality_check": await finish_check(session, fresh, summary)}
        if warnings:
            # 61.5: se avisa al operador (en el resumen de la pasada y en el log).
            summary = {**summary, "warnings": sorted(warnings)}
            fresh.summary = {**(fresh.summary or {}), "warnings": sorted(warnings)}
            log.warning(
                "tests.judge_warning",
                tenant_id=str(ctx.tenant_id),
                agent_id=str(run.agent_id),
                run_id=str(run.id),
                judge_model=judge_name,
                warnings=sorted(warnings),
            )
        reason, sections = fresh.reason, list((fresh.summary or {}).get("sections", []))
    if not_started:
        log.warning(
            "suite.stopped",
            tenant_id=str(ctx.tenant_id),
            agent_id=str(run.agent_id),
            run_id=str(run.id),
            reason=BUDGET_EXHAUSTED,
            not_started=not_started,
        )
        raise JobFailed(BUDGET_EXHAUSTED)
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


def customer_model() -> str:
    """El del cliente simulado (requisito 64.2): ``NEXUS_LLM_CUSTOMER_SIM_MODEL`` o el
    de clasificar."""
    from nexus_worker.platform_models import platform_model

    return platform_model("customer_sim")


def default_customer(tenant_id: uuid.UUID) -> Customer | None:
    """El cliente simulado de verdad; sin él en local (en memoria): una pasada es
    entonces un solo turno, como antes de la enmienda."""
    from nexus_worker.config import get_worker_settings
    from nexus_worker.runtime.llm import LiteLLMProvider

    settings = get_worker_settings()
    if settings.llm_use_inmemory:
        return None
    provider = LiteLLMProvider(context_management=None)
    model = customer_model()
    alternatives = [judge_model(), settings.llm_classify_model, settings.llm_respond_model]

    async def customer(messages: list[dict[str, str]], *, avoid_model: str | None = None) -> str:
        chosen = other_model(model, avoid=avoid_model, alternatives=alternatives)
        return await provider.acomplete(
            tenant_id=tenant_id, role="customer_sim", model=chosen, messages=messages
        )

    return customer


def make_agent_tests_handler(
    *,
    judge_factory: JudgeFactory | None = None,
    router_factory: Callable[[], Any] | None = None,
    customer_factory: CustomerFactory | None = None,
) -> JobHandler:
    make_judge = judge_factory or default_judge
    make_router = router_factory or default_router
    make_customer = customer_factory or default_customer

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
            ctx,
            run_id,
            judge=make_judge(ctx.tenant_id),
            router=make_router(),
            customer=make_customer(ctx.tenant_id),
        )
        return JobOutcome(result={"run_id": str(run_id), "summary": summary})

    return handle


def register(registry: JobRegistry = default_registry) -> None:
    if registry.get(KIND) is None:
        registry.register(KIND, make_agent_tests_handler(), timeout_s=TIMEOUT_S)


register()


__all__ = [
    "BUDGET_EXHAUSTED",
    "KIND",
    "PARALLEL",
    "customer_model",
    "default_customer",
    "default_judge",
    "make_agent_tests_handler",
    "register",
    "run_suite",
    "tell_failing",
]
