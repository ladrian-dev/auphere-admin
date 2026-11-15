"""El ciclo de vida de los modelos — spec 047, T149 (requisitos 41.7, 41.8 y 41.9).

Tres cosas que Auphere hace desde el panel y que el cron del worker
(``nexus_worker.streams.model_lifecycle_cron``) sigue cada día:

- **Retirada** (41.7). Auphere registra la fecha (``announce_retirement``): el
  despliegue pasa a ``retiring`` y **sigue atendiendo hasta su fecha**
  (``router_catalog.SERVABLE_STATUSES``). Los partners con agentes fijados en él
  reciben ``model.retirement`` con 30 días o más —o en cuanto se sabe, si el
  proveedor avisa con menos— y otra vez a 7 días, con el modelo propuesto para
  cada agente: el certificado para ese agente, de la misma gama y con el precio
  más cercano. En la fecha, cada agente pasa al propuesto si sigue certificado,
  o a «Automático» si no, con **una versión nueva** (su historial) y una fila de
  auditoría ``agent.quality_changed``; el despliegue pasa a ``retired``. Los
  agentes con perfil no notan nada: el router deja de elegirlo.
- **Coste** (41.8, enmendado por la spec 059, 3.12). Un precio de coste entra con
  su fecha, nunca pasada (``add_price``), y en su fecha el cron lo pasa a las
  columnas que lee el medidor. **No avisa a nadie**: lo que paga el partner sale de
  los pesos de venta, y el coste solo mueve el margen de Auphere.
- **«No disponible»** (41.9). ``mark_unavailable``: el modelo deja de ejecutarse
  desde el siguiente turno (``router_catalog.catalog_changed`` en este proceso y
  ``CATALOG_CHANGED`` por el canal de promoción en los demás).

**Spec 059: nadie deja mudos a los agentes.** «Retirar» y «No disponible» se
rechazan sobre un modelo en uso (``services.model_usage``: un valor por defecto de
la plataforma, un agente que responde con él o una asignación de cliente) y cuando
no se puede verificar qué usa el worker. Las dos tienen vuelta atrás
(``cancel_retirement`` y ``restore_available``). Y si llega la fecha de un modelo
que ya estaba en retirada y aún tiene agentes que no tienen a dónde ir —sin
sustituto y sin «Automático» que los atienda—, no se retira ni se los mueve: se
queda en retirada y se avisa una vez al día (``deployment.retirement_blocked``).

**Quién está «fijado»** en un despliegue: un agente con «Fijar un modelo»
(``model_policy.kind = pinned``) y **un agente de hoy** —sin ``model_policy``—,
que está fijado en su modelo de hoy: su asignación ``respond`` de
``tenant_model_bindings``, si no ``policies.llm.respond_model``, si no el
modelo de respuesta global del worker (``default_respond``).

Los agentes de cada cliente se leen con **su** GUC (garantía 1): una sesión por
cliente. Los avisos no llevan ids internos de cliente: la referencia del partner
(``external_client_ref``) y el nombre del agente.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
import structlog

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AgentConfig, NotificationKind, NotificationSeverity
from nexus_api.repositories import AuditRepository
from nexus_api.repositories.agent_config import AgentConfigRepository
from nexus_api.services import console_notifications
from nexus_api.services.certification import certified_deployments_for_agent
from nexus_api.services.model_usage import ModelUses, uses_of
from nexus_api.services.router_catalog import (
    AUTO_MODEL_POLICY,
    NOMINAL_ESTIMATE,
    CatalogSnapshot,
    Deployment,
    Price,
    auto_servable,
    catalog_changed,
    estimate_cost_micros,
    hard_reason,
    load_snapshot,
    model_policy_of,
)

log = structlog.get_logger(__name__)

#: Los avisos de retirada: a 30 días (o en cuanto se sabe) y a 7 (``events.md`` §3).
RETIREMENT_NOTICE_DAYS: tuple[int, ...] = (30, 7)
#: Quien firma lo que hace el ciclo de vida solo.
LIFECYCLE_ACTOR = "system:model_lifecycle"
#: La ventana del perfil de turno de un agente (39.4).
USAGE_WINDOW_DAYS = 30
#: Desde aquí, los precios entran por ``model_prices`` (la 0180 copió los de
#: antes desde las columnas): solo los posteriores se pasan a las columnas del
#: medidor, así que un precio antiguo nunca pisa una columna.
PRICES_FROM: date = date(2026, 10, 27)
_CONVERSATION_TASKS = ("answer", "tool_turn")
#: Los estados a los que puede volver un modelo «No disponible» (0231).
_RESTORABLE = frozenset({"draft", "certifying", "active", "retiring", "retired", "deprecated"})


class LifecycleError(ValueError):
    """Una operación del catálogo que no se puede hacer, con su código. Si el motivo
    es el uso del modelo (``model_in_use``, ``defaults_unverified``), ``uses`` dice
    cuál."""

    def __init__(self, code: str, detail: str, *, uses: ModelUses | None = None) -> None:
        super().__init__(detail)
        self.code = code
        self.uses = uses


# ── lo que se lee de cada cliente ──────────────────────────────────────────


@dataclass(frozen=True)
class AgentInCatalog:
    """Un agente publicado, con en qué está fijado y lo que gastó."""

    tenant_id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str
    version_id: uuid.UUID
    policies: Mapping[str, Any]
    #: El despliegue en el que está fijado, o None (un agente con perfil).
    fixed_on: str | None
    #: ``pinned`` («Fijar un modelo») o ``today`` (un agente de hoy).
    how: str | None
    partner_id: uuid.UUID | None
    client_ref: str | None
    eu_only: bool
    sovereign: bool
    certified: frozenset[str]
    #: modelo → contador → (cantidad, coste en USD) de los últimos 30 días.
    usage: Mapping[str, Mapping[str, tuple[Decimal, Decimal]]] = field(default_factory=dict)

    def notice_row(self, **extra: Any) -> dict[str, Any]:
        return {"client_ref": self.client_ref, "agent": self.agent_name, **extra}


@dataclass(frozen=True)
class Proposal:
    """El sustituto propuesto a un agente fijado: None = «Automático»."""

    agent: AgentInCatalog
    substitute: str | None

    @property
    def label(self) -> str:
        return self.substitute or "auto"


@dataclass
class LifecycleReport:
    """Lo que hizo una pasada del cron."""

    retirement_notices: int = 0
    moved_agents: int = 0
    retired: list[str] = field(default_factory=list)
    prices_applied: list[str] = field(default_factory=list)
    #: Los clientes cuyos agentes cambiaron de versión: el worker los recarga.
    tenants_changed: set[uuid.UUID] = field(default_factory=set)
    #: Spec 059 (1.8): las retiradas detenidas, con cuántos agentes atrapan.
    blocked: dict[str, int] = field(default_factory=dict)

    @property
    def catalog_changed(self) -> bool:
        return bool(self.retired or self.prices_applied)


_TENANTS_SQL = sa.text("SELECT id FROM tenants WHERE status <> 'archived'")
_MAPPINGS_SQL = sa.text("SELECT tenant_id, partner_id, external_client_ref FROM partner_tenants")
_AGENTS_SQL = sa.text(
    """
    SELECT a.id AS agent_id, a.name, c.id AS version_id, c.policies
      FROM agents a
      JOIN agent_configs c ON c.agent_id = a.id
     WHERE c.status = 'active' AND a.status <> 'archived'
    """
)
_RESPOND_BINDING_SQL = sa.text(
    "SELECT p.model_id FROM tenant_model_bindings b "
    "JOIN model_profiles p ON p.id = b.model_profile_id WHERE b.role = 'respond' LIMIT 1"
)
_FACTS_SQL = sa.text("SELECT eu_only, sovereign FROM business_profiles")
_USAGE_SQL = sa.text(
    """
    SELECT agent_id, model, meter, sum(quantity) AS qty, coalesce(sum(cost_usd), 0) AS cost
      FROM usage_records
     WHERE occurred_at >= :since AND agent_id IS NOT NULL AND source = 'channel'
       AND model IS NOT NULL
     GROUP BY agent_id, model, meter
    """
)


def fixed_deployment(
    policies: Mapping[str, Any] | None, *, respond_binding: str | None, default_respond: str | None
) -> tuple[str | None, str | None]:
    """En qué despliegue está fijado un agente, y cómo (``pinned`` o ``today``).
    Mismo orden que el turno de hoy: la asignación gana a la política."""
    policy = model_policy_of(policies)
    if policy is not None:
        return (policy.deployment, "pinned") if policy.kind == "pinned" else (None, None)
    llm = (policies or {}).get("llm")
    override = llm.get("respond_model") if isinstance(llm, Mapping) else None
    key = respond_binding or (override if isinstance(override, str) and override else None)
    key = key or default_respond
    return (key, "today") if key else (None, None)


async def scan_agents(
    *, default_respond: str | None = None, usage_since: datetime | None = None
) -> list[AgentInCatalog]:
    """Los agentes publicados de todos los clientes, cada cliente con su GUC."""
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        tenants = [uuid.UUID(str(t)) for (t,) in (await session.execute(_TENANTS_SQL)).all()]
        mappings = {
            uuid.UUID(str(t)): (uuid.UUID(str(p)), str(ref))
            for t, p, ref in (await session.execute(_MAPPINGS_SQL)).all()
        }
    out: list[AgentInCatalog] = []
    for tenant_id in tenants:
        partner_id, client_ref = mappings.get(tenant_id, (None, None))
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            rows = (await session.execute(_AGENTS_SQL)).all()
            if not rows:
                continue
            binding = await session.scalar(_RESPOND_BINDING_SQL)
            facts = (await session.execute(_FACTS_SQL)).one_or_none()
            usage: dict[uuid.UUID, dict[str, dict[str, tuple[Decimal, Decimal]]]] = {}
            if usage_since is not None:
                for agent_id, model, meter, qty, cost in (
                    await session.execute(_USAGE_SQL, {"since": usage_since})
                ).all():
                    usage.setdefault(agent_id, {}).setdefault(str(model), {})[str(meter)] = (
                        Decimal(str(qty)),
                        Decimal(str(cost)),
                    )
            for agent_id, name, version_id, policies in rows:
                fixed_on, how = fixed_deployment(
                    policies, respond_binding=binding, default_respond=default_respond
                )
                certified = await certified_deployments_for_agent(
                    session, agent_id=agent_id, agent_config_id=None, suite_revision=None
                )
                out.append(
                    AgentInCatalog(
                        tenant_id=tenant_id,
                        agent_id=agent_id,
                        agent_name=str(name),
                        version_id=version_id,
                        policies=dict(policies or {}),
                        fixed_on=fixed_on,
                        how=how,
                        partner_id=partner_id,
                        client_ref=client_ref,
                        eu_only=bool(facts.eu_only) if facts is not None else False,
                        sovereign=bool(facts.sovereign) if facts is not None else False,
                        certified=certified,
                        usage=usage.get(agent_id, {}),
                    )
                )
    return out


async def _snapshot() -> CatalogSnapshot:
    async with get_sessionmaker()() as session:
        return await load_snapshot(session, refresh_hop=False)


# ── el sustituto (41.7) ────────────────────────────────────────────────────


def _nominal_cost(deployment: Deployment, day: date | None = None) -> int | None:
    price = deployment.price_on(day or datetime.now(UTC).date())
    return None if price is None else estimate_cost_micros(price, NOMINAL_ESTIMATE)


def propose_substitute(
    snapshot: CatalogSnapshot, retiring_key: str, agent: AgentInCatalog
) -> str | None:
    """El certificado para ese agente, de la misma gama y con el precio más
    cercano, que hace lo que hacía el retirado y cumple la residencia del
    cliente. None = «Automático»."""
    retiring = snapshot.deployments.get(retiring_key)
    tier = retiring.capabilities.tier if retiring is not None else None
    reference = _nominal_cost(retiring) if retiring is not None else None
    specs = [
        snapshot.taxonomy.tasks[t]
        for t in _CONVERSATION_TASKS
        if t in snapshot.taxonomy.tasks
        and (
            retiring is None
            or all(retiring.capabilities.satisfies(n) for n in snapshot.taxonomy.tasks[t].needs)
        )
    ]
    ranked: list[tuple[int, int, str]] = []
    for candidate in snapshot.deployments.values():
        if candidate.key == retiring_key or candidate.status != "active":
            continue
        if candidate.key not in agent.certified or candidate.capabilities.tier != tier:
            continue
        if any(
            hard_reason(candidate, spec, eu_only=agent.eu_only, sovereign=agent.sovereign)
            for spec in specs
        ):
            continue
        cost = _nominal_cost(candidate)
        if cost is None:
            continue
        distance = abs(cost - reference) if reference is not None else cost
        ranked.append((distance, cost, candidate.key))
    return min(ranked)[2] if ranked else None


# ── retirada (41.7) ────────────────────────────────────────────────────────


def _days_left(retire_after: datetime, now: datetime) -> int:
    return math.ceil((retire_after - now).total_seconds() / 86_400)


def _notice_stage(days_left: int) -> int | None:
    due = [d for d in RETIREMENT_NOTICE_DAYS if days_left <= d]
    return min(due) if due else None


async def _proposals(
    key: str, *, default_respond: str | None, snapshot: CatalogSnapshot | None = None
) -> list[Proposal]:
    snapshot = snapshot or await _snapshot()
    agents = await scan_agents(default_respond=default_respond)
    return [
        Proposal(agent=a, substitute=propose_substitute(snapshot, key, a))
        for a in agents
        if a.fixed_on == key
    ]


async def _notify_retirement(
    key: str, *, retire_after: datetime, now: datetime, proposals: Sequence[Proposal]
) -> int:
    days_left = _days_left(retire_after, now)
    stage = _notice_stage(days_left)
    if stage is None or days_left <= 0:
        return 0
    by_partner: dict[uuid.UUID, list[Proposal]] = {}
    for proposal in proposals:
        if proposal.agent.partner_id is not None:
            by_partner.setdefault(proposal.agent.partner_id, []).append(proposal)
    sent = 0
    async with get_sessionmaker()() as session, session.begin():
        for partner_id, items in sorted(by_partner.items(), key=lambda kv: str(kv[0])):
            row = await console_notifications.emit(
                session,
                partner_id=partner_id,
                kind=NotificationKind.MODEL_RETIREMENT,
                severity=NotificationSeverity.WARNING,
                data={
                    "deployment": key,
                    "retire_after": retire_after.isoformat(),
                    "days_left": days_left,
                    "agents": [
                        p.agent.notice_row(proposed=p.label)
                        for p in sorted(
                            items, key=lambda p: (str(p.agent.client_ref), p.agent.agent_name)
                        )
                    ],
                },
                dedupe_key=f"model.retirement:{key}:{partner_id}:{stage}",
            )
            sent += row is not None
    return sent


async def guard_not_in_use(key: str, *, redis: Any | None = None) -> None:
    """Spec 059 (1.1 a 1.5): ``model_in_use`` si el modelo está en uso, o
    ``defaults_unverified`` si no se puede verificar qué usa el worker. Sin caché:
    un modelo recién asignado tiene que contar."""
    if redis is None:
        from nexus_api.core import redis_client

        redis = redis_client.get_redis()
    uses = await uses_of(key, redis=redis, cached=False)
    if uses.in_use:
        raise LifecycleError("model_in_use", f"{key} está en uso", uses=uses)
    if not uses.verified:
        raise LifecycleError(
            "defaults_unverified",
            f"no se puede verificar qué usa el worker ({uses.problem})",
            uses=uses,
        )


async def announce_retirement(
    key: str,
    *,
    retire_after: datetime,
    actor: str,
    reason: str | None = None,
    now: datetime | None = None,
    default_respond: str | None = None,
    redis: Any | None = None,
) -> list[Proposal]:
    """Auphere registra la fecha de retirada: ``retiring`` hasta entonces, y el
    aviso a los partners con agentes fijados si ya toca (con menos de 30 días,
    en el acto). Devuelve el sustituto propuesto a cada agente fijado. Desde la
    spec 059, solo sobre un modelo sin uso (``guard_not_in_use``)."""
    moment = now or datetime.now(UTC)
    if retire_after.tzinfo is None:
        raise LifecycleError("naive_date", "retire_after necesita zona horaria")
    if retire_after <= moment:
        raise LifecycleError("in_the_past", "la fecha de retirada ya pasó")
    await guard_not_in_use(key, redis=redis)
    async with get_sessionmaker()() as session, session.begin():
        before = await session.scalar(
            sa.text("SELECT status FROM model_profiles WHERE model_id = :k FOR UPDATE"),
            {"k": key},
        )
        if before is None:
            raise LifecycleError("unknown_deployment", key)
        if before in ("retired", "unavailable"):
            raise LifecycleError("not_servable", f"{key} está {before}")
        await session.execute(
            sa.text(
                "UPDATE model_profiles SET status = 'retiring', retire_after = :d, "
                "updated_at = now() WHERE model_id = :k"
            ),
            {"k": key, "d": retire_after},
        )
        await AuditRepository(session).record(
            actor=actor,
            action="deployment.retired",
            target=f"deployment:{key}",
            before={"status": before},
            after={
                "status": "retiring",
                "retire_after": retire_after.isoformat(),
                "reason": reason,
            },
            platform=True,
        )
    catalog_changed()
    proposals = await _proposals(key, default_respond=default_respond)
    await _notify_retirement(key, retire_after=retire_after, now=moment, proposals=proposals)
    return proposals


async def _move_agent(proposal: Proposal, *, retiring_key: str) -> bool:
    """El agente pasa al sustituto o a «Automático» con una versión nueva."""
    agent = proposal.agent
    new_policy = (
        {"kind": "pinned", "deployment": proposal.substitute}
        if proposal.substitute
        else dict(AUTO_MODEL_POLICY)
    )
    async with get_sessionmaker()() as session, tenant_scoped_session(session, agent.tenant_id):
        source = await session.get(AgentConfig, agent.version_id)
        if source is None:
            return False
        policies = {**dict(source.policies or {}), "model_policy": new_policy}
        moved = await AgentConfigRepository(session).publish_copy(
            source, policies=policies, published_by=LIFECYCLE_ACTOR
        )
        await AuditRepository(session).record(
            actor=LIFECYCLE_ACTOR,
            action="agent.quality_changed",
            target=f"agent:{agent.agent_id}",
            before={
                "model_policy": dict(source.policies or {}).get("model_policy")
                or {"kind": agent.how, "deployment": retiring_key},
                "version": source.version,
            },
            after={
                "model_policy": new_policy,
                "version": moved.version,
                "reason": "model.retirement",
                "deployment": retiring_key,
            },
        )
    log.info(
        "model_lifecycle.agent_moved",
        tenant_id=str(agent.tenant_id),
        agent_id=str(agent.agent_id),
        deployment=retiring_key,
        to=proposal.label,
    )
    return True


def _trapped(snapshot: CatalogSnapshot, proposals: Sequence[Proposal]) -> list[Proposal]:
    """Los agentes que no tienen a dónde ir: sin sustituto y sin «Automático» que
    pueda atender a su cliente (spec 059, 1.8). Moverlos los dejaría mudos."""
    return [
        p
        for p in proposals
        if p.substitute is None
        and not auto_servable(snapshot, eu_only=p.agent.eu_only, sovereign=p.agent.sovereign)
    ]


def _respond_default(default_respond: str | None) -> str:
    if default_respond:
        return default_respond
    from nexus_worker.platform_models import default_models

    return str(default_models()["respond"])


async def blocked_retirements(
    *, now: datetime | None = None, default_respond: str | None = None
) -> dict[str, int]:
    """``modelo → agentes atrapados`` de cada modelo en retirada con la fecha ya
    pasada que no se puede retirar (spec 059, 1.8). Lo enseña Modelos."""
    moment = now or datetime.now(UTC)
    snapshot = await _snapshot()
    respond = _respond_default(default_respond)
    out: dict[str, int] = {}
    for key, deployment in sorted(snapshot.deployments.items()):
        if deployment.status != "retiring" or deployment.retire_after is None:
            continue
        if moment < deployment.retire_after:
            continue
        trapped = _trapped(
            snapshot, await _proposals(key, default_respond=respond, snapshot=snapshot)
        )
        if trapped:
            out[key] = len(trapped)
    return out


async def _record_blocked(key: str, *, agents: int, moment: datetime) -> None:
    """Una auditoría ``deployment.retirement_blocked`` al día por modelo, y el
    evento en cada pasada para que lo vea quien mire los logs."""
    day = moment.date().isoformat()
    log.warning("model_lifecycle.retirement_blocked", deployment=key, agents=agents, day=day)
    async with get_sessionmaker()() as session, session.begin():
        seen = await session.scalar(
            sa.text(
                "SELECT 1 FROM audit_log WHERE action = 'deployment.retirement_blocked' "
                "AND target = :t AND after_json ->> 'date' = :d LIMIT 1"
            ),
            {"t": f"deployment:{key}", "d": day},
        )
        if seen:
            return
        await AuditRepository(session).record(
            actor=LIFECYCLE_ACTOR,
            action="deployment.retirement_blocked",
            target=f"deployment:{key}",
            after={"agents": agents, "date": day},
            platform=True,
        )


async def _retire_due(
    key: str, report: LifecycleReport, *, default_respond: str | None, now: datetime
) -> None:
    snapshot = await _snapshot()
    proposals = await _proposals(
        key, default_respond=_respond_default(default_respond), snapshot=snapshot
    )
    trapped = _trapped(snapshot, proposals)
    if trapped:
        report.blocked[key] = len(trapped)
        await _record_blocked(key, agents=len(trapped), moment=now)
        return
    for proposal in proposals:
        if await _move_agent(proposal, retiring_key=key):
            report.moved_agents += 1
            report.tenants_changed.add(proposal.agent.tenant_id)
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                "UPDATE model_profiles SET status = 'retired', updated_at = now() "
                "WHERE model_id = :k AND status = 'retiring'"
            ),
            {"k": key},
        )
        await AuditRepository(session).record(
            actor=LIFECYCLE_ACTOR,
            action="deployment.retired",
            target=f"deployment:{key}",
            before={"status": "retiring"},
            after={"status": "retired", "moved_agents": report.moved_agents},
            platform=True,
        )
    report.retired.append(key)


# ── «No disponible» (41.9) ─────────────────────────────────────────────────


async def mark_unavailable(key: str, *, actor: str, reason: str, redis: Any | None = None) -> str:
    """El despliegue deja de cumplir su contrato o su licencia: deja de ejecutarse
    desde el siguiente turno. Solo sobre un modelo sin uso (spec 059). Guarda el
    estado que tenía para «Volver a disponible», y lo devuelve."""
    if not reason.strip():
        raise LifecycleError("reason_required", "hace falta el motivo")
    await guard_not_in_use(key, redis=redis)
    async with get_sessionmaker()() as session, session.begin():
        before = await session.scalar(
            sa.text("SELECT status FROM model_profiles WHERE model_id = :k FOR UPDATE"),
            {"k": key},
        )
        if before is None:
            raise LifecycleError("unknown_deployment", key)
        await session.execute(
            sa.text(
                "UPDATE model_profiles SET status = 'unavailable', "
                "status_before_unavailable = CASE WHEN :b = 'unavailable' "
                "THEN status_before_unavailable ELSE :b END, updated_at = now() "
                "WHERE model_id = :k"
            ),
            {"k": key, "b": before},
        )
        await AuditRepository(session).record(
            actor=actor,
            action="deployment.unavailable",
            target=f"deployment:{key}",
            before={"status": before},
            after={"status": "unavailable", "reason": reason.strip()},
            platform=True,
        )
    catalog_changed()
    return str(before)


async def cancel_retirement(key: str, *, actor: str, reason: str) -> None:
    """Spec 059 (1.6): ``retiring`` vuelve a ``active`` y sin fecha. Los avisos
    pendientes dejan de salir, porque el cron solo recorre lo que está en
    retirada."""
    if not reason.strip():
        raise LifecycleError("reason_required", "hace falta el motivo")
    async with get_sessionmaker()() as session, session.begin():
        row = (
            await session.execute(
                sa.text(
                    "SELECT status, retire_after FROM model_profiles WHERE model_id = :k FOR UPDATE"
                ),
                {"k": key},
            )
        ).one_or_none()
        if row is None:
            raise LifecycleError("unknown_deployment", key)
        if row.status != "retiring":
            raise LifecycleError("not_retiring", f"{key} está {row.status}")
        await session.execute(
            sa.text(
                "UPDATE model_profiles SET status = 'active', retire_after = NULL, "
                "updated_at = now() WHERE model_id = :k"
            ),
            {"k": key},
        )
        await AuditRepository(session).record(
            actor=actor,
            action="deployment.retirement_cancelled",
            target=f"deployment:{key}",
            before={
                "status": "retiring",
                "retire_after": row.retire_after.isoformat() if row.retire_after else None,
            },
            after={"status": "active", "reason": reason.strip()},
            platform=True,
        )
    catalog_changed()


async def restore_available(key: str, *, actor: str, reason: str) -> str:
    """Spec 059 (1.7): «No disponible» vuelve al estado que tenía, sin pasar por
    la puerta de activación: es deshacer, no activar. El estado sale de la
    columna; si el modelo se marcó antes de la 0231, de su última auditoría; y si
    no hay rastro, ``draft``, que no atiende a nadie. Devuelve el estado."""
    if not reason.strip():
        raise LifecycleError("reason_required", "hace falta el motivo")
    async with get_sessionmaker()() as session, session.begin():
        row = (
            await session.execute(
                sa.text(
                    "SELECT status, status_before_unavailable FROM model_profiles "
                    "WHERE model_id = :k FOR UPDATE"
                ),
                {"k": key},
            )
        ).one_or_none()
        if row is None:
            raise LifecycleError("unknown_deployment", key)
        if row.status != "unavailable":
            raise LifecycleError("not_unavailable", f"{key} está {row.status}")
        target = row.status_before_unavailable
        if target is None:
            target = await session.scalar(
                sa.text(
                    "SELECT before_json ->> 'status' FROM audit_log "
                    "WHERE action = 'deployment.unavailable' AND target = :t "
                    "AND before_json ->> 'status' <> 'unavailable' "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"t": f"deployment:{key}"},
            )
        if target not in _RESTORABLE:
            target = "draft"
        await session.execute(
            sa.text(
                "UPDATE model_profiles SET status = :s, status_before_unavailable = NULL, "
                "updated_at = now() WHERE model_id = :k"
            ),
            {"k": key, "s": target},
        )
        await AuditRepository(session).record(
            actor=actor,
            action="deployment.restored",
            target=f"deployment:{key}",
            before={"status": "unavailable"},
            after={"status": target, "reason": reason.strip()},
            platform=True,
        )
    catalog_changed()
    return str(target)


# ── precio (41.8) ──────────────────────────────────────────────────────────


async def add_price(
    key: str,
    price: Price,
    *,
    actor: str,
    today: date | None = None,
) -> None:
    """Un coste nuevo con su vigencia y su fuente. No avisa a nadie (spec 059,
    3.12): el coste solo mueve el margen de Auphere. No entra con una fecha
    pasada (4.4): el medidor no revalora lo que ya pasó."""
    day = today or datetime.now(UTC).date()
    if price.valid_from < day:
        raise LifecycleError("in_the_past", "la fecha de vigencia ya pasó")
    async with get_sessionmaker()() as session, session.begin():
        deployment_id = await session.scalar(
            sa.text("SELECT id FROM model_profiles WHERE model_id = :k"), {"k": key}
        )
        if deployment_id is None:
            raise LifecycleError("unknown_deployment", key)
        await session.execute(
            sa.text(
                """
                INSERT INTO model_prices (deployment_id, valid_from, unit, input, cache_read,
                    cache_write, output, audio_minute, image, surcharge, source_url, currency)
                VALUES (:d, :v, :unit, :input, :cache_read, :cache_write, :output, :audio,
                    :image, CAST(:surcharge AS jsonb), :source, :currency)
                ON CONFLICT (deployment_id, valid_from) DO UPDATE SET
                    unit = EXCLUDED.unit, input = EXCLUDED.input,
                    cache_read = EXCLUDED.cache_read, cache_write = EXCLUDED.cache_write,
                    output = EXCLUDED.output, audio_minute = EXCLUDED.audio_minute,
                    image = EXCLUDED.image, surcharge = EXCLUDED.surcharge,
                    source_url = EXCLUDED.source_url, currency = EXCLUDED.currency
                """
            ),
            {
                "d": deployment_id,
                "v": price.valid_from,
                "unit": price.unit,
                "input": price.input,
                "cache_read": price.cache_read,
                "cache_write": price.cache_write,
                "output": price.output,
                "audio": price.audio_minute,
                "image": price.image,
                "surcharge": None if price.surcharge is None else _json(price.surcharge),
                "source": price.source_url,
                "currency": price.currency,
            },
        )
        await AuditRepository(session).record(
            actor=actor,
            action="deployment.price_added",
            target=f"deployment:{key}",
            after={"price": price.to_contract()},
            platform=True,
        )
    catalog_changed()


def _json(value: Mapping[str, Any]) -> str:
    import json

    return json.dumps(dict(value), sort_keys=True)


_PRICE_COLUMNS = (
    ("input", "price_input_per_mtok"),
    ("output", "price_output_per_mtok"),
    ("cache_read", "price_cache_read_per_mtok"),
    ("cache_write", "price_cache_write_per_mtok"),
    ("audio_minute", "price_per_minute"),
)


async def _apply_due_prices(today: date) -> list[str]:
    """Los precios que entran en vigor hoy pasan a las columnas que lee el
    medidor (``metering.pricing``). Solo los que entraron por ``model_prices``
    desde ``PRICES_FROM``: nunca un precio antiguo pisa una columna."""
    applied: list[str] = []
    snapshot = await _snapshot()
    async with get_sessionmaker()() as session, session.begin():
        columns = {
            str(r.model_id): r
            for r in (
                await session.execute(
                    sa.text(
                        "SELECT model_id, "
                        + ", ".join(col for _, col in _PRICE_COLUMNS)
                        + " FROM model_profiles"
                    )
                )
            ).all()
        }
        for key, deployment in sorted(snapshot.deployments.items()):
            price = deployment.price_on(today)
            row = columns.get(key)
            if price is None or row is None or price.valid_from <= PRICES_FROM:
                continue
            changes = {
                col: getattr(price, attr)
                for attr, col in _PRICE_COLUMNS
                if getattr(price, attr) is not None and getattr(row, col) != getattr(price, attr)
            }
            if not changes:
                continue
            assignments = ", ".join(f"{col} = :{col}" for col in changes)
            await session.execute(
                sa.text(
                    f"UPDATE model_profiles SET {assignments}, updated_at = now() "
                    "WHERE model_id = :k"
                ),
                {**changes, "k": key},
            )
            await AuditRepository(session).record(
                actor=LIFECYCLE_ACTOR,
                action="deployment.price_applied",
                target=f"deployment:{key}",
                after={
                    "valid_from": price.valid_from.isoformat(),
                    **{c: str(v) for c, v in changes.items()},
                },
                platform=True,
            )
            applied.append(key)
    return applied


# ── la pasada del cron ─────────────────────────────────────────────────────


async def run_lifecycle(
    *, now: datetime | None = None, default_respond: str | None = None
) -> LifecycleReport:
    """Una pasada: avisos de retirada a 30 y a 7 días y lo que vence hoy (retiradas
    y precios). Idempotente: cada aviso se deduplica y lo hecho no se rehace."""
    moment = now or datetime.now(UTC)
    report = LifecycleReport()
    snapshot = await _snapshot()
    for key, deployment in sorted(snapshot.deployments.items()):
        if deployment.status != "retiring" or deployment.retire_after is None:
            continue
        if moment >= deployment.retire_after:
            await _retire_due(key, report, default_respond=default_respond, now=moment)
            continue
        proposals = await _proposals(key, default_respond=default_respond, snapshot=snapshot)
        report.retirement_notices += await _notify_retirement(
            key, retire_after=deployment.retire_after, now=moment, proposals=proposals
        )
    report.prices_applied = await _apply_due_prices(moment.date())
    if report.catalog_changed or report.moved_agents:
        catalog_changed()
    log.info(
        "model_lifecycle.tick",
        retirement_notices=report.retirement_notices,
        moved_agents=report.moved_agents,
        blocked=report.blocked,
        retired=report.retired,
        prices_applied=report.prices_applied,
    )
    return report


__all__ = [
    "LIFECYCLE_ACTOR",
    "PRICES_FROM",
    "RETIREMENT_NOTICE_DAYS",
    "USAGE_WINDOW_DAYS",
    "AgentInCatalog",
    "LifecycleError",
    "LifecycleReport",
    "Proposal",
    "add_price",
    "announce_retirement",
    "blocked_retirements",
    "cancel_retirement",
    "fixed_deployment",
    "guard_not_in_use",
    "mark_unavailable",
    "propose_substitute",
    "restore_available",
    "run_lifecycle",
    "scan_agents",
]
