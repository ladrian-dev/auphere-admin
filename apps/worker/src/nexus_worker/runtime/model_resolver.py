"""Resolución de modelo: el router por tarea (spec 047) y los bindings (WP-19).

**El router (spec 047, T140, requisitos 40.1 a 40.12).** ``chain_for(task,
profile, ctx)`` es el único punto de decisión (research D20). Sigue los pasos del
contrato (``router-and-catalog.md`` §4):

1. **filtro duro** (``router_catalog.hard_filter``): activo, permitido al partner
   y al cliente, con las capacidades de la tarea, con la residencia del cliente,
   sin retención, y fuera de la restricción soberana si la tiene;
2. **calidad**: solo pares (despliegue, tarea) con certificación por clase
   vigente y nota ≥ el umbral del perfil; en las tareas de conversación, además,
   certificados **para ese agente**;
3. **orden**: el más barato dentro del objetivo de latencia p95;
4. **cadena**: el elegido y hasta dos alternativas en otros proveedores, con su
   misma residencia;
5. **registro**: la decisión lleva todo lo que ``llm.route_decision`` necesita y
   ningún texto; la emite el transporte cuando la usa (``LLMRouter``).

La **afinidad** de las tareas de conversación vive en el checkpoint del hilo
(``pinned_model``, garantía 4), por agente, y dura al menos lo que la caché del
proveedor; solo cambia si el proveedor falla, si caduca o si se publica otra
versión del agente. El **escalado** es una subllamada aislada: el bucle principal
no cambia de modelo. Los **límites** del turno (12 llamadas, techo de coste) y de
la conversación (3 escalados por hora) acaban en una persona.

Lo que **no** está aquí y hace ``pipeline.py`` (bloque C3): llamar al
clasificador tipado, leer las señales del grafo, pedir la subllamada y escribir
la afinidad en el estado. Este módulo le da la API.

**Los bindings (WP-19).** ``load_bindings`` y la forma antigua de ``chain_for``
(``chain_for(bindings, rol, default_model=…)``) siguen sirviendo al grafo de hoy
hasta que C3 lo pase al router; ``tenant_model_bindings`` sigue siendo el techo
del cliente (entra en ``RouteContext.allowed``).

- Se lee **dentro de la sesión ya scopeada del ``AgentLoader``**, no en una
  propia. Eso no es comodidad: ``tenant_model_bindings`` lleva RLS forzada y
  leerla ahí hace que el aislamiento lo imponga Postgres, no un WHERE que alguien
  pueda olvidar. Un tenant sin fila simplemente no ve ninguna.
- Sin binding, el rol cae a la configuración global.
- ``fallback_chain`` se guarda como cadenas y no como FKs porque un fallback que
  revienta al resolverse no es un fallback.
"""

from __future__ import annotations

import asyncio
import decimal
import hashlib
import json
import time
import uuid
from collections.abc import Iterator, Mapping, Sequence
from collections.abc import Set as AbstractSet
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Any, Literal, overload

import sqlalchemy as sa
import structlog
from nexus_api.services.router_catalog import (
    AGENT_PROFILES,
    NOMINAL_ESTIMATE,
    PINNED_BASE_PROFILE,
    TIERS,
    CatalogSnapshot,
    Deployment,
    ModelPolicy,
    NoPolicy,
    ProfilePolicy,
    Rejection,
    TaskPolicy,
    TaskSpec,
    TokenEstimate,
    estimate_cost_micros,
    hard_reason,
    model_policy_of,
    on_catalog_change,
)
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Bindings (WP-19)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ModelBinding:
    """Lo que un tenant eligió para un rol."""

    role: str
    model_id: str
    # Modelos a los que caer, en orden, antes del fallback global.
    fallback_chain: tuple[str, ...] = ()
    # Techo de coste por turno. Se lee ya para que el binding esté
    # completo; quien corta es WP-20.
    max_cost_per_turn_usd: decimal.Decimal | None = None

    def chain(self, *, global_fallback: str | None = None) -> tuple[str, ...]:
        """Cadena completa de intentos, sin repetidos y en orden."""
        models = [self.model_id, *self.fallback_chain]
        if global_fallback:
            models.append(global_fallback)
        # ``dict.fromkeys`` deduplica conservando el orden — importa: un
        # modelo repetido en la cadena se reintentaría dos veces y
        # duplicaría la latencia del peor caso sin ganar nada.
        return tuple(dict.fromkeys(m for m in models if m))


