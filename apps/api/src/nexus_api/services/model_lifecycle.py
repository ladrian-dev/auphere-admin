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
- **Precio** (41.8). Un precio entra con su fecha (``add_price``). Si sube más de
  un 10 % el precio estimado por mensaje de un agente —con lo que ese agente
  gastó los últimos 30 días, o con una llamada típica si no tiene tráfico—, su
  partner recibe ``model.price_change`` antes de que entre en vigor. En su
  fecha, el cron lo pasa a las columnas que lee el medidor.
- **«No disponible»** (41.9). ``mark_unavailable``: el router deja de usarlo
  desde el siguiente turno (``router_catalog.catalog_changed`` en este proceso
  y ``CATALOG_CHANGED`` por el canal de promoción en los demás).

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
from datetime import UTC, date, datetime, timedelta
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
from nexus_api.services.router_catalog import (
    AUTO_MODEL_POLICY,
    NOMINAL_ESTIMATE,
    CatalogSnapshot,
    Deployment,
    Price,
    TokenEstimate,
    catalog_changed,
    estimate_cost_micros,
    hard_reason,
    load_snapshot,
    model_policy_of,
)

log = structlog.get_logger(__name__)

#: Los avisos de retirada: a 30 días (o en cuanto se sabe) y a 7 (``events.md`` §3).
RETIREMENT_NOTICE_DAYS: tuple[int, ...] = (30, 7)
#: Un precio que sube el estimado por mensaje más que esto avisa (research, parte 7).
PRICE_ALERT_RATIO = Decimal("1.10")
#: Quien firma lo que hace el ciclo de vida solo.
LIFECYCLE_ACTOR = "system:model_lifecycle"
#: La ventana del perfil de turno de un agente (39.4).
USAGE_WINDOW_DAYS = 30
#: Desde aquí, los precios entran por ``model_prices`` (la 0180 copió los de
#: antes desde las columnas): solo los posteriores se pasan a las columnas del
#: medidor, así que un precio antiguo nunca pisa una columna.
PRICES_FROM: date = date(2026, 10, 27)
_CONVERSATION_TASKS = ("answer", "tool_turn")
_TOKEN_METERS = {
    "llm.input_tokens": "input_tokens",
    "llm.output_tokens": "output_tokens",
    "llm.cache_read": "cache_read_tokens",
    "llm.cache_write": "cache_write_tokens",
}


