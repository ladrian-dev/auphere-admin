"""El catálogo de despliegues en el panel de operador — spec 047, T150
(requisitos 41.1, 41.2, 41.7 a 41.9 y 54.1; ``contracts/admin-api.md`` §1).

Una fila de ``model_profiles`` es un despliegue (ADR-036). Desde aquí Auphere lo
da de alta (siempre en ``draft``), lo edita, le pone precios con su vigencia, lo
activa —por la puerta de ``router_catalog.activate_deployment``, que dice todo lo
que falta—, lo retira con su fecha o lo marca «No disponible». Sin tocar la base
a mano (historia 30).

Tres reglas:

- **Cada escritura lleva su persona y su motivo** (``X-Operator-Id``, ADR-034, y
  ``reason``) en la auditoría de plataforma.
- **Desde el siguiente turno**: tras escribir, este proceso olvida su catálogo
  (``router_catalog.catalog_changed``) y los workers lo oyen por el canal de
  promoción (``CATALOG_CHANGED``).
- **Una licencia excluida se rechaza en el alta** y la razón queda escrita
  (historia 24, escenario 3).

Es la única superficie que enseña costes (54.11): precios del proveedor tal cual.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.agent_configs import PROMOTE_CHANNEL
from nexus_api.api.admin.operator import operator_actor, require_operator
from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import OperatorAccount
from nexus_api.repositories import AuditRepository
from nexus_api.services import model_lifecycle
from nexus_api.services.router_catalog import (
    ACTIVATION_MESSAGES,
    CATALOG_CHANGED,
    ActivationRejected,
    Capabilities,
    CatalogSnapshot,
    Deployment,
    Price,
    activate_deployment,
    activation_problems,
    catalog_changed,
    license_excluded,
    load_snapshot,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/models", dependencies=[Depends(require_admin_token)])

_KEY_PATTERN = r"^[a-z0-9][a-z0-9._:/-]{2,120}$"


def _http(code: str, http_status: int, **extra: Any) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"code": code, **extra})


def default_respond_model() -> str | None:
    """El modelo de respuesta global del worker: los agentes de hoy sin modelo
    propio están fijados en él (``model_lifecycle``)."""
    return os.environ.get("NEXUS_LLM_RESPOND_MODEL") or None


async def publish_catalog_change(redis: Redis) -> None:
    """Desde el siguiente turno: este proceso y, por el canal de promoción, los
    workers. Si Redis falla, los demás lo ven en 5 minutos como mucho."""
    catalog_changed()
    try:
        await redis.publish(PROMOTE_CHANNEL, CATALOG_CHANGED)
    except Exception as exc:
        log.warning("admin.catalog_publish_failed", error=str(exc))


# ── formas ─────────────────────────────────────────────────────────────────


class RetentionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zero: bool = False
    how: str | None = Field(default=None, max_length=60)


class LicenseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    url: str | None = None
    read_at: datetime | None = None


class ContractIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dpa: bool = False
    subprocessor_listed: bool = False


class WeightsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    w_in: Decimal | None = None
    w_cache: Decimal | None = None
    w_out: Decimal | None = None


class DeploymentIn(BaseModel):
    """Un alta: la forma de ``router-and-catalog.md`` §2, sin estado (nace en
    ``draft``) y con el motivo."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_KEY_PATTERN)
    display_name: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=120)
    family: str | None = Field(default=None, max_length=40)
    provider: str = Field(min_length=1, max_length=60)
    route: str | None = None
    region: str | None = None
    residency: Literal["eu", "us", "global"] = "global"
    retention: RetentionIn = Field(default_factory=RetentionIn)
    license: LicenseIn | None = None
    contract: ContractIn = Field(default_factory=ContractIn)
    quota: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    meter_weights: WeightsIn = Field(default_factory=WeightsIn)
    reason: str = Field(min_length=1, max_length=500)


