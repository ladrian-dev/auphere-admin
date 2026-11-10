"""La vida de un agente en la consola — spec 047, T123 (requisitos 25 a 28;
``contracts/console-api.md`` §4).

- ``GET /clients/{ref}/agents/{agent_id}``: la cabecera — vida, estado visible
  con su motivo, si es el agente por defecto, las conversaciones en curso y lo
  que la persona puede hacer (25);
- ``POST …/pause`` · ``…/resume`` [``agents:write``]: pausar pide confirmación
  si hay conversaciones en curso y dice cuántas (27.8);
- ``POST …/archive`` ``{channels: [{channel_id, to}]}``: el destino de cada
  número, otro agente o ``"pause"`` (28.1); el agente por defecto pide elegir
  otro antes (28.4);
- ``POST …/restore``: vuelve en pausa (28.2);
- ``PUT /clients/{ref}/default-agent`` ``{agent_id}``: atómico (26.2).

Un agente archivado sigue alcanzable aquí (para restaurarlo); el de otro cliente
es un 404 opaco (garantía 9).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field

from nexus_api.db.models import Agent
from nexus_api.services import agent_states
from nexus_api.services.client_overview import read_client
from nexus_api.services.wallet.bags import currency_of

from .deps import ClientScope, client_scope

router = APIRouter(prefix="/clients/{ref}")

Action = Literal["rename", "pause", "resume", "archive", "restore", "make_default"]


def any_agent(*required: str) -> Callable[..., Awaitable[ClientScope]]:
    """Como ``agent_in_path``, pero también un agente archivado del cliente."""
    client_dep = client_scope(*required)

    async def _dependency(
        agent_id: uuid.UUID = Path(...),
        scope: ClientScope = Depends(client_dep),
    ) -> ClientScope:
        found = await scope.session.get(Agent, agent_id)
        if found is None or found.tenant_id != scope.tenant.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent")
        return replace(scope, agent_id=agent_id)

    return _dependency


class VisibleOut(BaseModel):
    code: str
    tone: str
    reason: str | None = None


class AgentHeaderOut(BaseModel):
    id: uuid.UUID
    name: str
    lifecycle: str
    pause_reason: str | None
    visible_state: VisibleOut
    is_default: bool
    open_conversations: int
    paused_by_kind: str | None = None
    paused_origin: str | None = None
    allowed: list[Action] = Field(default_factory=list)
    #: Spec 047 (44.1): el tope mensual del agente y lo gastado este mes, en
    #: cien milésimas de la moneda de la bolsa (``cap_currency``).
    monthly_cap_micros: int | None = None
    month_spent_micros: int = 0
    cap_currency: str = "USD"
    #: Recepción (requisito 35): lo que dice la versión publicada.
    is_reception: bool = False


class PauseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: bool = False
    note: str | None = Field(default=None, max_length=300)


class ChannelDestinationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel_id: uuid.UUID
    to: uuid.UUID | Literal["pause"]


class ArchiveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channels: list[ChannelDestinationIn] = Field(default_factory=list, max_length=50)


class DefaultIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: uuid.UUID


def _error(exc: agent_states.AgentStateError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code})


async def header(scope: ClientScope) -> AgentHeaderOut:
    assert scope.agent_id is not None
    agent = await scope.session.get(Agent, scope.agent_id, populate_existing=True)
    assert agent is not None
    detail = await read_client(scope.session, scope.tenant.id, scope.tenant.status)
    state = next((a for a in detail.agents if a.agent_id == agent.id), None)
    visible = (
        VisibleOut(code=state.visible.code, tone=state.visible.tone, reason=state.visible.reason)
        if state is not None
        else VisibleOut(code="draft", tone="muted")
    )
    allowed: list[Action] = []
    if "agents:write" in scope.principal.permissions:
        if agent.lifecycle == "archived":
            allowed = ["restore"]
        else:
            allowed = ["rename", "archive"]
            allowed.append("resume" if agent.lifecycle == "paused" else "pause")
            if not agent.is_default:
                allowed.append("make_default")
    return AgentHeaderOut(
        id=agent.id,
        name=agent.name,
        lifecycle=agent.lifecycle,
        pause_reason=agent.pause_reason,
        visible_state=visible,
        is_default=agent.is_default,
        open_conversations=await agent_states.open_conversations(scope.session, agent),
        paused_by_kind=agent.paused_by_kind,
        paused_origin=agent.paused_origin,
        allowed=allowed,
        monthly_cap_micros=agent.monthly_cap_micros,
        month_spent_micros=await _month_spent(scope, agent.id),
        cap_currency=await currency_of(scope.principal.partner.id, scope.tenant.id),
        is_reception=agent.is_reception,
    )


async def _month_spent(scope: ClientScope, agent_id: uuid.UUID) -> int:
    from nexus_api.db.models import AgentMonthlySpend
    from nexus_api.services.wallet.bags import month_of

    row = await scope.session.get(AgentMonthlySpend, (scope.tenant.id, agent_id, month_of()))
    return int(row.spent_micros) if row is not None else 0


@router.get("/agents/{agent_id}", response_model=AgentHeaderOut)
async def get_agent(scope: ClientScope = Depends(any_agent("agents:read"))) -> AgentHeaderOut:
    return await header(scope)


async def _agent(scope: ClientScope) -> Agent:
    agent = await scope.session.get(Agent, scope.agent_id)
    assert agent is not None
    return agent


@router.post("/agents/{agent_id}/pause", response_model=AgentHeaderOut)
async def pause_agent(
    body: PauseIn | None = None, scope: ClientScope = Depends(any_agent("agents:write"))
) -> AgentHeaderOut:
    agent = await _agent(scope)
    payload = body or PauseIn()
    open_now = await agent_states.open_conversations(scope.session, agent)
    if open_now and not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "confirm_required", "open_conversations": open_now},
        )
    try:
        await agent_states.pause(
            scope.session,
            agent,
            reason="manual",
            by_kind="partner_member",
            by_id=scope.principal.user_id,
            origin="console",
            actor=scope.principal.actor,
            note=payload.note,
        )
    except agent_states.AgentStateError as exc:
        raise _error(exc) from None
    _tell_client(scope, "agent.paused", agent.id)
    return await header(scope)


def _tell_client(scope: ClientScope, kind: str, agent_id: uuid.UUID) -> None:
    """Lo que hace el partner, a las personas del cliente (events.md §3: el
    partner se entera cuando lo hace el cliente, y al revés). Tras el commit."""
    from nexus_api.services.business.writes import after_commit
    from nexus_api.services.channel_config import announce

    tenant_id, by = scope.tenant.id, scope.principal.actor

    async def _send() -> None:
        await announce(
            tenant_id=tenant_id,
            kind=kind,
            data={"agent_id": str(agent_id), "by": by, "origin": "console"},
            to_client=True,
            to_partner=False,
        )

    after_commit(scope.session, _send)


@router.post("/agents/{agent_id}/resume", response_model=AgentHeaderOut)
async def resume_agent(scope: ClientScope = Depends(any_agent("agents:write"))) -> AgentHeaderOut:
    try:
        await agent_states.resume(
            scope.session,
            await _agent(scope),
            by_kind="partner_member",
            by_id=scope.principal.user_id,
            origin="console",
            actor=scope.principal.actor,
        )
    except agent_states.AgentStateError as exc:
        raise _error(exc) from None
    assert scope.agent_id is not None
    _tell_client(scope, "agent.resumed", scope.agent_id)
    return await header(scope)


@router.post("/agents/{agent_id}/archive", response_model=AgentHeaderOut)
async def archive_agent(
    body: ArchiveIn, scope: ClientScope = Depends(any_agent("agents:write"))
) -> AgentHeaderOut:
    destinations: dict[uuid.UUID, Any] = {c.channel_id: c.to for c in body.channels}
    try:
        await agent_states.archive(
            scope.session, await _agent(scope), channels=destinations, actor=scope.principal.actor
        )
    except agent_states.AgentStateError as exc:
        raise _error(exc) from None
    return await header(scope)


@router.post("/agents/{agent_id}/restore", response_model=AgentHeaderOut)
async def restore_agent(scope: ClientScope = Depends(any_agent("agents:write"))) -> AgentHeaderOut:
    try:
        await agent_states.restore(scope.session, await _agent(scope), actor=scope.principal.actor)
    except agent_states.AgentStateError as exc:
        raise _error(exc) from None
    return await header(scope)


@router.put("/default-agent", response_model=AgentHeaderOut)
async def set_default_agent(
    body: DefaultIn, scope: ClientScope = Depends(client_scope("agents:write"))
) -> AgentHeaderOut:
    agent = await scope.session.get(Agent, body.agent_id)
    if agent is None or agent.tenant_id != scope.tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent")
    try:
        await agent_states.set_default(scope.session, agent, actor=scope.principal.actor)
    except agent_states.AgentStateError as exc:
        raise _error(exc) from None
    return await header(replace(scope, agent_id=agent.id))


__all__ = ["any_agent", "header", "router"]
