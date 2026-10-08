"""``/admin/tenants/{tenant_id}/agents`` — los agentes de un cliente desde el
panel de Auphere (spec 030, iteración 3, R14).

Mismas reglas que la consola del partner (``services/agents.py``). La sesión
es la **del tenant** de la ruta (``scoped_session_from_path``): el servicio de
agentes se apoya en la RLS para saber de quién es cada agente, así que una
sesión de plataforma vería los de todos los clientes.

Las rutas de versiones (``…/agent-config…``) aceptan ``?agent_id=``; sin él,
actúan sobre el agente principal.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import scoped_session_from_path
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import OperatorAccount
from nexus_api.services import agents as agent_service

from .client_access import require_operator

router = APIRouter()


class AdminAgentChannelOut(BaseModel):
    id: uuid.UUID
    display: str


class AdminAgentOut(BaseModel):
    id: uuid.UUID
    name: str
    status: Literal["active", "archived"]
    is_principal: bool
    channels: list[AdminAgentChannelOut]
    active_version: int | None
    draft_version: int | None


class AdminAgentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)


class AdminAgentPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=80)
    status: Literal["archived"] | None = None

    @model_validator(mode="after")
    def _one_change(self) -> AdminAgentPatchIn:
        if (self.name is None) == (self.status is None):
            raise ValueError("send either a new name or status=archived")
        return self


class AdminChannelAgentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: uuid.UUID


def _actor(operator: OperatorAccount) -> str:
    return f"operator:{operator.email}"


def _http(exc: agent_service.AgentError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code})


async def _views(session: AsyncSession, *, include_archived: bool) -> list[AdminAgentOut]:
    return [
        AdminAgentOut(
            id=v.id,
            name=v.name,
            status=v.status,  # type: ignore[arg-type]
            is_principal=v.is_principal,
            channels=[AdminAgentChannelOut(id=cid, display=d) for cid, d in v.channels],
            active_version=v.active_version,
            draft_version=v.draft_version,
        )
        for v in await agent_service.list_agents(session, include_archived=include_archived)
    ]


async def _one(session: AsyncSession, agent_id: uuid.UUID) -> AdminAgentOut:
    return next(v for v in await _views(session, include_archived=True) if v.id == agent_id)


@router.get(
    "/tenants/{tenant_id}/agents",
    response_model=list[AdminAgentOut],
    dependencies=[Depends(require_admin_token)],
)
async def list_agents(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
) -> list[AdminAgentOut]:
    return await _views(session, include_archived=False)


@router.post(
    "/tenants/{tenant_id}/agents",
    response_model=AdminAgentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_token)],
)
async def create_agent(
    tenant_id: uuid.UUID,
    body: AdminAgentIn,
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(scoped_session_from_path),
) -> AdminAgentOut:
    """An agent without versions; its first version is staged with
    ``PUT …/agent-config?agent_id=`` (or from the partner console)."""
    try:
        agent = await agent_service.create_agent(
            session, tenant_id, name=body.name, actor=_actor(operator)
        )
    except agent_service.AgentError as exc:
        raise _http(exc) from None
    return await _one(session, agent.id)


@router.patch(
    "/tenants/{tenant_id}/agents/{agent_id}",
    response_model=AdminAgentOut,
    dependencies=[Depends(require_admin_token)],
)
async def update_agent(
    tenant_id: uuid.UUID,
    body: AdminAgentPatchIn,
    agent_id: uuid.UUID = Path(...),
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(scoped_session_from_path),
) -> AdminAgentOut:
    try:
        if body.name is not None:
            await agent_service.rename_agent(
                session, agent_id, name=body.name, actor=_actor(operator)
            )
        else:
            await agent_service.archive_agent(session, agent_id, actor=_actor(operator))
    except agent_service.AgentError as exc:
        raise _http(exc) from None
    return await _one(session, agent_id)


@router.patch(
    "/tenants/{tenant_id}/channels/{channel_id}/agent",
    dependencies=[Depends(require_admin_token)],
)
async def assign_channel_agent(
    tenant_id: uuid.UUID,
    body: AdminChannelAgentIn,
    channel_id: uuid.UUID = Path(...),
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(scoped_session_from_path),
) -> dict[str, str]:
    try:
        channel = await agent_service.assign_channel(
            session, channel_id, body.agent_id, actor=_actor(operator)
        )
    except agent_service.AgentError as exc:
        raise _http(exc) from None
    return {"channel_id": str(channel.id), "agent_id": str(channel.agent_id)}


__all__ = ["router"]