class DeploymentPatch(BaseModel):
    """Editar: lo que venga, y el motivo. El estado no se edita aquí: tiene sus
    rutas (activar, retirar, «No disponible»)."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    model: str | None = Field(default=None, min_length=1, max_length=120)
    family: str | None = Field(default=None, max_length=40)
    route: str | None = None
    region: str | None = None
    residency: Literal["eu", "us", "global"] | None = None
    retention: RetentionIn | None = None
    license: LicenseIn | None = None
    contract: ContractIn | None = None
    quota: dict[str, Any] | None = None
    capabilities: dict[str, Any] | None = None
    meter_weights: WeightsIn | None = None
    reason: str = Field(min_length=1, max_length=500)


class PriceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid_from: date
    input: Decimal | None = Field(default=None, ge=0)
    cache_read: Decimal | None = Field(default=None, ge=0)
    cache_write: Decimal | None = Field(default=None, ge=0)
    output: Decimal | None = Field(default=None, ge=0)
    audio_minute: Decimal | None = Field(default=None, ge=0)
    image: Decimal | None = Field(default=None, ge=0)
    long_context_surcharge: dict[str, Any] | None = None
    #: Un precio entra con su fuente (41.1).
    source: str = Field(min_length=8, max_length=500)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    unit: Literal["per_million_tokens"] = "per_million_tokens"


class ReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)


class RetireIn(ReasonIn):
    retire_after: datetime


class DeploymentRow(BaseModel):
    uuid: uuid.UUID
    display_name: str | None
    deployment: dict[str, Any]
    current_price: dict[str, Any] | None
    certified_tasks: list[str]
    activation_missing: list[str]
    activation_messages: dict[str, str]


class DeploymentList(BaseModel):
    items: list[DeploymentRow]
    statuses: list[str]


class PriceOut(BaseModel):
    alerts: int
    deployment: DeploymentRow


class ProposalOut(BaseModel):
    tenant_id: uuid.UUID
    agent_id: uuid.UUID
    client_ref: str | None
    agent: str
    proposed: str


class RetireOut(BaseModel):
    deployment: DeploymentRow
    proposals: list[ProposalOut]


# ── lectura ────────────────────────────────────────────────────────────────


def _row(deployment: Deployment, snapshot: CatalogSnapshot) -> DeploymentRow:
    certified = snapshot.certified_tasks(deployment.key)
    missing = activation_problems(deployment, class_certified_tasks=certified)
    price = deployment.current_price()
    assert deployment.id is not None
    return DeploymentRow(
        uuid=deployment.id,
        display_name=deployment.display_name,
        deployment=deployment.to_contract(),
        current_price=None if price is None else price.to_contract(),
        certified_tasks=sorted(certified),
        activation_missing=list(missing),
        activation_messages={m: ACTIVATION_MESSAGES[m] for m in missing},
    )


async def _snapshot(session: AsyncSession) -> CatalogSnapshot:
    async with session.begin():
        return await load_snapshot(session, refresh_hop=False)


def _by_uuid(snapshot: CatalogSnapshot, deployment_id: uuid.UUID) -> Deployment:
    for deployment in snapshot.deployments.values():
        if deployment.id == deployment_id:
            return deployment
    raise _http("unknown_deployment", status.HTTP_404_NOT_FOUND)


@router.get("/deployments", response_model=DeploymentList)
async def list_deployments(
    status_filter: str | None = Query(default=None, alias="status"),
    provider: str | None = None,
    task: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> DeploymentList:
    """Despliegues con capacidades, residencia, retención, licencia, contrato,
    estado, retirada, cuota, precios y certificaciones; y lo que les falta para
    activarse."""
    from nexus_api.db.models.router import DEPLOYMENT_STATUSES

    snapshot = await _snapshot(session)
    items = [
        _row(d, snapshot)
        for d in sorted(snapshot.deployments.values(), key=lambda d: (d.provider, d.key))
        if (status_filter is None or d.status == status_filter)
        and (provider is None or d.provider == provider)
        and (task is None or task in snapshot.certified_tasks(d.key))
    ]
    return DeploymentList(items=items, statuses=list(DEPLOYMENT_STATUSES))


# ── escritura ──────────────────────────────────────────────────────────────


def _capabilities(raw: dict[str, Any]) -> Capabilities:
    try:
        return Capabilities.from_json(raw)
    except (TypeError, ValueError) as exc:
        raise _http(
            "bad_capabilities", status.HTTP_422_UNPROCESSABLE_ENTITY, error=str(exc)
        ) from exc


def _check_retention(retention: RetentionIn) -> None:
    from nexus_worker.runtime.llm import RETENTION_WIRE

    if retention.zero and (retention.how is None or retention.how not in RETENTION_WIRE):
        raise _http(
            "unknown_retention",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            known=sorted(RETENTION_WIRE),
        )


def _check_weights(weights: WeightsIn) -> None:
    values = (weights.w_in, weights.w_cache, weights.w_out)
    if any(v is None for v in values) and any(v is not None for v in values):
        raise _http("partial_weights", status.HTTP_422_UNPROCESSABLE_ENTITY)


def _columns(
    *,
    model: str,
    display_name: str,
    family: str | None,
    route: str | None,
    region: str | None,
    residency: str,
    retention: RetentionIn,
    license_: LicenseIn | None,
    contract: ContractIn,
    quota: dict[str, Any],
    capabilities: dict[str, Any],
    weights: WeightsIn,
) -> dict[str, Any]:
    caps = _capabilities(capabilities)
    stored = {**capabilities, "model": model}
    return {
        "display_name": display_name,
        "family": family,
        "route": route,
        "region": region,
        "residency": residency,
        "zero_retention": retention.zero,
        "retention_how": retention.how if retention.zero else None,
        "license_id": license_.id if license_ else None,
        "license_url": license_.url if license_ else None,
        "license_read_at": license_.read_at if license_ else None,
        "contract_dpa": contract.dpa,
        "subprocessor_listed": contract.subprocessor_listed,
        "quota": json.dumps(quota, default=str),
        "capabilities": json.dumps(stored, default=str),
        "supports_tools": caps.tools,
        "supports_vision": caps.vision,
        "max_context": caps.context_window,
        "cache_min_tokens": caps.cache_min_tokens,
        "quota_weight_input": weights.w_in,
        "quota_weight_cache_read": weights.w_cache,
        "quota_weight_output": weights.w_out,
    }


_JSON_COLUMNS = frozenset({"quota", "capabilities"})


def _assign(columns: dict[str, Any]) -> str:
    return ", ".join(
        f"{c} = CAST(:{c} AS jsonb)" if c in _JSON_COLUMNS else f"{c} = :{c}" for c in columns
    )


async def _reload(session: AsyncSession, deployment_id: uuid.UUID) -> DeploymentRow:
    snapshot = await _snapshot(session)
    return _row(_by_uuid(snapshot, deployment_id), snapshot)


@router.post("/deployments", response_model=DeploymentRow, status_code=status.HTTP_201_CREATED)
async def create_deployment(
    body: DeploymentIn,
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
    redis: Redis = Depends(get_redis),
) -> DeploymentRow:
    """Alta en ``draft``. Una licencia excluida (Llama 4, Qwen3.8-Flash-Next,
    AGPL) se rechaza y la razón queda en la auditoría."""
    actor = operator_actor(operator)
    if body.license is not None and license_excluded(body.license.id):
        async with session.begin():
            await AuditRepository(session).record(
                actor=actor,
                action="deployment.rejected",
                target=f"deployment:{body.id}",
                after={
                    "id": body.id,
                    "code": "license_excluded",
                    "license": body.license.id,
                    "why": ACTIVATION_MESSAGES["license_excluded"],
                    "reason": body.reason,
                },
                platform=True,
            )
        raise _http(
            "license_excluded",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            message=ACTIVATION_MESSAGES["license_excluded"],
        )
    _check_retention(body.retention)
    _check_weights(body.meter_weights)
    columns = _columns(
        model=body.model,
        display_name=body.display_name,
        family=body.family,
        route=body.route,
        region=body.region,
        residency=body.residency,
        retention=body.retention,
        license_=body.license,
        contract=body.contract,
        quota=body.quota,
        capabilities=body.capabilities,
        weights=body.meter_weights,
    )
    names = ["provider", "model_id", "status", *columns]
    values = ", ".join(f"CAST(:{c} AS jsonb)" if c in _JSON_COLUMNS else f":{c}" for c in names)
    async with session.begin():
        exists = await session.scalar(
            sa.text("SELECT 1 FROM model_profiles WHERE model_id = :k"), {"k": body.id}
        )
        if exists:
            raise _http("deployment_exists", status.HTTP_409_CONFLICT)
        deployment_id = await session.scalar(
            sa.text(
                f"INSERT INTO model_profiles ({', '.join(names)}) VALUES ({values}) RETURNING id"
            ),
            {"provider": body.provider, "model_id": body.id, "status": "draft", **columns},
        )
        await AuditRepository(session).record(
            actor=actor,
            action="deployment.created",
            target=f"deployment:{body.id}",
            after={"id": body.id, "provider": body.provider, "reason": body.reason},
            platform=True,
        )
    await publish_catalog_change(redis)
    assert isinstance(deployment_id, uuid.UUID)
    return await _reload(session, deployment_id)


#: Lo que, si cambia, deja de describir lo que se certificó (requisito 42.2).
_CERTIFIED_SHAPE = ("model", "route", "region", "capabilities", "provider")


@router.patch("/deployments/{deployment_id}", response_model=DeploymentRow)
async def update_deployment(
    deployment_id: uuid.UUID,
    body: DeploymentPatch,
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
    redis: Redis = Depends(get_redis),
) -> DeploymentRow:
    """Editar. Las capacidades, la región, la ruta o el modelo caducan sus
    certificaciones por clase: ya no describen lo que se certificó (42.2). El
    precio no: tiene su propia ruta, con vigencia."""
    snapshot = await _snapshot(session)
    current = _by_uuid(snapshot, deployment_id)
    contract = current.to_contract()
    if body.license is not None and license_excluded(body.license.id):
        raise _http(
            "license_excluded",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            message=ACTIVATION_MESSAGES["license_excluded"],
        )
    retention = body.retention or RetentionIn(**contract["retention"])
    weights = body.meter_weights or WeightsIn(**contract["meter_weights"])
    _check_retention(retention)
    _check_weights(weights)
    lic = contract["license"]
    columns = _columns(
        model=body.model or current.model,
        display_name=body.display_name or current.display_name or current.key,
        family=body.family if body.family is not None else current.family,
        route=body.route if body.route is not None else current.route,
        region=body.region if body.region is not None else current.region,
        residency=body.residency or current.residency,
        retention=retention,
        license_=body.license or (LicenseIn(**lic) if lic else None),
        contract=body.contract or ContractIn(**contract["contract"]),
        quota=body.quota if body.quota is not None else dict(current.quota),
        capabilities=(
            body.capabilities if body.capabilities is not None else contract["capabilities"]
        ),
        weights=weights,
    )
    reshaped = [
        f
        for f in _CERTIFIED_SHAPE
        if getattr(body, f, None) is not None
        and (
            body.capabilities != contract["capabilities"]
            if f == "capabilities"
            else getattr(body, f) != getattr(current, f)
        )
    ]
    actor = operator_actor(operator)
    async with session.begin():
        await session.execute(
            sa.text(
                f"UPDATE model_profiles SET {_assign(columns)}, updated_at = now() WHERE id = :id"
            ),
            {**columns, "id": deployment_id},
        )
        expired = 0
        if reshaped:
            result = await session.execute(
                sa.text(
                    "UPDATE model_task_certifications SET invalidated_at = now() "
                    "WHERE deployment_id = :d AND invalidated_at IS NULL"
                ),
                {"d": deployment_id},
            )
            expired = int(getattr(result, "rowcount", 0) or 0)
        await AuditRepository(session).record(
            actor=actor,
            action="deployment.updated",
            target=f"deployment:{current.key}",
            before=contract,
            after={
                "changed": sorted(body.model_dump(exclude_unset=True, exclude={"reason"})),
                "expired_certifications": expired,
                "reason": body.reason,
            },
            platform=True,
        )
    await publish_catalog_change(redis)
    return await _reload(session, deployment_id)


@router.post("/deployments/{deployment_id}/activate", response_model=DeploymentRow)
async def activate(
    deployment_id: uuid.UUID,
    body: ReasonIn,
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
    redis: Redis = Depends(get_redis),
) -> DeploymentRow:
    """La puerta del requisito 41.2: si falta algo, ``422`` con todo lo que falta."""
    snapshot = await _snapshot(session)
    current = _by_uuid(snapshot, deployment_id)
    try:
        async with session.begin():
            await activate_deployment(session, current.key)
            await AuditRepository(session).record(
                actor=operator_actor(operator),
                action="deployment.activated",
                target=f"deployment:{current.key}",
                before={"status": current.status},
                after={"status": "active", "reason": body.reason},
                platform=True,
            )
    except ActivationRejected as exc:
        raise _http(
            "activation_rejected",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            missing=list(exc.missing),
            messages={m: ACTIVATION_MESSAGES[m] for m in exc.missing},
        ) from exc
    await publish_catalog_change(redis)
    return await _reload(session, deployment_id)


@router.post(
    "/deployments/{deployment_id}/prices",
    response_model=PriceOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_price(
    deployment_id: uuid.UUID,
    body: PriceIn,
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
    redis: Redis = Depends(get_redis),
) -> PriceOut:
    """Un precio nuevo con su vigencia y su fuente. Si sube más de un 10 % el
    precio estimado por mensaje de algún agente, su partner lo sabe ya (41.8)."""
    current = _by_uuid(await _snapshot(session), deployment_id)
    price = Price(
        valid_from=body.valid_from,
        input=body.input,
        cache_read=body.cache_read,
        cache_write=body.cache_write,
        output=body.output,
        audio_minute=body.audio_minute,
        image=body.image,
        surcharge=body.long_context_surcharge,
        source_url=body.source,
        currency=body.currency,
        unit=body.unit,
    )
    alerts = await model_lifecycle.add_price(
        current.key,
        price,
        actor=operator_actor(operator),
        default_respond=default_respond_model(),
    )
    await publish_catalog_change(redis)
    return PriceOut(alerts=len(alerts), deployment=await _reload(session, deployment_id))


@router.post("/deployments/{deployment_id}/retire", response_model=RetireOut)
async def retire(
    deployment_id: uuid.UUID,
    body: RetireIn,
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
    redis: Redis = Depends(get_redis),
) -> RetireOut:
    """La fecha de retirada: sigue atendiendo hasta entonces; los partners con
    agentes fijados reciben el aviso con el sustituto propuesto (41.7)."""
    current = _by_uuid(await _snapshot(session), deployment_id)
    try:
        proposals = await model_lifecycle.announce_retirement(
            current.key,
            retire_after=body.retire_after,
            actor=operator_actor(operator),
            reason=body.reason,
            default_respond=default_respond_model(),
        )
    except model_lifecycle.LifecycleError as exc:
        raise _http(exc.code, status.HTTP_422_UNPROCESSABLE_ENTITY, message=str(exc)) from exc
    await publish_catalog_change(redis)
    return RetireOut(
        deployment=await _reload(session, deployment_id),
        proposals=[
            ProposalOut(
                tenant_id=p.agent.tenant_id,
                agent_id=p.agent.agent_id,
                client_ref=p.agent.client_ref,
                agent=p.agent.agent_name,
                proposed=p.label,
            )
            for p in proposals
        ],
    )


@router.post("/deployments/{deployment_id}/unavailable", response_model=DeploymentRow)
async def unavailable(
    deployment_id: uuid.UUID,
    body: ReasonIn,
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
    redis: Redis = Depends(get_redis),
) -> DeploymentRow:
    """Deja de cumplir su contrato o su licencia: el router deja de usarlo desde
    el siguiente turno (41.9)."""
    current = _by_uuid(await _snapshot(session), deployment_id)
    await model_lifecycle.mark_unavailable(
        current.key, actor=operator_actor(operator), reason=body.reason
    )
    await publish_catalog_change(redis)
    return await _reload(session, deployment_id)


__all__ = ["default_respond_model", "publish_catalog_change", "router"]
