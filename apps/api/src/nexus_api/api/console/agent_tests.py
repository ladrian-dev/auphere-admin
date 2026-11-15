"""Las pruebas de un agente en la consola — spec 047, T086 (requisito 21;
``contracts/console-api.md`` §4).

- ``GET …/agents/{agent_id}/tests``: toda la suite con el estado de cada prueba
  («Pasa», «Inestable», «Falla», «No sé», «No se pudo probar», «Sin ejecutar», «No
  aplica»), su «Por qué falló» y el resumen (21.5);
- ``POST …/tests`` [``agents:write``]: una prueba añadida por una persona (21.1);
- ``PATCH …/tests/{test_id}`` [``agents:write``]: editarla, o marcar una del
  sector «No aplica» con su razón (21.6);
- ``POST …/test-runs`` [``agents:write``] ``{scope: all | affected | failed | one,
  test_id?, dry_run?, confirmed_tests?}`` → ``202 {job_id}``: la pasada corre en el
  worker (21.4). Quién la paga, en ``services.testing.billing`` (requisito 68).
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Agent, AuditLog
from nexus_api.db.models.agent_spec import AgentTest
from nexus_api.services import jobs as jobs_service
from nexus_api.services.testing import billing
from nexus_api.services.testing import runs as runs_service
from nexus_api.services.testing.judge import judge_calibrated, unknown_state_keys
from nexus_api.services.testing.suites import add_test, bump, ensure_suite

from .agent_draft_routes import agent_in_path
from .deps import ClientScope, require_build_room, resolve_mapping

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/clients/{ref}/agents/{agent_id}")


class CriterionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    text: str = Field(min_length=1, max_length=300)


class TestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    persona: str = Field(default="", max_length=500)
    first_message: str = Field(min_length=1, max_length=2000)
    plan: str = Field(default="", max_length=1000)
    expected_state: dict[str, Any] = Field(default_factory=dict)
    criteria: list[CriterionIn] = Field(default_factory=list, max_length=6)
    critical: bool = False


class TestPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    first_message: str | None = Field(default=None, min_length=1, max_length=2000)
    plan: str | None = Field(default=None, max_length=1000)
    expected_state: dict[str, Any] | None = None
    criteria: list[CriterionIn] | None = Field(default=None, max_length=6)
    critical: bool | None = None
    #: «No aplica», con su razón; ``""`` lo quita.
    not_applicable_reason: str | None = Field(default=None, max_length=500)


class TestTurnOut(BaseModel):
    """Un turno de la conversación de una pasada (``runs.served_turns``)."""

    role: Literal["customer", "agent"]
    text: str
    #: Lo que habría hecho el agente en ese turno, en una frase cada cosa.
    actions: list[str] = Field(default_factory=list)


class TestAttemptOut(BaseModel):
    """Una pasada de la última ejecución (``runs.served_attempt``). Tipada para que
    el barrido de ``test_console_scope.py`` vea su conversación."""

    attempt: int
    passed: bool | None
    transcript: list[TestTurnOut] = Field(default_factory=list)
    stop: str | None = None


class TestOut(BaseModel):
    id: uuid.UUID
    kind: str
    name: str
    persona: str
    first_message: str
    plan: str
    expected_state: dict[str, Any]
    criteria: list[dict[str, Any]]
    critical: bool
    not_applicable_reason: str | None
    sector_test_ref: str | None
    stale: bool
    status: runs_service.TestStatus
    passes: int
    decided: int
    why_failed: str | None
    #: Con ``status = model_failed``: qué modelo no respondió. No hay nada que arreglar
    #: en el agente, y por eso no va en ``why_failed``.
    why_untested: str | None = None
    #: Spec 047, enmienda (58.4): ``generated`` si salió de la guía generada para
    #: este cliente («Generada»); si no, su ``kind``.
    origin: str
    #: Spec 047, enmienda (61.6): la conversación de la pasada que se enseña en «Por
    #: qué falló» (la primera que falló o, si ninguna, la primera) y por qué
    #: terminó; y todas las pasadas de la última ejecución.
    transcript: list[TestTurnOut] = Field(default_factory=list)
    stop: str | None = None
    attempts: list[TestAttemptOut] = Field(default_factory=list)


class SuiteOut(BaseModel):
    summary: dict[str, Any]
    tests: list[TestOut]
    judge_calibrated: bool
    allowed: list[Literal["add", "edit", "run"]]
    #: Requisito 68: quién pagaría ahora una pasada de todas las pruebas.
    next_full_pass: billing.Payer


class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["all", "affected", "failed", "one"] = "all"
    test_id: uuid.UUID | None = None
    #: Spec 047, enmienda (61.8): solo estimar el coste, sin encolar nada.
    dry_run: bool = False
    #: Requisito 68.4: cuántas pruebas vio y aceptó que cobrara la bolsa del cliente. Si ahora
    #: son más, lo que aceptó ya no es lo que costaría.
    confirmed_tests: int | None = Field(default=None, ge=1)


class RunOut(BaseModel):
    job_id: uuid.UUID
    run_id: uuid.UUID
    tests: int


def _judge_model() -> str:
    """El modelo que hace de juez en este despliegue, del registro de la plataforma
    (spec 059, 5.4): la calibración que cuenta es la suya, no la de cualquiera."""
    from nexus_worker.platform_models import default_models

    return str(default_models()["judge"])


def _error(code: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


def _measurable(expected: dict[str, Any] | None) -> None:
    """Quien escribe una prueba se entera si espera algo que nadie puede medir (66.8)."""
    unknown = unknown_state_keys(expected)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "unknown_state_key", "keys": unknown},
        )


def _test_out(test: AgentTest, outcome: runs_service.TestOutcome) -> TestOut:
    shown = next((a for a in outcome.attempts if a.get("passed") is False), None) or next(
        iter(outcome.attempts), None
    )
    return TestOut(
        id=test.id,
        kind=test.kind,
        name=test.name,
        persona=test.persona,
        first_message=test.first_message,
        plan=test.plan,
        expected_state=dict(test.expected_state or {}),
        criteria=list(test.criteria or []),
        critical=test.critical,
        not_applicable_reason=test.not_applicable_reason,
        sector_test_ref=test.sector_test_ref,
        stale=test.stale,
        status=outcome.status,
        passes=outcome.passes,
        decided=outcome.decided,
        why_failed=outcome.why_failed,
        why_untested=outcome.why_untested,
        origin="generated" if test.generated_guide_id is not None else test.kind,
        transcript=[TestTurnOut.model_validate(t) for t in shown["transcript"]] if shown else [],
        stop=shown["stop"] if shown else None,
        attempts=[TestAttemptOut.model_validate(a) for a in outcome.attempts],
    )


async def _suite_out(scope: ClientScope) -> SuiteOut:
    assert scope.agent_id is not None
    tests, outcomes, summary = await runs_service.suite_view(scope.session, scope.agent_id)
    writes = "agents:write" in scope.principal.permissions
    return SuiteOut(
        summary=summary,
        tests=[_test_out(t, outcomes[t.id]) for t in tests],
        judge_calibrated=await judge_calibrated(scope.session, model=_judge_model()),
        allowed=["add", "edit", "run"] if writes else [],
        next_full_pass=await billing.next_full_pass(
            scope.session,
            agent_id=scope.agent_id,
            partner_id=scope.principal.partner.id,
            tenant_id=scope.tenant.id,
        ),
    )


@router.get("/tests", response_model=SuiteOut)
async def get_tests(scope: ClientScope = Depends(agent_in_path("agents:read"))) -> SuiteOut:
    return await _suite_out(scope)


@router.post("/tests", response_model=SuiteOut, status_code=status.HTTP_201_CREATED)
async def add_person_test(
    body: TestIn, scope: ClientScope = Depends(agent_in_path("agents:write"))
) -> SuiteOut:
    assert scope.agent_id is not None
    _measurable(body.expected_state)
    suite = await ensure_suite(scope.session, scope.agent_id)
    item = body.model_dump()
    item["criteria"] = [c.model_dump() for c in body.criteria]
    await add_test(scope.session, suite, item, kind="person", by="partner_member")
    return await _suite_out(scope)


@router.patch("/tests/{test_id}", response_model=SuiteOut)
async def edit_test(
    test_id: uuid.UUID,
    body: TestPatchIn,
    scope: ClientScope = Depends(agent_in_path("agents:write")),
) -> SuiteOut:
    assert scope.agent_id is not None
    _measurable(body.expected_state)
    suite = await ensure_suite(scope.session, scope.agent_id)
    test = await scope.session.get(AgentTest, test_id)
    if test is None or test.suite_id != suite.id or test.archived_at is not None:
        raise _error("unknown_test", status.HTTP_404_NOT_FOUND)
    if body.not_applicable_reason is not None:
        reason = " ".join(body.not_applicable_reason.split())
        if reason and test.kind != "sector":
            # 21.6: solo una prueba del sector «no aplica»; las demás se borran.
            raise _error("not_applicable_only_sector", status.HTTP_422_UNPROCESSABLE_CONTENT)
        if reason and len(reason) < 3:
            raise _error("reason_required", status.HTTP_422_UNPROCESSABLE_CONTENT)
        test.not_applicable_reason = reason or None
    changes = ("name", "first_message", "plan", "expected_state", "critical", "criteria")
    if test.kind == "sector" and any(getattr(body, field) is not None for field in changes):
        # 21.6: las del sector se ven y pueden no aplicar, pero no se cambian. Quitarle
        # «crítica» a una sería saltarse la puerta de publicar.
        raise _error("sector_test_locked", status.HTTP_409_CONFLICT)
    for field in ("name", "first_message", "plan", "expected_state", "critical"):
        value = getattr(body, field)
        if value is not None:
            setattr(test, field, value)
            test.stale = True
    if body.criteria is not None:
        test.criteria = [c.model_dump() for c in body.criteria]
        test.stale = True
    # Requisito 66.3: desde aquí es de una persona; el sistema ya no la archiva ni la marca.
    test.created_by_kind = "partner_member"
    await bump(scope.session, suite)
    await scope.session.flush()
    return await _suite_out(scope)


@router.post(
    "/test-runs",
    response_model=RunOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={200: {"description": "dry_run: the estimate, nothing queued (61.8)"}},
)
async def start_run(
    body: RunIn,
    ref: str = Path(...),
    agent_id: uuid.UUID = Path(...),
    principal: ConsolePrincipal = Depends(require_console_principal("agents:write")),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> RunOut | JSONResponse:
    """Abre su propia transacción: el trabajo se encola **después** de confirmar.
    Con ``dry_run`` solo dice cuánto costaría y quién lo paga (61.8 y 68), sin encolar.

    Spec 047, T217: como mucho una pasada viva por agente. Si ya hay una, se
    devuelve esa y no se encola nada (como «Volver a leer»): la fila del agente se
    bloquea para que dos peticiones a la vez no lancen dos. La de «Guardar» no se
    devuelve, ``409 suite_running``: si la puerta para ese trabajo, esperarlo diría
    que la pasada no terminó, y sí terminó."""
    if body.scope == "one" and body.test_id is None:
        raise _error("test_required", status.HTTP_422_UNPROCESSABLE_CONTENT)
    mapping = await resolve_mapping(session, principal, ref)
    async with tenant_scoped_session(session, mapping.tenant_id):
        agent = await session.get(Agent, agent_id, with_for_update=not body.dry_run)
        if agent is None or agent.tenant_id != mapping.tenant_id or agent.status != "active":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent")
        suite = await ensure_suite(session, agent_id)
        from nexus_api.services.testing.sector_catalog import reconcile_suite
        from nexus_api.services.testing.suites import list_tests

        # Requisito 66: lo que se va a pagar es la suite de las herramientas de hoy. Una
        # estimación la cuenta igual y lo deshace: no escribe nada.
        target = await runs_service.target_version(session, agent_id)
        trial = await session.begin_nested() if body.dry_run else None
        if target is not None:
            await reconcile_suite(session, suite, tools=list(target.tools or []))
        tests = await list_tests(session, suite)
        chosen = await runs_service.tests_of_run(
            session, agent_id, tests, scope=body.scope, test_id=body.test_id
        )
        live_tests = runs_service.tests_in_scope(tests, scope="all")
        if trial is not None:
            await trial.rollback()
        if not chosen:
            raise _error("nothing_to_run", status.HTTP_409_CONFLICT)
        if target is None:
            raise _error("no_version", status.HTTP_409_CONFLICT)
        spent = await billing.first_pass_spent(session, agent_id)
        # Requisito 68: lo que cubre todas es una pasada completa, se llame como se llame.
        # Y repetir lo que no pasa solo es la primera si aún no se había hecho ninguna.
        everything = len(chosen) == len(live_tests)
        full = body.scope == "all" or (
            everything and (body.scope == "affected" or (body.scope == "failed" and not spent))
        )
        scope_of_run = "all" if full else body.scope
        payer: billing.Payer = (
            await billing.next_full_pass(
                session,
                agent_id=agent_id,
                partner_id=principal.partner.id,
                tenant_id=mapping.tenant_id,
            )
            if full
            else "auphere"
        )
        if payer == "auphere":
            await require_build_room(principal.partner.id)
        price = await billing.price_run(
            session,
            payer=payer,
            partner_id=principal.partner.id,
            tenant_id=mapping.tenant_id,
            agent_id=agent_id,
            tests=len(chosen),
        )
        if body.dry_run:
            from nexus_api.services.testing.estimate import estimate_for_agent

            estimate = await estimate_for_agent(session, agent_id, tests=len(chosen))
            return JSONResponse({"tests": len(chosen), **estimate.out(), **price.out()})
        live = await runs_service.live_run(session, agent_id)
        if live is not None and live.job_id is not None:
            if live.reason == "publish":
                raise _error("suite_running", status.HTTP_409_CONFLICT)
            only = (live.summary or {}).get("test_id") if live.scope == "one" else None
            running = await runs_service.tests_of_run(
                session,
                agent_id,
                tests,
                scope=live.scope,
                test_id=uuid.UUID(str(only)) if only else None,
            )
            return RunOut(job_id=live.job_id, run_id=live.id, tests=len(running))
        if payer == "client_bag":
            if price.charge is None:
                # Sin precio no se cobra a ciegas, y asignar saldo no lo arreglaría (68.5).
                raise _error("charge_unknown", status.HTTP_409_CONFLICT)
            if not price.fits:
                raise _error("client_bag_not_enough", status.HTTP_402_PAYMENT_REQUIRED)
            if body.confirmed_tests is None:
                raise _error("charge_not_confirmed", status.HTTP_409_CONFLICT)
            if len(chosen) > body.confirmed_tests:
                raise _error("charge_changed", status.HTTP_409_CONFLICT)
        job = await jobs_service.create_job(
            session, kind="tests", agent_id=agent_id, created_by=principal.user_id
        )
        run = await runs_service.create_run(
            session,
            agent_id=agent_id,
            scope=scope_of_run,
            reason="manual",
            paid_by=billing.PAID_BY[payer],
            created_by=principal.actor,
            job_id=job.id,
        )
        if body.test_id is not None:
            run.summary = {"test_id": str(body.test_id)}
        out = RunOut(job_id=job.id, run_id=run.id, tests=len(chosen))
        if payer == "client_bag":
            # Gastar lo de un cliente deja rastro, en la misma transacción: quién, qué agente
            # y cuánto se le dijo.
            session.add(
                AuditLog(
                    tenant_id=mapping.tenant_id,
                    actor=principal.actor,
                    action="agent.tests.charged_to_bag",
                    target=f"agent:{agent_id}",
                    after_json={
                        "run_id": str(run.id),
                        "tests": len(chosen),
                        "estimate": price.charge.out() if price.charge is not None else None,
                        "origin": "console",
                    },
                )
            )
    try:
        await jobs_service.enqueue_job(redis, job)
    except Exception as exc:  # la fila es la verdad: caduca y se relanza
        log.warning("console.tests.enqueue_failed", error=type(exc).__name__)
    return out


__all__ = ["router"]
