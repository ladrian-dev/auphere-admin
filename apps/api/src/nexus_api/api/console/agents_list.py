"""``/console/clients/{ref}/agents`` — los agentes de un cliente (spec 030, R14).

Un cliente puede tener varios agentes; cada número de WhatsApp contesta con
uno. Estas rutas los listan, crean (con un borrador v1 sembrado desde una
plantilla, como el primer agente de un cliente), renombran y archivan, y
asignan un número a un agente. Las reglas viven en ``services/agents.py``
para que el admin diga lo mismo; aquí solo se traducen a HTTP.

Las rutas que editan «el agente» (versiones, ajustes, herramientas,
habilidades, capacidades, plantilla) aceptan ``?agent=`` y, sin él, actúan
sobre el agente principal (``deps.agent_scope``).
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Any, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from nexus_api.services import agents as agent_service

from .deps import ClientScope, client_scope
from .schemas_onboarding import FromSeedIn
from .seed_templates import stage_from_seed

router = APIRouter(prefix="/clients/{ref}")

AgentId = Path(..., description="One of the client's agents")


class AgentChannelOut(BaseModel):
    id: uuid.UUID
    display: str


class AgentOut(BaseModel):
    id: uuid.UUID
    name: str
    status: Literal["active", "archived"]
    is_principal: bool
    channels: list[AgentChannelOut]
    active_version: int | None
    draft_version: int | None
    # Spec 047 (25, 26.1): the card — its stored life, the visible state the
    # whole console shows the same, whether it is the default agent, and the
    # tab the card opens (the builder for a draft, the channels when it waits
    # for one, the overview otherwise).
    lifecycle: str | None = None
    pause_reason: str | None = None
    is_default: bool = False
    visible_state: dict[str, Any] | None = None
    opens: Literal["builder", "channels", "overview"] | None = None
    #: Recepción (requisito 35): lo que dice la versión publicada del agente.
    is_reception: bool = False


def _opens(code: str | None) -> Literal["builder", "channels", "overview"]:
    if code == "draft":
        return "builder"
    if code == "ready_no_channel":
        return "channels"
    return "overview"


class AgentCreateIn(FromSeedIn):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)


class AgentPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=80)
    status: Literal["archived"] | None = None

    @model_validator(mode="after")
    def _one_change(self) -> AgentPatchIn:
        if (self.name is None) == (self.status is None):
            raise ValueError("send either a new name or status=archived")
        return self


class ChannelAgentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: uuid.UUID


class ChannelAgentOut(BaseModel):
    channel_id: uuid.UUID
    agent_id: uuid.UUID


def _http(exc: agent_service.AgentError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code})


async def _states(scope: ClientScope) -> dict[uuid.UUID, Any]:
    from nexus_api.db.models import Agent
    from nexus_api.services.client_overview import read_client

    detail = await read_client(scope.session, scope.tenant.id, scope.tenant.status)
    rows = (
        await scope.session.execute(
            sa.select(
                Agent.id, Agent.lifecycle, Agent.pause_reason, Agent.is_default, Agent.is_reception
            ).where(Agent.tenant_id == scope.tenant.id)
        )
    ).all()
    stored = {r[0]: r for r in rows}
    out: dict[uuid.UUID, Any] = {}
    for state in detail.agents:
        row = stored.get(state.agent_id)
        out[state.agent_id] = (state.visible, row)
    return out


def _card(view: Any, states: dict[uuid.UUID, Any]) -> AgentOut:
    visible, row = states.get(view.id, (None, None))
    return AgentOut(
        id=view.id,
        name=view.name,
        status=view.status,
        is_principal=view.is_principal,
        channels=[AgentChannelOut(id=cid, display=disp) for cid, disp in view.channels],
        active_version=view.active_version,
        draft_version=view.draft_version,
        lifecycle=row[1] if row else None,
        pause_reason=row[2] if row else None,
        is_default=bool(row[3]) if row else False,
        visible_state=(
            {"code": visible.code, "tone": visible.tone, "reason": visible.reason}
            if visible is not None
            else None
        ),
        opens=_opens(visible.code if visible is not None else None),
        is_reception=bool(row[4]) if row else False,
    )


async def _out(scope: ClientScope, agent_id: uuid.UUID) -> AgentOut:
    views = await agent_service.list_agents(scope.session, include_archived=True)
    view = next(v for v in views if v.id == agent_id)
    return _card(view, await _states(scope))


@router.get("/agents", response_model=list[AgentOut])
async def list_agents(
    include_archived: bool = False,
    scope: ClientScope = Depends(client_scope("agents:read")),
) -> list[AgentOut]:
    """Spec 047 (28.2): ``?include_archived=true`` adds the archived agents, so
    the tab can show them («Archivado») and restore them."""
    views = await agent_service.list_agents(scope.session, include_archived=include_archived)
    states = await _states(scope)
    return [_card(v, states) for v in views]


@router.post(
    "/agents",
    response_model=AgentOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "name_taken"}, 404: {"description": "Unknown seed template."}},
)
async def create_agent(
    body: AgentCreateIn, scope: ClientScope = Depends(client_scope("agents:write"))
) -> AgentOut:
    """A new agent with its draft v1 sown from a template — it answers on no
    number until it is published and a number is assigned to it."""
    try:
        agent = await agent_service.create_agent(
            scope.session, scope.tenant.id, name=body.name, actor=scope.principal.actor
        )
    except agent_service.AgentError as exc:
        raise _http(exc) from None
    await stage_from_seed(
        scope.session,
        replace(scope, agent_id=agent.id),
        seed_template=body.seed_template,
        placeholders=body.placeholders,
    )
    return await _out(scope, agent.id)


@router.patch(
    "/agents/{agent_id}",
    response_model=AgentOut,
    responses={
        404: {"description": "Unknown agent."},
        409: {"description": "name_taken · agent_has_channels · last_agent"},
    },
)
async def update_agent(
    body: AgentPatchIn,
    agent_id: uuid.UUID = AgentId,
    scope: ClientScope = Depends(client_scope("agents:write")),
) -> AgentOut:
    try:
        if body.name is not None:
            await agent_service.rename_agent(
                scope.session, agent_id, name=body.name, actor=scope.principal.actor
            )
        else:
            await agent_service.archive_agent(scope.session, agent_id, actor=scope.principal.actor)
    except agent_service.AgentError as exc:
        raise _http(exc) from None
    return await _out(scope, agent_id)


@router.patch(
    "/channels/{channel_id}/agent",
    response_model=ChannelAgentOut,
    responses={
        404: {"description": "Unknown channel or agent."},
        409: {"description": "channel_send_only · agent_not_published · agent_archived"},
    },
)
async def assign_channel_agent(
    body: ChannelAgentIn,
    channel_id: uuid.UUID = Path(...),
    scope: ClientScope = Depends(client_scope("channels:write")),
) -> ChannelAgentOut:
    """Which agent answers on this number from its next message on."""
    try:
        channel = await agent_service.assign_channel(
            scope.session, channel_id, body.agent_id, actor=scope.principal.actor
        )
    except agent_service.AgentError as exc:
        raise _http(exc) from None
    assert channel.agent_id is not None
    return ChannelAgentOut(channel_id=channel.id, agent_id=channel.agent_id)


__all__ = ["router"]
