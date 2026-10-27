"""La certificación de despliegues: por clase y por agente.

Spec 047, T143 y T144 (requisitos 42.1 a 42.6, research D23). Ningún despliegue
habla con un cliente final sin haber demostrado antes, en español, que sabe hacer
su trabajo:

- **por clase** (despliegue y tarea, plataforma): la batería común —los casos del
  driver de evaluación, τ-bench 2.0 en español y un dominio propio de reservas,
  con cinco países y tú y usted— la ejecuta ``nexus_worker.certification``; aquí
  se **guarda** con su versión, su fecha, la nota de cada métrica y el umbral que
  pasó, y se **caduca** al cambiar el despliegue (modelo, proveedor, ruta, región
  o cuantización) o la batería. Un cambio de precio no la caduca: el precio no
  entra en la huella;
- **por agente** (despliegue y agente, por cliente, con RLS): la suite del agente
  con ese despliegue. Certifica si todas las críticas pasan 3 de 3 y la nota no
  baja más de 2 puntos frente a la referencia, que es el despliegue con el que está
  publicado. Caduca con otra versión del agente o de su suite, y el router no
  usa un despliegue cuya certificación por clase caducó;
- **en segundo plano**: un despliegue certificado por clase y más barato que el
  que usa hoy un agente se certifica para él, y el router solo lo usa si pasa;
- **quién paga**: el partner («Construcción y pruebas») si la lanza él al cambiar
  la calidad; Auphere, fuera de las partidas, si la lanza Auphere.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.services.router_catalog import (
    NOMINAL_ESTIMATE,
    CatalogSnapshot,
    Deployment,
    estimate_cost_micros,
)

#: Lo que mide la certificación por clase (requisito 42.1).
CLASS_METRICS: tuple[str, ...] = (
    "pass3",
    "reasks",
    "unsupported_claims",
    "tool_args_valid",
    "language_drift",
    "latency_p50_ms",
    "latency_p95_ms",
    "latency_p50_ms_reasoning",
    "latency_p95_ms_reasoning",
)
#: Lo que puede bajar la nota de un agente frente a su referencia (42.3).
MAX_REGRESSION_POINTS = 2.0


# ── por clase ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClassResult:
    """El resultado de pasar la batería a un despliegue en una tarea."""

    task: str
    battery_version: int
    metrics: Mapping[str, float | None]
    quality: float
    threshold: float
    judge: str | None = None

    @property
    def passed(self) -> bool:
        return self.quality >= self.threshold


def class_fingerprint(deployment: Deployment, battery_version: int) -> str:
    """La huella de lo que se certificó. Cambia con el modelo, el proveedor, la
    ruta, la región, la cuantización o la batería; **no** con el precio."""
    parts = {
        "key": deployment.key,
        "model": deployment.model,
        "provider": deployment.provider,
        "route": deployment.route,
        "region": deployment.region,
        "quantization": deployment.capabilities.quantization,
        "battery": battery_version,
    }
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:32]


async def record_class_certification(
    session: AsyncSession, deployment: Deployment, result: ClassResult
) -> None:
    """Guarda (o renueva) la certificación de ``deployment`` en la tarea."""
    if deployment.id is None:
        raise ValueError(f"{deployment.key} no tiene fila en model_profiles")
    scores = {
        "metrics": dict(result.metrics),
        "threshold": result.threshold,
        "fingerprint": class_fingerprint(deployment, result.battery_version),
        "judge": result.judge,
        "latency_p95_ms": result.metrics.get("latency_p95_ms"),
    }
    await session.execute(
        sa.text(
            """
            INSERT INTO model_task_certifications
                (deployment_id, task, battery_version, scores, quality, passed)
            VALUES (:d, :task, :b, CAST(:scores AS jsonb), :q, :passed)
            ON CONFLICT (deployment_id, task, battery_version) DO UPDATE
               SET scores = EXCLUDED.scores,
                   quality = EXCLUDED.quality,
                   passed = EXCLUDED.passed,
                   certified_at = now(),
                   invalidated_at = NULL
            """
        ),
        {
            "d": deployment.id,
            "task": result.task,
            "b": result.battery_version,
            "scores": json.dumps(scores, default=str),
            "q": round(max(0.0, min(1.0, result.quality)), 4),
            "passed": result.passed,
        },
    )


async def expire_class_certifications(
    session: AsyncSession, deployments: Iterable[Deployment], *, battery_version: int
) -> list[tuple[str, str]]:
    """Caduca lo que ya no describe al despliegue o es de otra batería.
    Devuelve los pares ``(despliegue, tarea)`` caducados."""
    by_id = {d.id: d for d in deployments if d.id is not None}
    rows = (
        await session.execute(
            sa.text(
                "SELECT deployment_id, task, battery_version, scores "
                "FROM model_task_certifications WHERE invalidated_at IS NULL"
            )
        )
    ).all()
    expired: list[tuple[str, str]] = []
    for deployment_id, task, version, scores in rows:
        deployment = by_id.get(deployment_id)
        if deployment is None:
            continue
        stale = version != battery_version or (scores or {}).get(
            "fingerprint"
        ) != class_fingerprint(deployment, version)
        if not stale:
            continue
        await session.execute(
            sa.text(
                "UPDATE model_task_certifications SET invalidated_at = now() "
                "WHERE deployment_id = :d AND task = :t AND battery_version = :b"
            ),
            {"d": deployment_id, "t": task, "b": version},
        )
        expired.append((deployment.key, task))
    return expired


# ── por agente ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SuiteCase:
    """Una prueba de la suite del agente con un despliegue: cuántas de sus
    repeticiones pasaron."""

    test_id: str
    critical: bool
    passes: int
    runs: int = 3


@dataclass(frozen=True)
class AgentSuiteResult:
    cases: tuple[SuiteCase, ...]
    #: La nota de la suite, de 0 a 100.
    score: float
    #: La del despliegue con el que el agente está publicado.
    reference_score: float
    reference_deployment: str

    def to_json(self) -> dict[str, Any]:
        return {
            "cases": [
                {"test_id": c.test_id, "critical": c.critical, "passes": c.passes, "runs": c.runs}
                for c in self.cases
            ],
            "score": self.score,
            "reference_score": self.reference_score,
            "reference_deployment": self.reference_deployment,
        }


@dataclass(frozen=True)
class AgentVerdict:
    passed: bool
    reasons: tuple[str, ...] = ()


def agent_verdict(result: AgentSuiteResult) -> AgentVerdict:
    """Todas las críticas en 3 de 3 y como mucho 2 puntos menos que la referencia."""
    reasons: list[str] = []
    failing = [c.test_id for c in result.cases if c.critical and c.passes < c.runs]
    if failing:
        reasons.append("critical_not_all_runs:" + ",".join(failing))
    drop = result.reference_score - result.score
    if drop > MAX_REGRESSION_POINTS + 1e-9:
        reasons.append(f"regression:{drop:.2f}")
    return AgentVerdict(passed=not reasons, reasons=tuple(reasons))


@dataclass(frozen=True)
class CertificationPayer:
    """Quién paga y con qué origen se mide el gasto (``usage_records.source``)."""

    paid_by: str
    usage_source: str


_PAYERS: dict[str, CertificationPayer] = {
    # «Construcción y pruebas»: el partner la lanzó al cambiar la calidad.
    "partner": CertificationPayer(paid_by="partner", usage_source="tests"),
    # Auphere: certificación por clase, despliegue nuevo, retirada, segundo plano.
    "auphere": CertificationPayer(paid_by="auphere", usage_source="certification"),
}


def payer_for(launched_by: str) -> CertificationPayer:
    try:
        return _PAYERS[launched_by]
    except KeyError:
        raise ValueError(f"launched_by={launched_by!r}: partner o auphere") from None


async def record_agent_certification(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID,
    agent_config_id: uuid.UUID,
    deployment: Deployment,
    suite_revision: int,
    result: AgentSuiteResult,
    launched_by: str,
) -> AgentVerdict:
    """Guarda la certificación de un despliegue para un agente. La sesión va con
    el ámbito del cliente: la tabla tiene RLS forzada y FK compuestas."""
    if deployment.id is None:
        raise ValueError(f"{deployment.key} no tiene fila en model_profiles")
    verdict = agent_verdict(result)
    payer = payer_for(launched_by)
    payload = {**result.to_json(), "reasons": list(verdict.reasons), "launched_by": launched_by}
    await session.execute(
        sa.text(
            """
            INSERT INTO agent_model_certifications
                (tenant_id, agent_id, deployment_id, agent_config_id, suite_revision,
                 result, passed, paid_by)
            VALUES (:t, :a, :d, :v, :s, CAST(:r AS jsonb), :p, :paid)
            """
        ),
        {
            "t": tenant_id,
            "a": agent_id,
            "d": deployment.id,
            "v": agent_config_id,
            "s": suite_revision,
            "r": json.dumps(payload),
            "p": verdict.passed,
            "paid": payer.paid_by,
        },
    )
    return verdict


_AGENT_CERTS_SQL = """
    SELECT DISTINCT ON (c.deployment_id) p.model_id, c.passed
      FROM agent_model_certifications c
      JOIN model_profiles p ON p.id = c.deployment_id
     WHERE c.agent_id = :a AND c.invalidated_at IS NULL {extra}
     ORDER BY c.deployment_id, c.certified_at DESC