_BINDINGS_SQL = sa.text(
    """
    SELECT b.role,
           p.model_id,
           b.fallback_chain,
           b.max_cost_per_turn_usd
      FROM tenant_model_bindings b
      JOIN model_profiles p ON p.id = b.model_profile_id
    """
)


async def load_bindings(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, ModelBinding]:
    """Bindings del tenant activo en la sesión.

    Sin ``WHERE tenant_id``: la sesión ya está scopeada y la RLS de la
    tabla es quien filtra. Añadir el WHERE aquí escondería una RLS rota
    en vez de dejar que un test de aislamiento la cace.
    """
    try:
        rows = (await session.execute(_BINDINGS_SQL)).all()
    except Exception as exc:
        # Un fallo leyendo la elección de modelo no puede tumbar el turno:
        # sin bindings el runtime usa la configuración global, que es
        # exactamente el comportamiento de antes de WP-19.
        log.warning("model_resolver.load_failed", tenant_id=str(tenant_id), error=str(exc))
        return {}

    bindings: dict[str, ModelBinding] = {}
    for role, model_id, fallback_chain, max_cost in rows:
        chain: Sequence[object] = fallback_chain if isinstance(fallback_chain, list) else ()
        bindings[role] = ModelBinding(
            role=role,
            model_id=model_id,
            fallback_chain=tuple(str(m) for m in chain if isinstance(m, str) and m),
            max_cost_per_turn_usd=max_cost,
        )
    return bindings


def _legacy_chain_for(
    bindings: Mapping[str, ModelBinding],
    role: str,
    *,
    default_model: str,
    global_fallback: str | None = None,
) -> tuple[str, ...]:
    """Cadena de modelos para un rol, con caída a la configuración global."""
    binding = bindings.get(role)
    if binding is None:
        models = [default_model, global_fallback] if global_fallback else [default_model]
        return tuple(dict.fromkeys(m for m in models if m))
    return binding.chain(global_fallback=global_fallback)


# ═══════════════════════════════════════════════════════════════════════════
# El router por tarea (spec 047)
# ═══════════════════════════════════════════════════════════════════════════

#: La afinidad dura al menos esto: la caché de Claude dura una hora (40.3).
PIN_MIN_TTL_S = 3600
#: La ventana del techo de escalados (40.10).
ESCALATION_WINDOW_S = 3600
#: El elegido y hasta dos alternativas (40.2.4).
CHAIN_LENGTH = 3

Outcome = Literal["routed", "pinned", "agent_pinned", "reserve_model", "no_model"]


@dataclass(frozen=True)
class RouteHint:
    """Lo que puede aportar un modelo de decisión tipada (40.11): una preferencia
    **entre los que ya pasaron el filtro**, nunca un candidato nuevo."""

    prefer: str | None = None
    complexity: str | None = None
    risk: str | None = None


