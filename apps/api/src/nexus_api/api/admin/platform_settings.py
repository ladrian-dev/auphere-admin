"""``GET/PUT /admin/platform/agent-respond-default`` — spec 065, requisito 13 (contracts/api.md).

El modelo con el que responden los agentes sin elección propia, en este entorno. Cambiarlo
mueve a muchos agentes de golpe, así que el ``PUT`` sin ``confirm`` no escribe: devuelve
``409 confirm_required`` con la lista de afectados. Con ``confirm`` escribe el ajuste, audita
con el motivo, invalida el catálogo y esos agentes, y les devuelve la pasada de pruebas. No
avisa a los partners (13.6).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.agent_configs import PROMOTE_CHANNEL
from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core import respond_catalog
from nexus_api.core.respond_profiles import profile_for
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import AuditLog, OperatorAccount
from nexus_api.db.models.model_profile import ModelProfile
from nexus_api.services.agent_respond_default import (
    following_default,
    read_setting,
    return_tests_pass,
    store_default,
)

from .operator import require_operator

router = APIRouter(prefix="/platform/agent-respond-default")
log = structlog.get_logger(__name__)


class DefaultOptionOut(BaseModel):
    model_id: str
    display_name: str


class AgentRespondDefaultOut(BaseModel):
    model_id: str
    display_name: str
    set_by: str | None = None
    set_at: datetime | None = None
    #: Los modelos habilitados para responder en este entorno.
    options: list[DefaultOptionOut]


class AgentRespondDefaultIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=500)
    confirm: bool = False

    @field_validator("reason")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reason is required")
        return value


async def _names(session: AsyncSession, model_ids: set[str]) -> dict[str, str]:
    rows = await session.execute(
        sa.select(ModelProfile.model_id, ModelProfile.display_name).where(
            ModelProfile.model_id.in_(model_ids)
        )
    )
    return {str(m): str(n) for m, n in rows}


async def _view(session: AsyncSession) -> AgentRespondDefaultOut:
    await respond_catalog.refresh_from_db(session)
    setting = await read_setting(session)
    model_id = setting["model_id"] if setting else respond_catalog.agent_respond_default()
    offered = [m for m, _ in respond_catalog.RESPOND_MODELS]
    names = await _names(session, {model_id, *offered})
    return AgentRespondDefaultOut(
        model_id=model_id,
        display_name=names.get(model_id, model_id),
        set_by=setting["set_by"] if setting else None,
        set_at=setting["set_at"] if setting else None,
        options=[DefaultOptionOut(model_id=m, display_name=names.get(m, m)) for m in offered],
    )


@router.get("", response_model=AgentRespondDefaultOut, dependencies=[Depends(require_admin_token)])
async def get_agent_respond_default(
    session: AsyncSession = Depends(get_db_session),
) -> AgentRespondDefaultOut:
    return await _view(session)


@router.put(
    "",
    response_model=AgentRespondDefaultOut,
    dependencies=[Depends(require_admin_token)],
    responses={
        409: {"description": "confirm_required, with the affected agents."},
        422: {"description": "unknown_model · reason missing."},
    },
)
async def put_agent_respond_default(
    body: AgentRespondDefaultIn,
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> AgentRespondDefaultOut:
    # Antes de cualquier rollback: el operador sale de esta misma sesión y caducaría.
    actor = f"operator:{operator.email}"
    await respond_catalog.refresh_from_db(session)
    offered = {m for m, _ in respond_catalog.RESPOND_MODELS}
    if body.model_id not in offered or profile_for(body.model_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "unknown_model", "model_id": body.model_id},
        )
    current = respond_catalog.agent_respond_default()
    await session.rollback()  # la lectura del catálogo no deja nada abierto
    affected = await following_default(current)
    if not body.confirm:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "confirm_required",
                "affected": [row.to_contract() for row in affected],
            },
        )
    before = await store_default(session, body.model_id, actor=actor)
    names = await _names(session, {body.model_id})
    after: dict[str, Any] = {
        "model_id": body.model_id,
        "model": names.get(body.model_id, body.model_id),
        "reason": body.reason,
        "agents": len(affected),
    }
    session.add(
        AuditLog(
            # De plataforma: no es de ningún cliente.
            tenant_id=None,
            actor=actor,
            action="admin.platform.agent_respond_default",
            target="platform:agent_respond_default",
            before_json={"model_id": before},
            after_json=after,
        )
    )
    await session.commit()
    await return_tests_pass(affected)

    from nexus_api.api.admin.models_catalog import publish_catalog_change

    await publish_catalog_change(redis)
    for row in affected:
        try:
            await redis.publish(PROMOTE_CHANNEL, f"{row.tenant_id}:{row.agent_id}")
        except Exception as exc:
            log.warning("agent_default.invalidate_failed", agent=str(row.agent_id), error=str(exc))
    log.info(
        "admin.platform.agent_respond_default",
        before=before,
        after=body.model_id,
        agents=len(affected),
    )
    return await _view(session)