"""


async def certified_deployments_for_agent(
    session: AsyncSession,
    *,
    agent_id: uuid.UUID,
    agent_config_id: uuid.UUID | None,
    suite_revision: int | None,
) -> frozenset[str]:
    """Los despliegues que **este agente** tiene certificados: lo que el router
    recibe en ``RouteContext.agent_certified``. Cuenta la última certificación
    de cada despliegue. Sin ``WHERE tenant_id``: la RLS filtra, y un test de
    aislamiento lo comprueba (test_44)."""
    extra = ""
    params: dict[str, Any] = {"a": agent_id}
    if agent_config_id is not None:
        extra += " AND c.agent_config_id = :v"
        params["v"] = agent_config_id
    if suite_revision is not None:
        extra += " AND c.suite_revision = :s"
        params["s"] = suite_revision
    rows = (await session.execute(sa.text(_AGENT_CERTS_SQL.format(extra=extra)), params)).all()
    return frozenset(str(model_id) for model_id, passed in rows if passed)


async def expire_agent_certifications(
    session: AsyncSession,
    *,
    agent_id: uuid.UUID,
    reason: str,
    deployment_keys: Sequence[str] | None = None,
) -> int:
    """Caduca las certificaciones del agente: otra versión (AgentSpec), otra
    suite o una certificación por clase caducada (``deployment_keys``)."""
    extra = ""
    params: dict[str, Any] = {"a": agent_id, "r": json.dumps({"invalidated_reason": reason})}
    if deployment_keys is not None:
        extra = " AND deployment_id IN (SELECT id FROM model_profiles WHERE model_id = ANY(:keys))"
        params["keys"] = list(deployment_keys)
    result = await session.execute(
        sa.text(
            "UPDATE agent_model_certifications SET invalidated_at = now(), "
            "result = result || CAST(:r AS jsonb) "
            f"WHERE agent_id = :a AND invalidated_at IS NULL{extra}"
        ),
        params,
    )
    return int(getattr(result, "rowcount", 0) or 0)


# ── en segundo plano (42.4) ─────────────────────────────────────────────────


def _nominal_cost(deployment: Deployment) -> int | None:
    price = deployment.current_price()
    return None if price is None else estimate_cost_micros(price, NOMINAL_ESTIMATE)


async def background_candidates(
    session: AsyncSession,
    snapshot: CatalogSnapshot,
    *,
    agent_id: uuid.UUID,
    agent_config_id: uuid.UUID,
    suite_revision: int,
    current_key: str,
    eu_only: bool = False,
    allowed: AbstractSet[str] | None = None,
) -> list[Deployment]:
    """Los despliegues que merece la pena certificar para este agente, del más
    barato al menos barato: activos, certificados por clase en todas las tareas
    de conversación, más baratos que el de hoy y sin certificación de este agente
    con esta versión y esta suite (pasada o no: una suspensa no se repite hasta
    que algo cambie)."""
    current = snapshot.deployments.get(current_key)
    current_cost = None if current is None else _nominal_cost(current)
    tasks = [t.code for t in snapshot.taxonomy.tasks.values() if t.conversation]
    tried = {
        str(row[0])
        for row in (
            await session.execute(
                sa.text(
                    "SELECT p.model_id FROM agent_model_certifications c "
                    "JOIN model_profiles p ON p.id = c.deployment_id "
                    "WHERE c.agent_id = :a AND c.agent_config_id = :v "
                    "AND c.suite_revision = :s AND c.invalidated_at IS NULL"
                ),
                {"a": agent_id, "v": agent_config_id, "s": suite_revision},
            )
        ).all()
    }
    out: list[tuple[int, Deployment]] = []
    for deployment in snapshot.deployments.values():
        if deployment.status != "active" or deployment.key == current_key:
            continue
        if deployment.key in tried or (allowed is not None and deployment.key not in allowed):
            continue
        if eu_only and deployment.residency != "eu":
            continue
        if not tasks or not all(snapshot.class_cert(deployment.key, t) for t in tasks):
            continue
        cost = _nominal_cost(deployment)
        if cost is None or (current_cost is not None and cost >= current_cost):
            continue
        out.append((cost, deployment))
    return [d for _, d in sorted(out, key=lambda item: (item[0], item[1].key))]


__all__ = [
    "CLASS_METRICS",
    "MAX_REGRESSION_POINTS",
    "AgentSuiteResult",
    "AgentVerdict",
    "CertificationPayer",
    "ClassResult",
    "SuiteCase",
    "agent_verdict",
    "background_candidates",
    "certified_deployments_for_agent",
    "class_fingerprint",
    "expire_agent_certifications",
    "expire_class_certifications",
    "payer_for",
    "record_agent_certification",
    "record_class_certification",
]
