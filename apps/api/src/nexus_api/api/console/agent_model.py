"""``GET/PUT /console/clients/{ref}/agents/{agent_id}/model`` — spec 065 (contracts/api.md).

El modelo con el que responde un agente, lo que el partner puede elegir con su precio, y el
cambio. Es un ajuste vivo del agente: vale desde su siguiente turno, sin publicar versión ni
lanzar pruebas (requisitos 2.3 y 6.2). El agente se busca dentro del cliente de la ruta
(``agent_in_path``): uno de otro cliente, archivado o inexistente es el mismo 404.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis

from nexus_api.api.admin.agent_configs import PROMOTE_CHANNEL
from nexus_api.api.deps import get_redis
from nexus_api.core.partner_allowlist import read_allowlist
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.services.agent_model import (
    ModelUnavailableForAgent,
    UnknownModel,
    agent_model_view,
    set_agent_model,
)
from nexus_api.services.business.writes import after_commit

from .agent_draft_routes import agent_in_path
from .deps import ClientScope
from .schemas_models import AgentModelIn, AgentModelOut

router = APIRouter(prefix="/clients/{ref}/agents/{agent_id}")
log = structlog.get_logger(__name__)

_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "Unknown client reference or agent."}
}


async def _allowed(scope: ClientScope) -> frozenset[str]:
    await apply_partner_to_session(scope.session, scope.principal.partner.id)
    return await read_allowlist(scope.session, scope.principal.partner.id)


@router.get("/model", response_model=AgentModelOut, responses=_RESPONSES)
async def get_agent_model(
    scope: ClientScope = Depends(agent_in_path("agents:read")),
) -> AgentModelOut:
    """El modelo del agente, de dónde sale y lo que el partner puede elegir."""
    assert scope.agent_id is not None
    view = await agent_model_view(
        scope.session,
        agent_id=scope.agent_id,
        allowed=await _allowed(scope),
        can_change="agents:write" in scope.principal.permissions,
    )
    return AgentModelOut.model_validate(view)


@router.put(
    "/model",
    response_model=AgentModelOut,
    responses={
        **_RESPONSES,
        422: {"description": "unknown_model · model_unavailable_for_agent · extra keys."},
    },
)
async def put_agent_model(
    body: AgentModelIn,
    scope: ClientScope = Depends(agent_in_path("agents:write")),
    redis: Redis = Depends(get_redis),
) -> AgentModelOut:
    """Elige el modelo del agente (``null``: el modelo por defecto de Auphere)."""
    assert scope.agent_id is not None
    allowed = await _allowed(scope)
    try:
        await set_agent_model(
            scope.session,
            agent_id=scope.agent_id,
            model_id=body.model_id,
            set_by="partner",
            actor=scope.principal.actor,
            allowed=allowed,
            action="console.agent.model.update",
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
    message = f"{scope.tenant.id}:{scope.agent_id}"

    async def _invalidate() -> None:
        # Solo ese agente: el worker recarga su bundle en el siguiente turno.
        try:
            await redis.publish(PROMOTE_CHANNEL, message)
        except Exception as exc:
            log.warning("agent_model.invalidate_failed", agent=message, error=str(exc))

    after_commit(scope.session, _invalidate)
    view = await agent_model_view(
        scope.session, agent_id=scope.agent_id, allowed=allowed, can_change=True
    )
    return AgentModelOut.model_validate(view)