@dataclass(frozen=True)
class PinnedModel:
    """La afinidad de un agente en una conversación (``AgentState.pinned_model``)."""

    deployment: str
    agent_version: str | None
    pinned_at: float
    expires_at: float

    def broken_by(self, *, agent_version: str | None, now: float) -> str | None:
        """Por qué ya no vale, o None si vale."""
        if now >= self.expires_at:
            return "expired"
        if agent_version != self.agent_version:
            return "new_version"
        return None

    def to_state(self) -> dict[str, Any]:
        return {
            "deployment": self.deployment,
            "agent_version": self.agent_version,
            "pinned_at": self.pinned_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_state(cls, value: Any) -> PinnedModel | None:
        if not isinstance(value, Mapping):
            return None
        try:
            return cls(
                deployment=str(value["deployment"]),
                agent_version=(
                    None if value.get("agent_version") is None else str(value["agent_version"])
                ),
                pinned_at=float(value["pinned_at"]),
                expires_at=float(value["expires_at"]),
            )
        except (KeyError, TypeError, ValueError):
            return None


@dataclass(frozen=True)
class RouteContext:
    """Todo lo que el router necesita saber del turno, sin texto."""

    tenant_id: uuid.UUID
    catalog: CatalogSnapshot
    agent_id: uuid.UUID | None = None
    #: La versión publicada del agente: otra versión rompe la afinidad.
    agent_version: str | None = None
    turn_id: str | None = None
    job_id: str | None = None
    #: La conversación del turno (``events.md`` §5); None fuera de un turno.
    conversation_id: str | None = None
    #: Techo de modelos del partner y del cliente (``partner_model_allowlist`` ∩
    #: ``tenant_model_bindings``). None = sin techo declarado.
    allowed: AbstractSet[str] | None = None
    eu_only: bool = False
    sovereign: bool = False
    #: Despliegues con certificación vigente **de este agente** (42.3).
    agent_certified: AbstractSet[str] = frozenset()
    #: La afinidad leída del hilo para este agente.
    pinned: PinnedModel | None = None
    #: ``model_policy`` = ``pinned`` en el AgentSpec (39.1, 39.8).
    agent_pinned_deployment: str | None = None
    min_context: int | None = None
    #: La familia juzgada, para la tarea ``judge`` (42.5).
    judged_family: str | None = None
    cooled: AbstractSet[str] = frozenset()
    #: Lo que se espera que ocupe la llamada. Sin estimación se ordena con
    #: ``NOMINAL_ESTIMATE`` y el techo por llamada no se comprueba.
    estimate: TokenEstimate | None = None
    hint: RouteHint | None = None
    #: Ventana de gama para el escalado: estrictamente por encima del suelo y
    #: hasta el techo, incluido.
    tier_floor: str | None = None
    tier_ceiling: str | None = None
    #: Reloj de la afinidad y de los escalados (segundos desde la época).
    now: float | None = None
    #: El día de los precios vigentes; por defecto, hoy.
    today: date | None = None


@dataclass(frozen=True)
class RouteDecision:
    """Una decisión del router. Lleva cliente y agente, nunca texto."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    agent_id: uuid.UUID | None
    agent_version: str | None
    turn_id: str | None
    job_id: str | None
    task: str
    conversation: bool
    profile: str
    policy_version: int
    chain: tuple[Deployment, ...]
    rejected: tuple[Rejection, ...]
    outcome: Outcome
    reasoning: str = "none"
    cache_key: str | None = None
    escalated: bool = False
    estimated_cost_micros: int | None = None
    #: Por qué no siguió la afinidad que había, si había una.
    pin_broken: str | None = None
    #: La conversación del turno, para ``llm.route_decision`` (``events.md`` §5).
    conversation_id: str | None = None

    @property
    def models(self) -> tuple[str, ...]:
        return tuple(d.key for d in self.chain)

    @property
    def chosen(self) -> str | None:
        return self.chain[0].key if self.chain else None

    @property
    def anomaly(self) -> str | None:
        """``router_anomalies.kind`` que esta decisión pide escribir, si alguna."""
        if self.outcome in ("reserve_model", "no_model"):
            return self.outcome
        return None


def cache_key_for(tenant_id: uuid.UUID, agent_version: str | None) -> str:
    """La clave de caché del proveedor, **por cliente y versión** (41.4).

    Opaca: el proveedor ve un hash, no el id del cliente."""
    raw = f"{tenant_id}:{agent_version or '-'}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _tier_rank(tier: str | None) -> int:
    return TIERS.index(tier) if tier in TIERS else -1


def _quality_reason(
    deployment: Deployment, spec: TaskSpec, policy: TaskPolicy, ctx: RouteContext
) -> str | None:
    cert = ctx.catalog.class_cert(deployment.key, spec.code)
    if cert is None:
        return "not_certified"
    if cert.quality < policy.min_quality:
        return "below_quality"
    if spec.conversation and deployment.key not in ctx.agent_certified:
        return "agent_not_certified"
    if (
        policy.latency_p95_ms is not None
        and cert.latency_p95_ms is not None
        and cert.latency_p95_ms > policy.latency_p95_ms
    ):
        return "over_latency"
    return None


def _tier_reason(deployment: Deployment, ctx: RouteContext) -> str | None:
    if ctx.tier_ceiling is None and ctx.tier_floor is None:
        return None
    rank = _tier_rank(deployment.capabilities.tier)
    if rank < 0:
        return "tier"
    if ctx.tier_floor is not None and rank <= _tier_rank(ctx.tier_floor):
        return "tier"
    if ctx.tier_ceiling is not None and rank > _tier_rank(ctx.tier_ceiling):
        return "tier"
    return None


def _cost(deployment: Deployment, estimate: TokenEstimate, ctx: RouteContext) -> int | None:
    price = deployment.price_on(ctx.today or datetime.now(UTC).date())
    return None if price is None else estimate_cost_micros(price, estimate)


def _with_alternatives(first: Deployment, ordered: Sequence[Deployment]) -> tuple[Deployment, ...]:
    """El elegido y hasta dos alternativas en proveedores distintos, con su
    misma residencia (40.2.4): una caída de proveedor no puede llevarse la
    cadena entera, ni sacar el turno de la residencia."""
    chain = [first]
    providers = {first.provider}
    for candidate in ordered:
        if len(chain) == CHAIN_LENGTH:
            break
        if candidate.key == first.key or candidate.provider in providers:
            continue
        if candidate.residency != first.residency:
            continue
        chain.append(candidate)
        providers.add(candidate.provider)
    return tuple(chain)


def _constraints(ctx: RouteContext) -> dict[str, Any]:
    return {
        "allowed": ctx.allowed,
        "eu_only": ctx.eu_only,
        "sovereign": ctx.sovereign,
        "min_context": ctx.min_context,
        "judged_family": ctx.judged_family,
        "cooled": ctx.cooled,
    }


@overload
def chain_for(task: str | None, profile: ProfilePolicy, ctx: RouteContext, /) -> RouteDecision: ...
@overload
def chain_for(
    task: Mapping[str, ModelBinding],
    profile: str,
    ctx: None = None,
    /,
    *,
    default_model: str,
    global_fallback: str | None = None,
) -> tuple[str, ...]: ...
def chain_for(
    task: str | None | Mapping[str, ModelBinding],
    profile: ProfilePolicy | str,
    ctx: RouteContext | None = None,
    /,
    *,
    default_model: str | None = None,
    global_fallback: str | None = None,
) -> RouteDecision | tuple[str, ...]:
    """La cadena de una llamada.

    ``chain_for(task, profile, ctx)`` es el router de la spec 047 y devuelve una
    :class:`RouteDecision`. ``chain_for(bindings, rol, default_model=…)`` es la
    forma de WP-19 que usa hoy ``pipeline.py``; desaparece cuando C3 pase el
    grafo al router.
    """
    if isinstance(task, Mapping):
        assert isinstance(profile, str) and default_model is not None
        return _legacy_chain_for(
            task, profile, default_model=default_model, global_fallback=global_fallback
        )
    assert isinstance(profile, ProfilePolicy) and ctx is not None
    return _route(task, profile, ctx)


def _route(task: str | None, profile: ProfilePolicy, ctx: RouteContext) -> RouteDecision:
    spec = ctx.catalog.taxonomy.require(task)
    policy = profile.task(spec.code)
    if policy is None:
        raise NoPolicy(f"el perfil {profile.profile} v{profile.version} no fija {spec.code}")
    now = ctx.now if ctx.now is not None else time.time()
    constraints = _constraints(ctx)
    rejected: list[Rejection] = []
    survivors: list[Deployment] = []
    for deployment in sorted(ctx.catalog.deployments.values(), key=lambda d: d.key):
        reason = (
            hard_reason(deployment, spec, **constraints)
            or _tier_reason(deployment, ctx)
            or _quality_reason(deployment, spec, policy, ctx)
        )
        if reason is not None:
            rejected.append(Rejection(deployment.key, reason))
        else:
            survivors.append(deployment)

    estimate = ctx.estimate or NOMINAL_ESTIMATE
    priced: list[tuple[int, Deployment]] = []
    for deployment in survivors:
        cost = _cost(deployment, estimate, ctx)
        if cost is None:
            rejected.append(Rejection(deployment.key, "unpriced"))
        elif (
            ctx.estimate is not None
            and policy.max_cost_per_call_micros is not None
            and cost > policy.max_cost_per_call_micros
        ):
            rejected.append(Rejection(deployment.key, "over_cost"))
        else:
            priced.append((cost, deployment))
    priced.sort(key=lambda item: (item[0], item[1].key))
    ordered = [d for _, d in priced]

    # El modelo tipado puede preferir, nunca añadir (40.11).
    if ctx.hint and ctx.hint.prefer:
        preferred = [d for d in ordered if d.key == ctx.hint.prefer]
        ordered = preferred + [d for d in ordered if d.key != ctx.hint.prefer]

    outcome: Outcome = "routed"
    pin_broken: str | None = None
    first: Deployment | None = ordered[0] if ordered else None

    if spec.conversation and ctx.agent_pinned_deployment:
        # «Fijar un modelo»: una persona lo eligió y la consola lo comprobó al
        # guardar (39.7, 39.9). Aquí solo el filtro duro: si dejó de cumplirlo
        # (no disponible, otra residencia), deja de usarse.
        fixed = ctx.catalog.deployments.get(ctx.agent_pinned_deployment)
        reason = (
            "unknown"
            if fixed is None
            else hard_reason(fixed, spec, **constraints) or _tier_reason(fixed, ctx)
        )
        if fixed is not None and reason is None:
            first, outcome = fixed, "agent_pinned"
            ordered = [fixed, *[d for d in ordered if d.key != fixed.key]]
        else:
            rejected.append(Rejection(ctx.agent_pinned_deployment, f"agent_pinned:{reason}"))
    elif spec.conversation and ctx.pinned is not None:
        pin_broken = ctx.pinned.broken_by(agent_version=ctx.agent_version, now=now)
        if pin_broken is None:
            held = next((d for d in ordered if d.key == ctx.pinned.deployment), None)
            if held is not None:
                first, outcome = held, "pinned"
            else:
                pin_broken = next(
                    (r.reason for r in rejected if r.deployment == ctx.pinned.deployment),
                    "gone",
                )

    chain: tuple[Deployment, ...] = ()
    if first is not None:
        chain = _with_alternatives(first, ordered)
    elif policy.reserve:
        reserve = ctx.catalog.deployments.get(policy.reserve)
        if reserve is not None and hard_reason(reserve, spec, **constraints) is None:
            chain, outcome = (reserve,), "reserve_model"
        else:
            outcome = "no_model"
    else:
        outcome = "no_model"

    cost_micros = _cost(chain[0], estimate, ctx) if chain else None
    return RouteDecision(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        agent_id=ctx.agent_id,
        agent_version=ctx.agent_version,
        turn_id=ctx.turn_id,
        job_id=ctx.job_id,
        task=spec.code,
        conversation=spec.conversation,
        profile=profile.profile,
        policy_version=profile.version,
        chain=chain,
        rejected=tuple(rejected),
        outcome=outcome,
        reasoning=policy.reasoning,
        cache_key=cache_key_for(ctx.tenant_id, ctx.agent_version),
        escalated=ctx.tier_ceiling is not None,
        estimated_cost_micros=cost_micros,
        pin_broken=pin_broken,
        conversation_id=ctx.conversation_id,
    )


# ── el catálogo en memoria ─────────────────────────────────────────────────

#: Como el catálogo de precios (``metering.pricing``): el retraso máximo en ver
#: un despliegue nuevo, un «No disponible» o un perfil publicado. El requisito
#: 41.9 pide «desde el siguiente turno»; quien publica llama a
#: ``invalidate_catalog`` en el proceso que lo hace y los demás lo ven en 5 min.
CATALOG_TTL_S = 300.0

_snapshot: CatalogSnapshot | None = None
_snapshot_at = 0.0
_snapshot_lock = asyncio.Lock()


async def _load_snapshot_from_db() -> CatalogSnapshot:
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.services.router_catalog import load_snapshot

    async with get_sessionmaker()() as session:
        return await load_snapshot(session)


async def get_catalog_snapshot(*, force: bool = False) -> CatalogSnapshot:
    """El catálogo de plataforma, leído como mucho una vez cada ``CATALOG_TTL_S``.
    Si una lectura falla se sigue con el anterior: un catálogo de hace seis
    minutos vale más que ninguno."""
    global _snapshot, _snapshot_at
    fresh = _snapshot is not None and time.monotonic() - _snapshot_at < CATALOG_TTL_S
    if fresh and not force and _snapshot is not None:
        return _snapshot
    async with _snapshot_lock:
        if not force and _snapshot is not None and time.monotonic() - _snapshot_at < CATALOG_TTL_S:
            return _snapshot
        try:
            _snapshot = await _load_snapshot_from_db()
            _snapshot_at = time.monotonic()
        except Exception as exc:
            log.error("model_resolver.catalog_load_failed", error=str(exc), stale=bool(_snapshot))
            if _snapshot is None:
                raise
        return _snapshot


def invalidate_catalog() -> None:
    global _snapshot, _snapshot_at
    _snapshot = None
    _snapshot_at = 0.0


# Lo que el admin o el cron del ciclo de vida cambian en este proceso se ve en el
# siguiente turno (41.9, 40.13); los demás procesos lo oyen por el canal de
# promoción (``runtime/promote_subscriber.py``).
on_catalog_change(invalidate_catalog)


# ── afinidad en el estado del hilo ─────────────────────────────────────────


def pin_after(
    decision: RouteDecision,
    *,
    served: str,
    now: float,
    previous: PinnedModel | None = None,
    agent_version: str | None = None,
) -> PinnedModel | None:
    """La afinidad que queda tras una llamada de conversación que respondió
    ``served``. Se desliza con el uso, como la caché del proveedor; si respondió
    una alternativa (el proveedor del fijado falló), pasa a ella. None en las
    tareas que no son de conversación: no fijan modelo."""
    if not decision.conversation or decision.escalated or not served:
        return None
    deployment = next((d for d in decision.chain if d.key == served), None)
    ttl = PIN_MIN_TTL_S
    if deployment is not None and deployment.capabilities.cache_ttl_s:
        ttl = max(ttl, deployment.capabilities.cache_ttl_s)
    version = agent_version if agent_version is not None else decision.agent_version
    if (
        previous is not None
        and previous.deployment == served
        and previous.agent_version == version
        and now < previous.expires_at
    ):
        return replace(previous, expires_at=now + ttl)
    return PinnedModel(
        deployment=served, agent_version=version, pinned_at=now, expires_at=now + ttl
    )


def _agent_key(agent_id: uuid.UUID | str | None) -> str:
    return "" if agent_id is None else str(agent_id)


def pins_from_state(state: Mapping[str, Any]) -> dict[str, PinnedModel]:
    """Las afinidades del hilo, por agente (``""`` = el agente principal)."""
    raw = state.get("pinned_model")
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, PinnedModel] = {}
    for agent, value in raw.items():
        pin = PinnedModel.from_state(value)
        if pin is not None:
            out[str(agent)] = pin
    return out


def pinned_for(state: Mapping[str, Any], agent_id: uuid.UUID | str | None) -> PinnedModel | None:
    return pins_from_state(state).get(_agent_key(agent_id))


def with_pin(
    current: Mapping[str, Any] | None,
    agent_id: uuid.UUID | str | None,
    pin: PinnedModel | None,
) -> dict[str, Any]:
    """El valor nuevo de ``AgentState.pinned_model`` (reemplazo, no reductor)."""
    out = dict(current or {})
    key = _agent_key(agent_id)
    if pin is None:
        out.pop(key, None)
    else:
        out[key] = pin.to_state()
    return out


# ── escalado ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TurnSignals:
    """Las señales de dificultad **del grafo**, no del texto (40.4)."""

    #: Una herramienta rechazó sus argumentos al validarlos.
    tool_args_rejected: bool = False
    #: Cuántas veces el agente ha repreguntado el mismo dato.
    repeated_ask: int = 0
    #: El juez dio el turno en rojo.
    judge_red: bool = False
    #: Cuántas intenciones trae el mensaje.
    intents: int = 1
    #: Iteraciones del bucle con herramientas.
    tool_iterations: int = 0

    def fired(self) -> tuple[str, ...]:
        fired = []
        if self.tool_args_rejected:
            fired.append("tool_args_rejected")
        if self.repeated_ask >= 2:
            fired.append("repeated_ask")
        if self.judge_red:
            fired.append("judge_red")
        if self.intents > 1:
            fired.append("multi_intent")
        if self.tool_iterations > 4:
            fired.append("long_tool_loop")
        return tuple(fired)


@dataclass(frozen=True)
class EscalationVerdict:
    """``none``: seguir; ``subcall``: subllamada aislada con ``decision``;
    ``handoff``: pasar a una persona con ``reason`` (``events.md`` §2)."""

    action: Literal["none", "subcall", "handoff"]
    signals: tuple[str, ...] = ()
    reason: str | None = None
    decision: RouteDecision | None = None


def record_escalation(escalations_at: Sequence[float], *, now: float) -> list[float]:
    """La ventana de la última hora con este escalado (``router_escalations``)."""
    recent = [t for t in escalations_at if now - t < ESCALATION_WINDOW_S]
    return [*recent, now]


def escalation_for(
    signals: TurnSignals,
    *,
    origin_task: str,
    profile: ProfilePolicy,
    ctx: RouteContext,
    current_tier: str | None,
    escalations_at: Sequence[float],
    now: float | None = None,
) -> EscalationVerdict:
    """Qué hacer cuando el turno da señales (40.4, 40.10).

    La subllamada va por la tarea ``escalate`` con la ventana de gama
    ``(current_tier, escalate_to]``. «Económico» no escala: pasa a una persona.
    """
    fired = signals.fired()
    if not fired:
        return EscalationVerdict("none")
    if profile.profile == "economy":
        return EscalationVerdict("handoff", fired, reason="escalated")
    origin = profile.task(origin_task)
    if origin is None or origin.escalate_to is None:
        return EscalationVerdict("none", fired)
    moment = now if now is not None else (ctx.now if ctx.now is not None else time.time())
    recent = [t for t in escalations_at if moment - t < ESCALATION_WINDOW_S]
    if len(recent) >= profile.max_escalations_per_hour:
        return EscalationVerdict("handoff", fired, reason="turn_limit")
    sub = replace(
        ctx,
        tier_floor=current_tier,
        tier_ceiling=origin.escalate_to,
        pinned=None,
        agent_pinned_deployment=None,
        now=moment,
    )
    decision = _route("escalate", profile, sub)
    if decision.outcome == "no_model":
        return EscalationVerdict("handoff", fired, reason="no_model", decision=decision)
    return EscalationVerdict("subcall", fired, decision=decision)


# ── límites del turno (40.10) ──────────────────────────────────────────────


class TurnLimitReached(RuntimeError):
    """El turno llegó a su techo: la conversación pasa a una persona con el
    motivo ``turn_limit``."""

    reason = "turn_limit"

    def __init__(self, limit: Literal["calls", "cost"], detail: str) -> None:
        super().__init__(detail)
        self.limit = limit


@dataclass
class TurnBudget:
    """Llamadas y coste del turno en curso, contra los techos de su perfil."""

    max_calls: int
    cost_ceiling_micros: int | None
    calls: int = 0
    cost_micros: int = 0

    @classmethod
    def for_profile(cls, profile: ProfilePolicy) -> TurnBudget:
        return cls(
            max_calls=profile.max_calls_per_turn,
            cost_ceiling_micros=profile.turn_cost_ceiling_micros,
        )

    def before_call(self) -> None:
        if self.calls >= self.max_calls:
            raise TurnLimitReached("calls", f"{self.calls} llamadas de {self.max_calls}")
        if self.cost_ceiling_micros is not None and self.cost_micros >= self.cost_ceiling_micros:
            raise TurnLimitReached("cost", f"{self.cost_micros} µUSD de {self.cost_ceiling_micros}")
        self.calls += 1

    def add_cost(self, micros: int) -> None:
        self.cost_micros += max(0, int(micros))


_turn_budget: ContextVar[TurnBudget | None] = ContextVar("router_turn_budget", default=None)


@contextmanager
def turn_budget(budget: TurnBudget) -> Iterator[TurnBudget]:
    """Activa los techos del turno para todas las llamadas que salgan dentro."""
    token = _turn_budget.set(budget)
    try:
        yield budget
    finally:
        _turn_budget.reset(token)


def current_turn_budget() -> TurnBudget | None:
    return _turn_budget.get()


# ── la clasificación tipada (40.5) ─────────────────────────────────────────


class ClassifyResult(BaseModel):
    """Lo que devuelve el clasificador: un objeto, nunca una etiqueta suelta.

    ``intents`` es cuántas peticiones distintas trae el mensaje: con más de una,
    el turno da la señal de escalado «varias intenciones» (40.4). Es obligatorio
    como el resto: la salida estructurada estricta pide todas las propiedades."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: str = Field(min_length=1, max_length=40)
    needs_tools: StrictBool
    risk: Literal["low", "medium", "high"]
    complexity: Literal["low", "medium", "high"]
    language: str = Field(min_length=2, max_length=8)
    intents: int = Field(ge=1, le=5)


#: El esquema para la salida estructurada estricta. ``strict`` en OpenAI pide
#: todas las propiedades requeridas y ``additionalProperties: false``: la
#: configuración del modelo lo da.
CLASSIFY_SCHEMA: dict[str, Any] = ClassifyResult.model_json_schema()


def parse_classification(raw: str) -> ClassifyResult | None:
    """La validación propia, **siempre**, aunque el proveedor sea estricto."""
    try:
        return ClassifyResult.model_validate(json.loads(raw))
    except (ValueError, TypeError, ValidationError):
        return None


# ── la subllamada de escalado (40.4) ───────────────────────────────────────


class EscalationResult(BaseModel):
    """Lo que devuelve la subllamada aislada de escalado: un consejo para el
    bucle principal (que no cambia de modelo) o que lo lleve una persona."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    guidance: str = Field(min_length=1, max_length=1500)
    handoff: StrictBool


# ── lo que el router sabe del cliente (40.2.1) ─────────────────────────────


@dataclass(frozen=True)
class RouteFacts:
    """Lo del cliente y del agente que entra en el filtro duro y en la calidad.

    Se lee con la RLS del cliente (``tenant_scoped_session``) y con el GUC del
    partner para su lista permitida: nada de otro cliente entra aquí."""

    eu_only: bool = False
    sovereign: bool = False
    #: ``partner_model_allowlist`` del partner, si tiene lista. Es el techo de
    #: las tareas de conversación (39.7, 40.2.1).
    partner_allowed: frozenset[str] | None = None
    #: Los despliegues certificados **para este agente** (42.3).
    agent_certified: frozenset[str] = frozenset()
    #: True si no se pudo leer: entonces «Solo UE» por si acaso (falla cerrado).
    degraded: bool = False

    @classmethod
    def unreadable(cls) -> RouteFacts:
        return cls(eu_only=True, degraded=True)


_FACTS_SQL = sa.text("SELECT eu_only, sovereign FROM business_profiles")


async def load_route_facts(
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID | None,
    *,
    partner_id: uuid.UUID | None = None,
) -> RouteFacts:
    """Los hechos del cliente para el router. Sin ``WHERE tenant_id``: la sesión
    va con el GUC del cliente y la RLS filtra (garantía 1). Si algo falla, falla
    cerrado: «Solo UE» y sin certificaciones del agente."""
    from nexus_api.core.partner_allowlist import read_allowlist
    from nexus_api.core.partner_context import apply_partner_to_session
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.services.certification import certified_deployments_for_agent

    try:
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            row = (await session.execute(_FACTS_SQL)).one_or_none()
            certified: frozenset[str] = frozenset()
            if agent_id is not None:
                certified = await certified_deployments_for_agent(
                    session, agent_id=agent_id, agent_config_id=None, suite_revision=None
                )
        allowed: frozenset[str] | None = None
        if partner_id is not None:
            async with sm() as session, session.begin():
                await apply_partner_to_session(session, partner_id)
                allowed = await read_allowlist(session, partner_id) or None
    except Exception as exc:
        log.warning("model_resolver.facts_unreadable", tenant_id=str(tenant_id), error=str(exc))
        return RouteFacts.unreadable()
    return RouteFacts(
        eu_only=bool(row.eu_only) if row is not None else False,
        sovereign=bool(row.sovereign) if row is not None else False,
        partner_allowed=allowed,
        agent_certified=certified,
    )


def could_route(snapshot: CatalogSnapshot, task: str) -> bool:
    """¿Hay algún despliegue que pueda ganar ``task`` para algún cliente?

    Activo, con retención cero y subprocesador, con las capacidades de la tarea
    y con certificación por clase vigente. Es la comprobación barata, en memoria,
    que deja a los agentes de hoy sin una lectura más por turno mientras nada
    pase el filtro (research D44)."""
    spec = snapshot.taxonomy.tasks.get(task)
    if spec is None:
        return False
    return any(
        hard_reason(d, spec) is None and snapshot.class_cert(d.key, task) is not None
        for d in snapshot.deployments.values()
    )


__all__ = [
    "AGENT_PROFILES",
    "CATALOG_TTL_S",
    "CHAIN_LENGTH",
    "CLASSIFY_SCHEMA",
    "ESCALATION_WINDOW_S",
    "PINNED_BASE_PROFILE",
    "PIN_MIN_TTL_S",
    "ClassifyResult",
    "EscalationResult",
    "EscalationVerdict",
    "ModelBinding",
    "ModelPolicy",
    "PinnedModel",
    "RouteContext",
    "RouteDecision",
    "RouteFacts",
    "RouteHint",
    "TurnBudget",
    "TurnLimitReached",
    "TurnSignals",
    "cache_key_for",
    "chain_for",
    "could_route",
    "current_turn_budget",
    "escalation_for",
    "get_catalog_snapshot",
    "invalidate_catalog",
    "load_bindings",
    "load_route_facts",
    "model_policy_of",
    "parse_classification",
    "pin_after",
    "pinned_for",
    "pins_from_state",
    "record_escalation",
    "turn_budget",
    "with_pin",
]
