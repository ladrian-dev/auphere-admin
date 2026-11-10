"""Ejecutar la certificación: por clase y por agente (spec 047, T143 y T144).

Quien llama pone **cómo** se ejecuta un caso (``run_case``) o una prueba de la
suite (``run_test``): el driver de evaluación con el despliegue fijado y el juez
de la tarea ``judge``. Aquí van las reglas que no dependen de eso:

- **tres repeticiones** de cada caso (pass^3, requisito 42.1);
- **el juez es de otra familia** que el despliegue juzgado (42.5): con la misma
  familia, o sin saberla, no se certifica;
- **un lote es de un solo cliente** (garantía 7, requisito 40.12): la suite de un
  agente nunca lleva pruebas de otro cliente;
- **en segundo plano** (42.4) se certifican, para un agente con perfil, los
  despliegues más baratos que el suyo que ya pasaron la batería, y paga Auphere.

Lo que se guarda y cuándo caduca: ``nexus_api.services.certification``. Cada
llamada a un modelo de una certificación lleva su tarea (la del caso o ``judge``)
y se mide con el origen de quien paga (``payer_for(...).usage_source``).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from nexus_api.services.certification import (
    AgentSuiteResult,
    AgentVerdict,
    ClassResult,
    SuiteCase,
    background_candidates,
    record_agent_certification,
)
from nexus_api.services.router_catalog import CatalogSnapshot, Deployment
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_worker.certification.battery import Battery, BatteryCase
from nexus_worker.certification.metrics import CaseRun, class_metrics, quality

#: Repeticiones de cada caso y de cada prueba (pass^3).
RUNS_PER_CASE = 3

CaseRunner = Callable[[BatteryCase, Deployment, int], Awaitable[CaseRun]]


class SameFamilyJudge(ValueError):
    """El juez y el juzgado son de la misma familia (o no se sabe)."""


class SingleClientBatch(ValueError):
    """Una suite con pruebas de otro cliente: el lote no se arma."""


def require_other_family(judge: Deployment, judged: Deployment) -> None:
    if judge.family is None or judged.family is None or judge.family == judged.family:
        raise SameFamilyJudge(
            f"juez {judge.key} ({judge.family}) para {judged.key} ({judged.family})"
        )


async def certify_class(
    battery: Battery,
    deployment: Deployment,
    task: str,
    *,
    run_case: CaseRunner,
    judge: Deployment,
) -> ClassResult:
    """Pasa la batería de ``task`` a ``deployment``: tres veces cada caso.

    Secuencial a propósito: el catálogo es de pago, y una batería no tiene prisa
    pero sí cuotas que respetar. La batería no lleva datos de clientes."""
    require_other_family(judge, deployment)
    cases = battery.for_task(task)
    if not cases:
        raise ValueError(f"la batería v{battery.version} no tiene casos de {task}")
    runs: dict[str, list[CaseRun]] = {}
    for case in cases:
        runs[case.id] = [
            await run_case(case, deployment, attempt) for attempt in range(RUNS_PER_CASE)
        ]
    metrics = class_metrics(runs)
    return ClassResult(
        task=task,
        battery_version=battery.version,
        metrics=metrics,
        quality=quality(metrics, battery.weights),
        threshold=battery.threshold,
        judge=judge.key,
    )


@dataclass(frozen=True)
class SuiteTest:
    """Una prueba de la suite de un agente (requisito 21)."""

    tenant_id: uuid.UUID
    test_id: str
    critical: bool
    weight: float = 1.0


TestRunner = Callable[[SuiteTest, Deployment, int], Awaitable[bool]]


async def certify_agent(
    *,
    tenant_id: uuid.UUID,
    tests: Sequence[SuiteTest],
    deployment: Deployment,
    reference_score: float,
    reference_deployment: str,
    run_test: TestRunner,
) -> AgentSuiteResult:
    """La suite del agente con ``deployment``, tres veces cada prueba.

    La nota (de 0 a 100) pondera cada prueba por la fracción de repeticiones que
    pasaron. El veredicto (críticas 3 de 3 y 2 puntos como mucho) lo da
    ``certification.agent_verdict`` al guardarla."""
    strangers = sorted(t.test_id for t in tests if t.tenant_id != tenant_id)
    if strangers:
        raise SingleClientBatch(f"pruebas de otro cliente en la suite: {strangers}")
    if not tests:
        raise ValueError("una suite vacía no certifica nada")
    cases: list[SuiteCase] = []
    earned = 0.0
    total = 0.0
    for test in tests:
        passes = 0
        for attempt in range(RUNS_PER_CASE):
            if await run_test(test, deployment, attempt):
                passes += 1
        cases.append(SuiteCase(test_id=test.test_id, critical=test.critical, passes=passes))
        earned += test.weight * passes / RUNS_PER_CASE
        total += test.weight
    return AgentSuiteResult(
        cases=tuple(cases),
        score=round(100 * earned / total, 2),
        reference_score=reference_score,
        reference_deployment=reference_deployment,
    )


@dataclass(frozen=True)
class BackgroundOutcome:
    deployment: str
    verdict: AgentVerdict


async def certify_in_background(
    session: AsyncSession,
    snapshot: CatalogSnapshot,
    *,
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID,
    agent_config_id: uuid.UUID,
    suite_revision: int,
    current_key: str,
    reference_score: float,
    tests: Sequence[SuiteTest],
    run_test: TestRunner,
    eu_only: bool = False,
    limit: int = 1,
) -> list[BackgroundOutcome]:
    """Requisito 42.4: los ``limit`` despliegues más baratos que el de hoy y ya
    certificados por clase pasan la suite de este agente; se guarda el resultado
    (lo paga Auphere) y el router solo los usa si pasan.

    ``session`` va con el ámbito del cliente. Lo llama un trabajo por agente con
    perfil (no un lote de varios clientes)."""
    candidates = await background_candidates(
        session,
        snapshot,
        agent_id=agent_id,
        agent_config_id=agent_config_id,
        suite_revision=suite_revision,
        current_key=current_key,
        eu_only=eu_only,
    )
    out: list[BackgroundOutcome] = []
    for deployment in candidates[: max(0, limit)]:
        result = await certify_agent(
            tenant_id=tenant_id,
            tests=tests,
            deployment=deployment,
            reference_score=reference_score,
            reference_deployment=current_key,
            run_test=run_test,
        )
        verdict = await record_agent_certification(
            session,
            tenant_id=tenant_id,
            agent_id=agent_id,
            agent_config_id=agent_config_id,
            deployment=deployment,
            suite_revision=suite_revision,
            result=result,
            launched_by="auphere",
        )
        out.append(BackgroundOutcome(deployment=deployment.key, verdict=verdict))
    return out


__all__ = [
    "RUNS_PER_CASE",
    "BackgroundOutcome",
    "CaseRunner",
    "SameFamilyJudge",
    "SingleClientBatch",
    "SuiteTest",
    "TestRunner",
    "certify_agent",
    "certify_class",
    "certify_in_background",
    "require_other_family",
]
