"""El modelo de cada agente desde el panel de operador — spec 065 (contracts/api.md).

- ``GET /admin/tenants/{tenant_id}/agents/models``: cada agente activo del cliente con su
  elección y con qué responde.
- ``PUT /admin/tenants/{tenant_id}/agents/{agent_id}/model``: Auphere elige el modelo de un
  agente entre los habilitados para responder en el entorno, esté o no en la lista del
  partner (requisito 7.2), con motivo. Escribe ``set_by = 'operator'``, audita
  ``admin.agent.model.update`` e invalida ese agente.

La sesión es la del cliente de la ruta (``scoped_session_from_path``): un agente de otro
cliente no se ve y es el mismo 404 que uno que no existe.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.agent_configs import PROMOTE_CHANNEL
from nexus_api.api.console.schemas_models import (
    AgentModelChoiceOut,
    AgentModelOut,
)
from nexus_api.api.deps import get_redis, scoped_session_from_path
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import Agent, OperatorAccount
from nexus_api.services.agent_model import (
    ModelUnavailableForAgent,
    UnknownModel,
    agent_model_rows,
    agent_model_view,
    set_agent_model,
)
from nexus_api.services.business.writes import after_commit

from .operator import require_operator

router = APIRouter()
log = structlog.get_logger(__name__)


class AdminAgentModelEffectiveOut(BaseModel):
    model_id: str
    display_name: str
    #: ``agent`` · ``agent_operator`` · ``version`` · ``platform``.
    source: str


class AdminAgentModelRowOut(BaseModel):
    agent_id: uuid.UUID
    name: str
    lifecycle: str
    choice: AgentModelChoiceOut | None
    effective: AdminAgentModelEffectiveOut


class AdminAgentModelIn(BaseModel):
    """El modelo (``null``: el modelo por defecto de Auphere) y por qué. El cliente y el
    agente salen de la ruta."""

    model_config = ConfigDict(extra="forbid")

    model_id: str | None = Field(default=None, min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reason is required")
        return value


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")


@router.get(
    "/tenants/{tenant_id}/agents/models",
    response_model=list[AdminAgentModelRowOut],
    dependencies=[Depends(require_admin_token)],
)
async def list_agent_models(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
) -> list[AdminAgentModelRowOut]:
    rows = await agent_model_rows(session)
    return [AdminAgentModelRowOut.model_validate(r) for r in rows]


@router.put(
    "/tenants/{tenant_id}/agents/{agent_id}/model",
    response_model=AgentModelOut,
    dependencies=[Depends(require_admin_token)],
    responses={
        404: {"description": "Unknown agent for this client."},
        422: {"description": "unknown_model · model_unavailable_for_agent · reason missing."},
    },
)
async def put_agent_model(
    tenant_id: uuid.UUID,
    body: AdminAgentModelIn,
    agent_id: uuid.UUID = Path(...),
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(scoped_session_from_path),
    redis: Redis = Depends(get_redis),
) -> AgentModelOut:
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.status != "active":
        raise _not_found()
    try:
        await set_agent_model(
            session,
            agent_id=agent_id,
            model_id=body.model_id,
            set_by="operator",
            actor=f"operator:{operator.email}",
            allowed=None,
            action="admin.agent.model.update",
            reason=body.reason,
        )
    except UnknownModel as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "unknown_model", "model_id": exc.model_id},
        ) from None
    except ModelUnavailableForAgent:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "model_unavailable_for_agent"},
        ) from None
    # El cliente de la fila del agente, leída bajo la RLS de la sesión de la ruta.
    message = f"{agent.tenant_id}:{agent_id}"

    async def _invalidate() -> None:
        try:
            await redis.publish(PROMOTE_CHANNEL, message)
        except Exception as exc:
            log.warning("agent_model.invalidate_failed", agent=message, error=str(exc))

    after_commit(session, _invalidate)
    view: dict[str, Any] = await agent_model_view(
        session, agent_id=agent_id, allowed=None, can_change=True
    )
    return AgentModelOut.model_validate(view)
