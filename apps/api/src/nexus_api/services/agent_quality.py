"""La calidad de un agente — spec 047, T147 (requisito 39; ``contracts/console-api.md``
§4, research D19 y D24).

La pantalla Agente > Avanzado > «Calidad» enseña, para cada opción (los perfiles
«Automático», «Económico», «Equilibrado» y «Máximo», y «Fijar un modelo»):

- una línea de para qué sirve;
- el **precio estimado por mensaje**, comparado con el de la opción actual (39.4).
  Sale de **elegir con el router de verdad** (``chain_for``) el primer modelo de
  cada tarea del turno con los hechos del cliente («Solo UE», la lista del
  partner, lo certificado para este agente) y aplicar sus precios vigentes al
  **perfil de turno** del agente: lo medido en sus últimos 30 días o, sin
  tráfico, el del sector. El precio es el coste del modelo por 2,2 (paso directo,
  39.6): el partner ve precios, nunca costes (C9);
- después de guardar, el **precio real medio por mensaje de 7 días** (39.5).

«Fijar un modelo» ofrece los despliegues activos, permitidos al partner, con la
residencia del cliente y certificados por clase para las tareas de conversación;
cada uno dice si ya está certificado **para este agente** (39.7). Uno que no lo
está, o un perfil sin certificar, se comprueba antes de guardar: la suite del
agente con esa política (39.9, ``check``). Con «Solo UE» no se ofrece un perfil
que no tenga, en alguna tarea del turno, un modelo con inferencia en la UE (39.10).
Un agente migrado (fijado en su modelo de hoy) ve la propuesta de «Automático»
(39.11).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import Message, MessageDirection
from nexus_api.db.models.usage_record import UsageRecord
from nexus_api.services.router_catalog import (
    TURN_TASKS,
    CatalogSnapshot,
    Deployment,
    TokenEstimate,
    estimate_cost_micros,
)

#: Paso directo (ADR-037, 39.6): lo que paga el partner por cada micro-USD de modelo.
PRICE_MULTIPLIER: Final = Decimal("2.2")
PROFILES: Final = ("auto", "economy", "balanced", "max")
LINES: Final[dict[str, str]] = {
    "auto": "Auphere elige en cada tarea el modelo más barato que la hace bien.",
    "economy": "El precio más bajo; para preguntas sencillas y repetidas.",
    "balanced": "Más calidad en las respuestas sin disparar el precio.",
    "max": "La mejor calidad disponible, para conversaciones delicadas.",
    "pinned": "Un modelo fijo para conversar; el resto de tareas sigue «Automático».",
}
#: El turno de un agente sin tráfico (el «sector» de 39.4, hasta tener el de
#: cada sector medido): una clasificación y un turno con herramientas.
SECTOR_TURN: Final[dict[str, TokenEstimate]] = {
    "classify": TokenEstimate(input_tokens=900, output_tokens=20),
    "tool_turn": TokenEstimate(input_tokens=1_500, output_tokens=220, cache_read_tokens=4_000),
}
#: Con menos mensajes, el perfil medido no dice nada todavía.
MIN_MESSAGES: Final = 20
_METERS: Final = {
    "llm.input_tokens": "input_tokens",
    "llm.output_tokens": "output_tokens",
    "llm.cache_read": "cache_read_tokens",
    "llm.cache_write": "cache_write_tokens",
}
#: El modelo de hoy de un agente migrado (``agent_spec.legacy``).
LEGACY_DEPLOYMENT: Final = "nexus/current-binding"


@dataclass
class TurnProfile:
    source: str
    tasks: dict[str, TokenEstimate] = field(default_factory=dict)


async def _agent_messages(session: AsyncSession, agent_id: uuid.UUID, since: datetime) -> int:
    return int(
        await session.scalar(
            sa.select(sa.func.count())
            .select_from(Message)
            .where(
                Message.agent_id == agent_id,
                Message.direction == MessageDirection.OUTBOUND,
                Message.created_at >= since,
            )
        )
        or 0
    )


async def turn_profile(session: AsyncSession, agent_id: uuid.UUID) -> TurnProfile:
    """Lo que gasta un mensaje de este agente, por tarea: medido en 30 días o, sin
    tráfico suficiente, el del sector."""
    since = datetime.now(UTC) - timedelta(days=30)
    messages = await _agent_messages(session, agent_id, since)
    if messages < MIN_MESSAGES:
        return TurnProfile(source="sector", tasks=dict(SECTOR_TURN))
    rows = (
        await session.execute(
            sa.select(UsageRecord.task, UsageRecord.meter, sa.func.sum(UsageRecord.quantity))
            .where(
                UsageRecord.agent_id == agent_id,
                UsageRecord.occurred_at >= since,
                UsageRecord.meter.in_(list(_METERS)),
                UsageRecord.task.is_not(None),
            )
            .group_by(UsageRecord.task, UsageRecord.meter)
        )
    ).all()
    totals: dict[str, dict[str, int]] = {}
    for task, meter, quantity in rows:
        totals.setdefault(str(task), {})[_METERS[meter]] = int(Decimal(quantity) / messages)
    if not totals:
        return TurnProfile(source="sector", tasks=dict(SECTOR_TURN))
    return TurnProfile(
        source="agent_30d",
        tasks={
            task: TokenEstimate(
                input_tokens=t.get("input_tokens", 0),
                output_tokens=t.get("output_tokens", 0),
                cache_read_tokens=t.get("cache_read_tokens", 0),
                cache_write_tokens=t.get("cache_write_tokens", 0),
            )
            for task, t in totals.items()
        },
    )


def _price_micros(deployment: Deployment, estimate: TokenEstimate) -> int | None:
    """El precio (coste por 2,2) de una llamada con los precios vigentes hoy."""
    price = deployment.current_price()
    cost = None if price is None else estimate_cost_micros(price, estimate)
    return None if cost is None else int((Decimal(cost) * PRICE_MULTIPLIER).to_integral_value())


@dataclass
class Facts:
    tenant_id: uuid.UUID
    agent_id: uuid.UUID
    agent_version: str | None
    eu_only: bool
    sovereign: bool
    partner_allowed: frozenset[str] | None
    agent_certified: frozenset[str]


def estimate(
    snapshot: CatalogSnapshot,
    facts: Facts,
    profile: TurnProfile,
    policy: dict[str, Any],
) -> int | None:
    """El precio por mensaje (micro-USD) de una política, con el router de verdad.
    ``None`` si alguna tarea del turno no tendría modelo o precio."""
    from nexus_worker.runtime.model_resolver import RouteContext, chain_for

    pinned = str(policy.get("deployment")) if policy.get("kind") == "pinned" else None
    name = "auto" if pinned else str(policy.get("profile") or "auto")
    profile_policy = snapshot.profile(name)
    if profile_policy is None:
        return None
    total = 0
    for task, tokens in profile.tasks.items():
        spec = snapshot.taxonomy.tasks.get(task)
        if spec is None or profile_policy.task(task) is None:
            continue
        decision = chain_for(
            task,
            profile_policy,
            RouteContext(
                tenant_id=facts.tenant_id,
                catalog=snapshot,
                agent_id=facts.agent_id,
                agent_version=facts.agent_version,
                allowed=facts.partner_allowed if spec.conversation else None,
                eu_only=facts.eu_only,
                sovereign=facts.sovereign,
                agent_certified=facts.agent_certified | ({pinned} if pinned else frozenset()),
                agent_pinned_deployment=pinned,
                estimate=tokens,
            ),
        )
        if not decision.chain:
            return None
        price = _price_micros(decision.chain[0], tokens)
        if price is None:
            return None
        total += price
    return total


def eu_servable(snapshot: CatalogSnapshot, facts: Facts, profile: str) -> bool:
    """Con «Solo UE», el perfil tiene modelo con inferencia en la UE en todas las
    tareas del turno (39.10). Sin «Solo UE», siempre."""
    if not facts.eu_only:
        return True
    from nexus_worker.runtime.model_resolver import RouteContext, chain_for

    policy = snapshot.profile(profile)
    if policy is None:
        return False
    for task in TURN_TASKS:
        if policy.task(task) is None or task not in snapshot.taxonomy.tasks:
            return False
        decision = chain_for(
            task,
            policy,
            RouteContext(
                tenant_id=facts.tenant_id,
                catalog=snapshot,
                agent_id=facts.agent_id,
                eu_only=True,
                sovereign=facts.sovereign,
                agent_certified=facts.agent_certified,
            ),
        )
        if not decision.chain:
            return False
    return True


def pinnable(snapshot: CatalogSnapshot, facts: Facts) -> list[Deployment]:
    """Lo que «Fijar un modelo» puede ofrecer (39.7): activo, permitido, con la
    residencia del cliente y certificado por clase para conversar."""
    out: list[Deployment] = []
    for deployment in snapshot.deployments.values():
        if deployment.status != "active":
            continue
        if facts.partner_allowed is not None and deployment.key not in facts.partner_allowed:
            continue
        if facts.eu_only and deployment.residency != "eu":
            continue
        if not all(
            snapshot.class_cert(deployment.key, task) is not None
            for task in ("answer", "tool_turn")
        ):
            continue
        out.append(deployment)
    return sorted(out, key=lambda d: (d.display_name or d.key).lower())


async def real_price_7d(session: AsyncSession, agent_id: uuid.UUID) -> int | None:
    """El precio real medio por mensaje de los últimos 7 días (39.5), en micro-USD."""
    since = datetime.now(UTC) - timedelta(days=7)
    messages = await _agent_messages(session, agent_id, since)
    if not messages:
        return None
    cost = await session.scalar(
        sa.select(sa.func.sum(UsageRecord.cost_usd)).where(
            UsageRecord.agent_id == agent_id,
            UsageRecord.occurred_at >= since,
            UsageRecord.meter.in_(list(_METERS)),
        )
    )
    if cost is None:
        return None
    return int(
        (Decimal(cost) * Decimal(1_000_000) * PRICE_MULTIPLIER / messages).to_integral_value()
    )


def same_policy(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    def norm(p: dict[str, Any] | None) -> tuple[str, str]:
        p = p or {}
        if p.get("kind") == "pinned":
            return ("pinned", str(p.get("deployment")))
        return ("profile", str(p.get("profile") or ""))

    return norm(a) == norm(b)


def valid_policy(policy: dict[str, Any], pinnable_keys: set[str]) -> bool:
    if policy.get("kind") == "profile":
        return policy.get("profile") in PROFILES
    if policy.get("kind") == "pinned":
        return str(policy.get("deployment")) in pinnable_keys
    return False


#: Cuánto puede bajar la nota frente a la suite de siempre (la puerta, 23.2).
MAX_DROP: Final = 2.0


async def finish_check(session: AsyncSession, run: Any, summary: dict[str, Any]) -> dict[str, Any]:
    """El veredicto de una comprobación de calidad (39.9): todas las críticas
    pasan y la nota baja como mucho 2 puntos frente a la última pasada normal.
    Si pasa, los despliegues que esa política usa para conversar quedan
    certificados para este agente (42.3)."""
    from nexus_api.db.models.agent_spec import AgentTestRun
    from nexus_api.services.certification import AgentSuiteResult, record_agent_certification
    from nexus_api.services.router_catalog import load_snapshot

    reference = await session.scalar(
        sa.select(AgentTestRun)
        .where(
            AgentTestRun.tenant_id == run.tenant_id,
            AgentTestRun.agent_id == run.agent_id,
            AgentTestRun.status == "done",
            AgentTestRun.reason != "certification",
        )
        .order_by(AgentTestRun.created_at.desc())
        .limit(1)
    )
    rate = summary.get("rate")
    reference_rate = (reference.summary or {}).get("rate") if reference is not None else None
    reasons: list[str] = []
    if summary.get("critical_failed"):
        reasons.append("critical_failed")
    if rate is None:
        reasons.append("no_result")
    elif reference_rate is not None and float(reference_rate) - float(rate) > MAX_DROP:
        reasons.append(f"regression:{float(reference_rate) - float(rate):.2f}")
    passed = not reasons
    check = {"passed": passed, "reasons": reasons, "reference_rate": reference_rate}
    run.summary = {**dict(run.summary or {}), "quality_check": check}
    if passed and run.agent_config_id is not None:
        snapshot = await load_snapshot(session, refresh_hop=False)
        # El detalle de cada prueba está en la pasada (``agent_test_results``);
        # la certificación guarda la nota y la referencia con las que pasó.
        result = AgentSuiteResult(
            cases=(),
            score=float(rate or 0.0),
            reference_score=float(reference_rate if reference_rate is not None else rate or 0.0),
            reference_deployment="suite",
        )
        for key in (run.summary or {}).get("check_deployments") or []:
            deployment = snapshot.deployments.get(str(key))
            if deployment is None or deployment.id is None:
                continue
            await record_agent_certification(
                session,
                tenant_id=run.tenant_id,
                agent_id=run.agent_id,
                agent_config_id=run.agent_config_id,
                deployment=deployment,
                suite_revision=int((run.summary or {}).get("suite_revision") or 0),
                result=result,
                launched_by="partner",
            )
    await session.flush()
    return check


def conversation_deployments(
    snapshot: CatalogSnapshot, facts: Facts, policy: dict[str, Any]
) -> list[str]:
    """Los despliegues con los que esa política conversaría: los que la
    comprobación certifica para el agente si pasa."""
    if policy.get("kind") == "pinned":
        return [str(policy.get("deployment"))]
    from nexus_worker.runtime.model_resolver import RouteContext, chain_for

    profile = snapshot.profile(str(policy.get("profile") or "auto"))
    if profile is None:
        return []
    out: list[str] = []
    for task in ("answer", "tool_turn"):
        spec = snapshot.taxonomy.tasks.get(task)
        if spec is None or profile.task(task) is None:
            continue
        decision = chain_for(
            task,
            profile,
            RouteContext(
                tenant_id=facts.tenant_id,
                catalog=snapshot,
                agent_id=facts.agent_id,
                allowed=facts.partner_allowed,
                eu_only=facts.eu_only,
                sovereign=facts.sovereign,
                agent_certified=facts.agent_certified,
            ),
        )
        if decision.chain and decision.chain[0].key not in out:
            out.append(decision.chain[0].key)
    return out


__all__ = [
    "LEGACY_DEPLOYMENT",
    "LINES",
    "PRICE_MULTIPLIER",
    "PROFILES",
    "SECTOR_TURN",
    "Facts",
    "TurnProfile",
    "conversation_deployments",
    "estimate",
    "eu_servable",
    "finish_check",
    "pinnable",
    "real_price_7d",
    "same_policy",
    "turn_profile",
    "valid_policy",
]