class LifecycleError(ValueError):
    """Una operación del catálogo que no se puede hacer, con su código."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


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


@dataclass(frozen=True)
class PriceAlert:
    partner_id: uuid.UUID
    deployment: str
    valid_from: date
    increase_pct: int
    agents: tuple[dict[str, Any], ...]


@dataclass
class LifecycleReport:
    """Lo que hizo una pasada del cron."""

    retirement_notices: int = 0
    price_notices: int = 0
    moved_agents: int = 0
    retired: list[str] = field(default_factory=list)
    prices_applied: list[str] = field(default_factory=list)
    #: Los clientes cuyos agentes cambiaron de versión: el worker los recarga.
    tenants_changed: set[uuid.UUID] = field(default_factory=set)

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


async def announce_retirement(
    key: str,
    *,
    retire_after: datetime,
    actor: str,
    reason: str | None = None,
    now: datetime | None = None,
    default_respond: str | None = None,
) -> list[Proposal]:
    """Auphere registra la fecha de retirada: ``retiring`` hasta entonces, y el
    aviso a los partners con agentes fijados si ya toca (con menos de 30 días,
    en el acto). Devuelve el sustituto propuesto a cada agente fijado."""
    moment = now or datetime.now(UTC)
    if retire_after.tzinfo is None:
        raise LifecycleError("naive_date", "retire_after necesita zona horaria")
    if retire_after <= moment:
        raise LifecycleError("in_the_past", "la fecha de retirada ya pasó")
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


async def _retire_due(key: str, report: LifecycleReport, *, default_respond: str | None) -> None:
    snapshot = await _snapshot()
    for proposal in await _proposals(key, default_respond=default_respond, snapshot=snapshot):
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


async def mark_unavailable(key: str, *, actor: str, reason: str) -> str:
    """El despliegue deja de cumplir su contrato o su licencia: el router deja
    de usarlo desde el siguiente turno. Devuelve el estado que tenía."""
    if not reason.strip():
        raise LifecycleError("reason_required", "hace falta el motivo")
    async with get_sessionmaker()() as session, session.begin():
        before = await session.scalar(
            sa.text("SELECT status FROM model_profiles WHERE model_id = :k FOR UPDATE"),
            {"k": key},
        )
        if before is None:
            raise LifecycleError("unknown_deployment", key)
        await session.execute(
            sa.text(
                "UPDATE model_profiles SET status = 'unavailable', updated_at = now() "
                "WHERE model_id = :k"
            ),
            {"k": key},
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


# ── precio (41.8) ──────────────────────────────────────────────────────────


def _usage_cost_micros(usage: Mapping[str, tuple[Decimal, Decimal]]) -> int:
    return int(sum((cost for _qty, cost in usage.values()), Decimal(0)) * 1_000_000)


def _estimate(usage: Mapping[str, tuple[Decimal, Decimal]]) -> TokenEstimate:
    tokens = {
        field_name: int(usage.get(meter, (Decimal(0), Decimal(0)))[0])
        for meter, field_name in _TOKEN_METERS.items()
    }
    return TokenEstimate(**tokens)


def message_price_ratio(
    agent: AgentInCatalog, key: str, *, old: Price, new: Price
) -> Decimal | None:
    """Cuánto cambia el precio estimado por mensaje del agente si ``key`` pasa
    de ``old`` a ``new``: con su perfil de turno de 30 días (39.4) —lo demás que
    gastó no cambia— o, sin tráfico con ese modelo, con una llamada típica."""
    on_key = agent.usage.get(key)
    if on_key:
        tokens = _estimate(on_key)
        old_cost, new_cost = estimate_cost_micros(old, tokens), estimate_cost_micros(new, tokens)
        total = sum(_usage_cost_micros(u) for u in agent.usage.values())
        other = max(0, total - _usage_cost_micros(on_key))
    else:
        old_cost = estimate_cost_micros(old, NOMINAL_ESTIMATE)
        new_cost = estimate_cost_micros(new, NOMINAL_ESTIMATE)
        other = 0
    if old_cost is None or new_cost is None or other + old_cost <= 0:
        return None
    return Decimal(other + new_cost) / Decimal(other + old_cost)


async def _price_alerts(
    key: str, price: Price, *, default_respond: str | None, now: datetime
) -> list[PriceAlert]:
    snapshot = await _snapshot()
    deployment = snapshot.deployments.get(key)
    old = deployment.price_on(price.valid_from - timedelta(days=1)) if deployment else None
    if old is None:
        return []
    agents = await scan_agents(
        default_respond=default_respond, usage_since=now - timedelta(days=USAGE_WINDOW_DAYS)
    )
    rows: dict[uuid.UUID, list[tuple[Decimal, AgentInCatalog]]] = {}
    for agent in agents:
        if agent.partner_id is None or not (agent.fixed_on == key or key in agent.usage):
            continue
        ratio = message_price_ratio(agent, key, old=old, new=price)
        if ratio is not None and ratio > PRICE_ALERT_RATIO:
            rows.setdefault(agent.partner_id, []).append((ratio, agent))
    alerts: list[PriceAlert] = []
    async with get_sessionmaker()() as session, session.begin():
        for partner_id, items in sorted(rows.items(), key=lambda kv: str(kv[0])):
            pct = _pct(max(r for r, _ in items))
            listed = tuple(
                a.notice_row(increase_pct=_pct(r))
                for r, a in sorted(items, key=lambda x: (str(x[1].client_ref), x[1].agent_name))
            )
            row = await console_notifications.emit(
                session,
                partner_id=partner_id,
                kind=NotificationKind.MODEL_PRICE_CHANGE,
                severity=NotificationSeverity.WARNING,
                data={
                    "deployment": key,
                    "valid_from": price.valid_from.isoformat(),
                    "increase_pct": pct,
                    "agents": list(listed),
                },
                dedupe_key=f"model.price_change:{key}:{price.valid_from.isoformat()}:{partner_id}",
            )
            if row is not None:
                alerts.append(PriceAlert(partner_id, key, price.valid_from, pct, listed))
    return alerts


async def add_price(
    key: str,
    price: Price,
    *,
    actor: str,
    today: date | None = None,
    default_respond: str | None = None,
) -> list[PriceAlert]:
    """Un precio nuevo con su vigencia y su fuente. Si sube más de un 10 % el
    precio estimado por mensaje de algún agente, avisa a su partner ya: antes de
    que entre en vigor. Devuelve los avisos enviados."""
    day = today or datetime.now(UTC).date()
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
    moment = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
    return await _price_alerts(key, price, default_respond=default_respond, now=moment)


def _pct(ratio: Decimal) -> int:
    """La subida en puntos enteros: 1,25 → 25."""
    return round((ratio - 1) * 100)


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
    """Una pasada: avisos de retirada a 30 y a 7 días, avisos de precio de lo
    que aún no está en vigor, y lo que vence hoy (retiradas y precios).
    Idempotente: cada aviso se deduplica y lo hecho no se rehace."""
    moment = now or datetime.now(UTC)
    report = LifecycleReport()
    snapshot = await _snapshot()
    for key, deployment in sorted(snapshot.deployments.items()):
        if deployment.status != "retiring" or deployment.retire_after is None:
            continue
        if moment >= deployment.retire_after:
            await _retire_due(key, report, default_respond=default_respond)
            continue
        proposals = await _proposals(key, default_respond=default_respond, snapshot=snapshot)
        report.retirement_notices += await _notify_retirement(
            key, retire_after=deployment.retire_after, now=moment, proposals=proposals
        )
    today = moment.date()
    for key, deployment in sorted(snapshot.deployments.items()):
        if deployment.status not in ("active", "retiring"):
            continue
        for price in deployment.prices:
            if price.valid_from > today:
                alerts = await _price_alerts(
                    key, price, default_respond=default_respond, now=moment
                )
                report.price_notices += len(alerts)
    report.prices_applied = await _apply_due_prices(today)
    if report.catalog_changed or report.moved_agents:
        catalog_changed()
    log.info(
        "model_lifecycle.tick",
        retirement_notices=report.retirement_notices,
        price_notices=report.price_notices,
        moved_agents=report.moved_agents,
        retired=report.retired,
        prices_applied=report.prices_applied,
    )
    return report


__all__ = [
    "LIFECYCLE_ACTOR",
    "PRICES_FROM",
    "PRICE_ALERT_RATIO",
    "RETIREMENT_NOTICE_DAYS",
    "USAGE_WINDOW_DAYS",
    "AgentInCatalog",
    "LifecycleError",
    "LifecycleReport",
    "PriceAlert",
    "Proposal",
    "add_price",
    "announce_retirement",
    "fixed_deployment",
    "mark_unavailable",
    "message_price_ratio",
    "propose_substitute",
    "run_lifecycle",
    "scan_agents",
]
