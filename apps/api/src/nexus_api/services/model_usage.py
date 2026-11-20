"""¿Está en uso un modelo? — spec 059 (requisitos 1.1, 1.2 y 1.5; research D2 y D3).

Un modelo está **en uso** si se cumple cualquiera de estas tres cosas:

- **la plataforma lo usa por defecto**: el registro de
  ``nexus_worker.platform_models.default_models``, calculado aquí y publicado por el
  latido de cada worker (1.1 y 1.5);
- **responde con él algún agente activo**: por la asignación de su cliente, por su
  propia elección o por el modelo por defecto (1.2);
- **algún cliente lo tiene asignado**, en cualquier rol.

«Retirar» y «No disponible» no se pueden aplicar a un modelo en uso. Tampoco se
pueden aplicar si no se puede **verificar** qué usa el worker de verdad: un latido
que falta, uno de una versión que no publica sus modelos, o uno que publica otros.
Por eso ``ModelUses.verified`` es tan parte de la respuesta como los usos.

El barrido de agentes y asignaciones recorre **todos** los clientes, cada uno bajo su
propio GUC (garantía 1, ``tests/isolation/test_model_usage_scan_rls.py``), y de él
solo salen recuentos y nombres de cliente.
"""

from __future__ import annotations

import json
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Final, Literal

import sqlalchemy as sa
import structlog

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker

log = structlog.get_logger(__name__)

#: El latido del worker (``nexus_worker.health``): ``nexus:health:{servicio}:{instancia}``.
HEARTBEAT_PREFIX: Final = "nexus:health:"
#: La versión de lo que publica el latido. Otra versión cuenta como sin publicar.
HEARTBEAT_VERSION: Final = 1
#: El listado de Modelos cachea el barrido; las guardas nunca.
LIST_CACHE_TTL_S: Final = 60.0

Problem = Literal["no_heartbeat", "unpublished", "mismatch"]


@dataclass(frozen=True)
class ClientUsage:
    """Lo que sale del barrido para un modelo: cuántos agentes responden con él y
    qué clientes lo usan (por sus agentes o por una asignación)."""

    agents: int = 0
    clients: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelUses:
    defaults: tuple[str, ...] = ()
    agents: int = 0
    clients: tuple[str, ...] = ()
    verified: bool = True
    problem: Problem | None = None

    @property
    def in_use(self) -> bool:
        return bool(self.defaults or self.agents or self.clients)

    def to_contract(self) -> dict[str, Any]:
        return {
            "defaults": list(self.defaults),
            "agents": self.agents,
            "clients": list(self.clients),
            "verified": self.verified,
            "problem": self.problem,
        }


@dataclass
class _Tally:
    agents: int = 0
    clients: set[str] = field(default_factory=set)


_TENANTS_SQL = sa.text("SELECT id, name FROM tenants WHERE status <> 'archived' ORDER BY name")
#: Spec 065 (T081): cada agente no archivado con su versión activa (si la tiene) y su
#: elección. Uno con elección y aún sin versión también tiene el modelo en uso (8.1).
_AGENTS_SQL = sa.text(
    """
    SELECT c.policies, p.model_id AS chosen
      FROM agents a
      LEFT JOIN agent_configs c ON c.agent_id = a.id AND c.status = 'active'
      LEFT JOIN model_profiles p ON p.id = a.respond_model_profile_id
     WHERE a.status <> 'archived'
       AND (c.id IS NOT NULL OR a.respond_model_profile_id IS NOT NULL)
    """
)
#: Las asignaciones de cliente que siguen vivas. La de ``respond`` ya no la lee nadie: la
#: 0240 la pasó a los agentes y la borra la migración siguiente.
_BINDINGS_SQL = sa.text(
    "SELECT b.role, p.model_id FROM tenant_model_bindings b "
    "JOIN model_profiles p ON p.id = b.model_profile_id WHERE b.role <> 'respond'"
)

_list_cache: tuple[float, dict[str, ClientUsage]] | None = None


def invalidate() -> None:
    """Olvida el barrido cacheado del listado."""
    global _list_cache
    _list_cache = None


