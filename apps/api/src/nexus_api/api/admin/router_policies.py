"""La política del router en el panel de operador — spec 047, T150 (requisitos
40.13, 54.2 y 54.9; ``contracts/admin-api.md`` §2).

- La taxonomía vigente (``router_taxonomy``).
- Los perfiles (``router_profiles``): cada cambio es **una versión nueva**, con
  quién y por qué, que se aplica desde el siguiente turno. Un perfil puede bajar
  los techos del requisito 40.10 (12 llamadas por turno, 3 escalados por hora),
  nunca subirlos.
- La vista previa: qué despliegue elegiría el router para una tarea de un agente
  dado, con los descartados y su motivo, **sin llamar a ningún modelo**. Es el
  mismo ``chain_for`` del turno (research D20).
- Las anomalías: decisiones con modelo de reserva o sin modelo, cliente a
  cliente con su GUC, y las conversaciones que esperan en la Bandeja por «Sin
  modelo disponible».

El módulo no se llama ``router.py``: el paquete ``api.admin`` ya tiene un
``router`` (el ``APIRouter`` de ``/admin``) y un submódulo con ese nombre lo
taparía.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.models_catalog import publish_catalog_change
from nexus_api.api.admin.operator import operator_actor, require_operator
from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core.security import require_admin_token
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import OperatorAccount
from nexus_api.db.models.router import ROUTER_PROFILES
from nexus_api.repositories import AuditRepository
from nexus_api.services.router_catalog import (
    MAX_CALLS_PER_TURN,
    MAX_ESCALATIONS_PER_HOUR,
    Deployment,
    ProfilePolicy,
    load_snapshot,
    model_policy_of,
)

router = APIRouter(prefix="/router", dependencies=[Depends(require_admin_token)])


def _http(code: str, http_status: int, **extra: Any) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"code": code, **extra})


class ProfileOut(BaseModel):
    profile: str
    version: int
    policy: dict[str, Any]
    published_by: str
    reason: str | None
    published_at: datetime


class ProfilesOut(BaseModel):
    items: list[ProfileOut]
    ceilings: dict[str, int]


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy: dict[str, Any]
    reason: str = Field(min_length=1, max_length=500)


class PreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: uuid.UUID
    agent_id: uuid.UUID | None = None
    task: str = Field(min_length=1, max_length=32)
    profile: str | None = None


class AnomalyOut(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    task: str
    kind: str
    decision_id: uuid.UUID | None
    created_at: datetime


class WaitingOut(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    conversations: int


class AnomaliesOut(BaseModel):
    items: list[AnomalyOut]
    waiting_no_model: list[WaitingOut]
    since: datetime


@router.get("/taxonomy")
async def get_taxonomy(session: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    async with session.begin():
        row = (
            await session.execute(
                sa.text("SELECT version, tasks FROM router_taxonomy ORDER BY version DESC LIMIT 1")
            )
        ).one_or_none()
    if row is None:
        raise _http("no_taxonomy", status.HTTP_404_NOT_FOUND)
    return {"version": int(row.version), "tasks": list(row.tasks)}


_PROFILE_COLUMNS = "profile, version, policy, published_by, reason, published_at"


@router.get("/profiles", response_model=ProfilesOut)
async def get_profiles(session: AsyncSession = Depends(get_db_session)) -> ProfilesOut:
    """La versión vigente de cada perfil y los techos que no se pueden subir."""
    async with session.begin():
        rows = (
            await session.execute(
                sa.text(
                    f"SELECT DISTINCT ON (profile) {_PROFILE_COLUMNS} FROM router_profiles "
                    "ORDER BY profile, version DESC"
                )
            )
        ).mappings()
        items = [ProfileOut(**dict(r)) for r in rows]
    return ProfilesOut(
        items=items,
        ceilings={
            "max_calls_per_turn": MAX_CALLS_PER_TURN,
            "max_escalations_per_hour": MAX_ESCALATIONS_PER_HOUR,
        },
    )


@router.get("/profiles/{profile}/versions", response_model=list[ProfileOut])
async def get_profile_versions(
    profile: str = Path(...), session: AsyncSession = Depends(get_db_session)
) -> list[ProfileOut]:
    """El historial de un perfil: quién cambió qué y por qué."""
    async with session.begin():
        rows = (
            await session.execute(
                sa.text(
                    f"SELECT {_PROFILE_COLUMNS} FROM router_profiles WHERE profile = :p "
                    "ORDER BY version DESC"
                ),
                {"p": profile},
            )
        ).mappings()
        return [ProfileOut(**dict(r)) for r in rows]


def _validate(profile: str, policy: dict[str, Any], *, tasks: set[str], keys: set[str]) -> None:
    for ceiling, limit in (
        ("max_calls_per_turn", MAX_CALLS_PER_TURN),
        ("max_escalations_per_hour", MAX_ESCALATIONS_PER_HOUR),
    ):
        value = policy.get(ceiling)
        if value is not None and (not isinstance(value, int) or value > limit or value < 0):
            raise _http("over_ceiling", status.HTTP_422_UNPROCESSABLE_ENTITY, field=ceiling)
    raw_tasks = policy.get("tasks")
    if not isinstance(raw_tasks, dict) or not raw_tasks:
        raise _http("no_tasks", status.HTTP_422_UNPROCESSABLE_ENTITY)
    unknown = sorted(set(raw_tasks) - tasks)
    if unknown:
        raise _http("unknown_task", status.HTTP_422_UNPROCESSABLE_ENTITY, tasks=unknown)
    reserves = sorted(
        str(t.get("reserve"))
        for t in raw_tasks.values()
        if isinstance(t, dict) and t.get("reserve") and t.get("reserve") not in keys
    )
    if reserves:
        raise _http("unknown_reserve", status.HTTP_422_UNPROCESSABLE_ENTITY, reserves=reserves)
    try:
        ProfilePolicy.from_row(profile, 1, policy)
    except (TypeError, ValueError, AttributeError) as exc:
        raise _http("bad_policy", status.HTTP_422_UNPROCESSABLE_ENTITY, error=str(exc)) from exc


@router.put("/profiles/{profile}", response_model=ProfileOut)
async def put_profile(
    body: ProfileIn,
    profile: str = Path(...),
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
    redis: Redis = Depends(get_redis),
) -> ProfileOut:
    """Una versión nueva del perfil, con su motivo. Se aplica desde el siguiente
    turno (40.13): ningún turno en curso cambia de política a mitad."""
    if profile not in ROUTER_PROFILES:
        raise _http("unknown_profile", status.HTTP_404_NOT_FOUND)
    actor = operator_actor(operator)
    async with session.begin():
        snapshot = await load_snapshot(session, refresh_hop=False)
        _validate(
            profile,
            body.policy,
            tasks=set(snapshot.taxonomy.codes),
            keys=set(snapshot.deployments),
        )
        before = await session.scalar(
            sa.text("SELECT max(version) FROM router_profiles WHERE profile = :p"), {"p": profile}
        )
        version = int(before or 0) + 1
        row = (
            (
                await session.execute(
                    sa.text(
                        "INSERT INTO router_profiles (profile, version, policy, published_by, reason) "
                        "VALUES (:p, :v, CAST(:policy AS jsonb), :by, :reason) "
                        f"RETURNING {_PROFILE_COLUMNS}"
                    ),
                    {
                        "p": profile,
                        "v": version,
                        "policy": json.dumps(body.policy),
                        "by": actor,
                        "reason": body.reason,
                    },
                )
            )
            .mappings()
            .one()
        )
        await AuditRepository(session).record(
            actor=actor,
            action="router.policy_changed",
            target=f"router_profile:{profile}",
            before={"version": before},
            after={"profile": profile, "version": version, "reason": body.reason},
            platform=True,
        )
    await publish_catalog_change(redis)
    return ProfileOut(**dict(row))


@router.post("/preview")
async def preview(
    body: PreviewIn, session: AsyncSession = Depends(get_db_session)
) -> dict[str, Any]:
    """Qué elegiría el router para esa tarea de ese agente, sin llamar a nadie:
    el mismo ``chain_for`` del turno, con los hechos del cliente leídos con su
    GUC. Enseña costes (solo aquí, 54.11)."""
    from nexus_worker.runtime.model_resolver import RouteContext, chain_for, load_route_facts

    from nexus_api.metering.wallet import partner_id_for_tenant

    async with session.begin():
        snapshot = await load_snapshot(session, refresh_hop=False)
        partner_id = await partner_id_for_tenant(session, body.tenant_id)
    if body.task not in snapshot.taxonomy.tasks:
        raise _http("unknown_task", status.HTTP_422_UNPROCESSABLE_ENTITY)
    policy = None
    agent_version: str | None = None
    if body.agent_id is not None:
        async with get_sessionmaker()() as scoped, tenant_scoped_session(scoped, body.tenant_id):
            row = (
                await scoped.execute(
                    sa.text(
                        "SELECT id, policies FROM agent_configs "
                        "WHERE agent_id = :a AND status = 'active'"
                    ),
                    {"a": body.agent_id},
                )
            ).one_or_none()
        if row is None:
            raise _http("unknown_agent", status.HTTP_404_NOT_FOUND)
        policy = model_policy_of(row.policies)
        agent_version = str(row.id)
    name = body.profile or (policy.profile if policy is not None else "auto")
    profile = snapshot.profile(name)
    if profile is None or profile.task(body.task) is None:
        raise _http("no_policy", status.HTTP_422_UNPROCESSABLE_ENTITY, profile=name)
    facts = await load_route_facts(body.tenant_id, body.agent_id, partner_id=partner_id)
    spec = snapshot.taxonomy.tasks[body.task]
    decision = chain_for(
        body.task,
        profile,
        RouteContext(
            tenant_id=body.tenant_id,
            catalog=snapshot,
            agent_id=body.agent_id,
            agent_version=agent_version,
            allowed=facts.partner_allowed if spec.conversation else None,
            eu_only=facts.eu_only,
            sovereign=facts.sovereign,
            agent_certified=facts.agent_certified,
            agent_pinned_deployment=(
                policy.deployment if policy is not None and policy.kind == "pinned" else None
            ),
        ),
    )
    return {
        "task": decision.task,
        "conversation": decision.conversation,
        "profile": decision.profile,
        "policy_version": decision.policy_version,
        "outcome": decision.outcome,
        "chain": [
            {
                "deployment": d.key,
                "provider": d.provider,
                "residency": d.residency,
                "price": _price(d),
            }
            for d in decision.chain
        ],
        "rejected": [r.as_log() for r in decision.rejected],
        "estimated_cost_micros": decision.estimated_cost_micros,
        "facts": {
            "eu_only": facts.eu_only,
            "sovereign": facts.sovereign,
            "partner_allowed": sorted(facts.partner_allowed or []),
            "agent_certified": sorted(facts.agent_certified),
            "degraded": facts.degraded,
        },
    }


def _price(deployment: Deployment) -> dict[str, Any] | None:
    price = deployment.current_price()
    return None if price is None else price.to_contract()


@router.get("/anomalies", response_model=AnomaliesOut)
async def anomalies(
    since: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> AnomaliesOut:
    """Modelos de reserva y ``no_model`` de todos los clientes, cada uno leído
    con su GUC, y quién espera en la Bandeja por «Sin modelo disponible». Los
    enfriamientos son de cada proceso del worker y van a su log
    (``llm.cooldown``)."""
    moment = since or datetime.now(UTC) - timedelta(days=7)
    async with session.begin():
        tenants = (
            await session.execute(
                sa.text("SELECT id, name FROM tenants WHERE status <> 'archived' ORDER BY name")
            )
        ).all()
    items: list[AnomalyOut] = []
    waiting: list[WaitingOut] = []
    sm = get_sessionmaker()
    for tenant_id, tenant_name in tenants:
        async with sm() as scoped, tenant_scoped_session(scoped, tenant_id):
            for task, kind, decision_id, created_at in (
                await scoped.execute(
                    sa.text(
                        "SELECT task, kind, decision_id, created_at FROM router_anomalies "
                        "WHERE created_at >= :since ORDER BY created_at DESC LIMIT 200"
                    ),
                    {"since": moment},
                )
            ).all():
                items.append(
                    AnomalyOut(
                        tenant_id=tenant_id,
                        tenant_name=str(tenant_name),
                        task=str(task),
                        kind=str(kind),
                        decision_id=decision_id,
                        created_at=created_at,
                    )
                )
            stuck = await scoped.scalar(
                sa.text(
                    "SELECT count(*) FROM conversations "
                    "WHERE waiting_reason = 'no_model' AND status = 'escalated'"
                )
            )
            if stuck:
                waiting.append(
                    WaitingOut(
                        tenant_id=tenant_id, tenant_name=str(tenant_name), conversations=int(stuck)
                    )
                )
    items.sort(key=lambda a: a.created_at, reverse=True)
    return AnomaliesOut(items=items, waiting_no_model=waiting, since=moment)


__all__ = ["router"]