async def scan_usage() -> dict[str, ClientUsage]:
    """``modelo → ClientUsage`` de todos los clientes, cada uno bajo su GUC."""
    from nexus_api.core.respond_catalog import agent_respond_default
    from nexus_api.services.model_lifecycle import fixed_deployment

    # El modelo de los agentes sin elección (spec 065, requisito 13), no el de la plataforma:
    # ese otro lo pone en uso el registro de usos por defecto.
    default_respond = agent_respond_default()
    tally: dict[str, _Tally] = defaultdict(_Tally)
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        tenants = [(uuid.UUID(str(t)), str(n)) for t, n in (await session.execute(_TENANTS_SQL))]
    for tenant_id, name in tenants:
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            bindings = [(str(r), str(m)) for r, m in (await session.execute(_BINDINGS_SQL)).all()]
            for policies, chosen in (await session.execute(_AGENTS_SQL)).all():
                fixed_on, _how = fixed_deployment(
                    policies, choice=chosen, default_respond=default_respond
                )
                if fixed_on:
                    tally[fixed_on].agents += 1
                    tally[fixed_on].clients.add(name)
            for _role, model_id in bindings:
                tally[model_id].clients.add(name)
    return {
        key: ClientUsage(agents=t.agents, clients=tuple(sorted(t.clients)))
        for key, t in tally.items()
    }


async def _scan(*, cached: bool) -> dict[str, ClientUsage]:
    global _list_cache
    if cached and _list_cache is not None and time.monotonic() - _list_cache[0] < LIST_CACHE_TTL_S:
        return _list_cache[1]
    usage = await scan_usage()
    if cached:
        _list_cache = (time.monotonic(), usage)
    return usage


def _decode(raw: Any) -> dict[str, str] | None:
    """Los modelos que publicó un latido, o None si no los publica (``"1"`` de una
    versión anterior, JSON roto u otra versión)."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    try:
        data = json.loads(raw) if isinstance(raw, str) else None
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("v") != HEARTBEAT_VERSION:
        return None
    models = data.get("models")
    if not isinstance(models, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in models.items()
    ):
        return None
    return models


async def published_defaults(redis: Any) -> tuple[list[dict[str, str]], Problem | None]:
    """Lo que publica cada latido vivo, y el problema si no se puede verificar."""
    from nexus_worker.platform_models import WORKER_USES, default_models

    keys = [k async for k in redis.scan_iter(match=f"{HEARTBEAT_PREFIX}*", count=200)]
    if not keys:
        return [], "no_heartbeat"
    published: list[dict[str, str]] = []
    problem: Problem | None = None
    # Solo las claves que resuelve el worker (research D2): las de la API las
    # decide el entorno de la API.
    expected = {k: v for k, v in default_models().items() if k in WORKER_USES}
    for raw in await redis.mget(keys):
        if raw is None:
            continue  # caducó entre el SCAN y el MGET
        models = _decode(raw)
        if models is None:
            problem = problem or "unpublished"
            continue
        published.append(models)
        mine = {k: v for k, v in models.items() if k in WORKER_USES}
        if mine != expected and problem is None:
            problem = "mismatch"
    if not published and problem is None:
        problem = "no_heartbeat"
    return published, problem


async def uses_of(key: str, *, redis: Any, cached: bool = False) -> ModelUses:
    """Los usos de ``key``. Las guardas llaman sin caché (1.4); el listado, con."""
    return (await uses_of_many([key], redis=redis, cached=cached))[key]


async def uses_of_many(
    keys: list[str], *, redis: Any, cached: bool = False
) -> dict[str, ModelUses]:
    """Los usos de varios modelos con un solo barrido y una sola lectura del latido."""
    from nexus_worker.platform_models import default_models

    try:
        published, problem = await published_defaults(redis)
    except Exception as exc:
        log.warning("model_usage.heartbeat_unreadable", error=type(exc).__name__)
        published, problem = [], "no_heartbeat"
    sources = [default_models(), *published]
    usage = await _scan(cached=cached)
    out: dict[str, ModelUses] = {}
    for key in keys:
        defaults = sorted({use for models in sources for use, m in models.items() if m == key})
        found = usage.get(key, ClientUsage())
        out[key] = ModelUses(
            defaults=tuple(defaults),
            agents=found.agents,
            clients=found.clients,
            verified=problem is None,
            problem=problem,
        )
    return out


__all__ = [
    "HEARTBEAT_PREFIX",
    "HEARTBEAT_VERSION",
    "ClientUsage",
    "ModelUses",
    "invalidate",
    "published_defaults",
    "scan_usage",
    "uses_of",
    "uses_of_many",
]
