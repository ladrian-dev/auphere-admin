"""``/console/lite/agents`` y ``/console/lite/channels`` — los agentes del cliente
para su persona (spec 047, T167; requisitos 50.1, 50.2 y 27.6;
``contracts/lite-app-api.md`` §1). Solo módulo ``agents``.

- ``GET /agents``: cada agente con su ``visible_state`` —el mismo cálculo, los
  mismos códigos y tonos que la consola del partner (``client_overview``), que la
  lite no recalcula (25.5)—, sus números con el suyo y lo que la persona puede
  hacer (``allowed``);
- ``POST /agents/{agent_id}/pause`` · ``/resume``: pausar pide confirmación si hay
  conversaciones en curso y dice cuántas (27.8); la pausa del sistema (sin saldo,
  tope del agente) no la quita una persona (27.4);
- ``POST /channels/{channel_id}/pause`` · ``/resume``: solo ese número.

Cada cambio guarda quién y desde dónde (``lite_web`` o ``app``) en el agente o
el canal y en la auditoría, y avisa al partner (``agent.paused``,
``channel.resumed``…) cuando la transacción se confirma. Crear, archivar,
publicar o cambiar un agente no tiene ruta aquí (50.3).

Un agente o un número de otro cliente no existe para la RLS: ``404``, igual que
uno inventado.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from redis.asyncio import Redis

from nexus_api.api.deps import get_redis
from nexus_api.core.tenant_resolver import invalidate_tenant_cache
from nexus_api.db.models import Agent, Channel, ChannelStatus, NotificationKind, TenantStatus
from nexus_api.services import agent_states
from nexus_api.services import channel_config as channel_svc
from nexus_api.services.client_overview import read_client
from nexus_api.services.console_traffic import QA_PLAYGROUND_PROVIDER, customer_facing_channel

# El mismo estado visible que la consola del partner, con su misma forma
# (``VisibleOut``): la lite no lo recalcula ni lo pinta distinto (25.5).
from ..channel_config import VisibleOut, visible_of
from .deps import LiteScope, lite_scope

router = APIRouter()

AGENTS = lite_scope("agents")

Action = Literal["pause", "resume"]


class LiteAgentChannelOut(BaseModel):
    id: uuid.UUID
    type: str
    #: El número del negocio (nunca el de un cliente final).
    identifier: str
    visible_state: VisibleOut
    allowed: list[Action]


class LiteAgentCardOut(BaseModel):
    id: uuid.UUID
    name: str
    is_default: bool
    visible_state: VisibleOut
    pause_reason: str | None = None
    paused_by_kind: str | None = None
    paused_origin: str | None = None
    #: Quién y cuándo lo pausó (50.6): el nombre de la persona, o ``None`` si fue
    #: el sistema.
    paused_by_name: str | None = None
    paused_at: datetime | None = None
    open_conversations: int
    channels: list[LiteAgentChannelOut]
    allowed: list[Action]


class LiteAgentListOut(BaseModel):
    items: list[LiteAgentCardOut]


class LitePauseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Hay conversaciones en curso y la persona ya vio cuántas (27.8).
    confirm: bool = False


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown {what}")


def _live(agent: Agent) -> bool:
    return agent.status != "archived" and agent.lifecycle != "archived"


def _kind(channel: Channel) -> str:
    return channel.type.value if hasattr(channel.type, "value") else str(channel.type)


def _channel_allowed(channel: Channel, *, client_open: bool) -> list[Action]:
    if not client_open or channel.status is ChannelStatus.DISCONNECTED:
        return []
    return ["resume" if channel.status is ChannelStatus.PAUSED else "pause"]


def _channel_out(channel: Channel, *, client_open: bool) -> LiteAgentChannelOut:
    return LiteAgentChannelOut(
        id=channel.id,
        type=_kind(channel),
        identifier=channel.provider_identifier,
        visible_state=visible_of(channel),
        allowed=_channel_allowed(channel, client_open=client_open),
    )


def _agent_allowed(agent: Agent, *, client_open: bool) -> list[Action]:
    """Pausar lo que atiende; reanudar solo la pausa de una persona. La del
    sistema (sin saldo, tope) la deshace el sistema (27.4); la del cliente, el
    partner."""
    if not client_open or not _live(agent):
        return []
    if agent.lifecycle == "paused":
        return ["resume"] if agent.pause_reason == "manual" else []
    return ["pause"]


async def _agents(scope: LiteScope, only: uuid.UUID | None = None) -> list[LiteAgentCardOut]:
    session = scope.session
    tenant = scope.tenant
    detail = await read_client(session, tenant.id, tenant.status)
    visible = {a.agent_id: a.visible for a in detail.agents}
    agents = [
        a
        for a in (
            await session.scalars(
                sa.select(Agent)
                .where(Agent.tenant_id == tenant.id)
                .order_by(Agent.created_at, Agent.id)
                .execution_options(populate_existing=True)
            )
        ).all()
        if _live(a)
    ]
    channels = (
        await session.scalars(
            sa.select(Channel)
            .where(
                Channel.tenant_id == tenant.id,
                customer_facing_channel(),
                Channel.status != ChannelStatus.DISCONNECTED,
            )
            .order_by(Channel.created_at, Channel.id)
            .execution_options(populate_existing=True)
        )
    ).all()
    # Un número sin agente lo atiende el principal: el primero (como el estado
    # visible de ``read_client`` y la Bandeja).
    principal = agents[0].id if agents else None
    by_agent: dict[uuid.UUID | None, list[Channel]] = {}
    for channel in channels:
        by_agent.setdefault(channel.agent_id or principal, []).append(channel)
    client_open = tenant.status is TenantStatus.ACTIVE
    names = await _person_names(
        {a.paused_by_id for a in agents if a.paused_by_id and a.paused_by_kind != "system"}
    )
    out: list[LiteAgentCardOut] = []
    for agent in agents:
        if only is not None and agent.id != only:
            continue
        state = visible.get(agent.id)
        out.append(
            LiteAgentCardOut(
                id=agent.id,
                name=agent.name,
                is_default=agent.is_default,
                visible_state=(
                    VisibleOut(code=state.code, tone=state.tone, reason=state.reason)
                    if state is not None
                    else VisibleOut(code="draft", tone="muted")
                ),
                pause_reason=agent.pause_reason,
                paused_by_kind=agent.paused_by_kind,
                paused_origin=agent.paused_origin,
                paused_by_name=names.get(agent.paused_by_id or ""),
                paused_at=agent.paused_at,
                open_conversations=await agent_states.open_conversations(session, agent),
                channels=[
                    _channel_out(c, client_open=client_open) for c in by_agent.get(agent.id, [])
                ],
                allowed=_agent_allowed(agent, client_open=client_open),
            )
        )
    return out


async def _person_names(user_ids: set[str]) -> dict[str, str]:
    """El nombre de quien pausó: una persona del cliente o del partner. Las
    membresías son de plataforma: se leen en su propia sesión."""
    if not user_ids:
        return {}
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import ClientMembership, PartnerMembership

    out: dict[str, str] = {}
    async with get_sessionmaker()() as session, session.begin():
        for model in (ClientMembership, PartnerMembership):
            for user_id, name, email in (
                await session.execute(
                    sa.select(model.user_id, model.display_name, model.email).where(
                        model.user_id.in_(list(user_ids))
                    )
                )
            ).all():
                out.setdefault(str(user_id), str(name or email))
    return out


async def _agent(scope: LiteScope, agent_id: uuid.UUID) -> Agent:
    agent = await scope.session.get(Agent, agent_id)
    if agent is None or agent.tenant_id != scope.tenant.id or not _live(agent):
        raise _not_found("agent")
    return agent


async def _one(scope: LiteScope, agent_id: uuid.UUID) -> LiteAgentCardOut:
    (agent,) = await _agents(scope, only=agent_id)
    return agent


def _tell_partner(scope: LiteScope, kind: NotificationKind, data: dict[str, Any]) -> None:
    """``events.md`` §3: lo que hizo el cliente, a la campana del partner, solo si
    la transacción se confirma. Quién y desde dónde, nunca más."""
    tenant_id = scope.tenant.id
    payload = {**data, "by": scope.person_name, "origin": scope.origin}

    async def _announce() -> None:
        await channel_svc.announce(tenant_id=tenant_id, kind=kind.value, data=payload)

    scope.after_commit(_announce)


@router.get("/agents", response_model=LiteAgentListOut)
async def list_agents(scope: LiteScope = Depends(AGENTS)) -> LiteAgentListOut:
    return LiteAgentListOut(items=await _agents(scope))


@router.post(
    "/agents/{agent_id}/pause",
    response_model=LiteAgentCardOut,
    responses={409: {"description": "confirm_required | agent_archived"}},
)
async def pause_agent(
    agent_id: uuid.UUID,
    body: LitePauseIn | None = None,
    scope: LiteScope = Depends(AGENTS),
) -> LiteAgentCardOut:
    """Pausar (27.1): sus mensajes se siguen guardando y esperan a una persona con
    «Agente en pausa»; sus números no cambian (25.4)."""
    agent = await _agent(scope, agent_id)
    if not _agent_allowed(agent, client_open=scope.tenant.status is TenantStatus.ACTIVE):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "not_allowed"})
    if agent.lifecycle == "paused":
        return await _one(scope, agent.id)
    open_now = await agent_states.open_conversations(scope.session, agent)
    if open_now and not (body or LitePauseIn()).confirm:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "confirm_required", "open_conversations": open_now},
        )
    try:
        await agent_states.pause(
            scope.session,
            agent,
            reason="manual",
            by_kind="client_user",
            by_id=scope.principal.user_id,
            origin=scope.origin,
            actor=scope.principal.actor,
        )
    except agent_states.AgentStateError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code}) from None
    _tell_partner(
        scope,
        NotificationKind.AGENT_PAUSED,
        {"agent_id": str(agent.id), "agent": agent.name, "reason": "manual"},
    )
    return await _one(scope, agent.id)


@router.post(
    "/agents/{agent_id}/resume",
    response_model=LiteAgentCardOut,
    responses={409: {"description": "system_pause"}},
)
async def resume_agent(agent_id: uuid.UUID, scope: LiteScope = Depends(AGENTS)) -> LiteAgentCardOut:
    """Reanudar devuelve lo de antes (27.3). Solo la pausa de una persona."""
    agent = await _agent(scope, agent_id)
    if agent.lifecycle != "paused":
        return await _one(scope, agent.id)
    if agent.pause_reason != "manual" or scope.tenant.status is not TenantStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "system_pause", "pause_reason": agent.pause_reason},
        )
    try:
        await agent_states.resume(
            scope.session,
            agent,
            by_kind="client_user",
            by_id=scope.principal.user_id,
            origin=scope.origin,
            actor=scope.principal.actor,
        )
    except agent_states.AgentStateError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code}) from None
    _tell_partner(
        scope, NotificationKind.AGENT_RESUMED, {"agent_id": str(agent.id), "agent": agent.name}
    )
    return await _one(scope, agent.id)


async def _channel(scope: LiteScope, channel_id: uuid.UUID) -> Channel:
    channel = await scope.session.get(Channel, channel_id, populate_existing=True)
    if (
        channel is None
        or channel.tenant_id != scope.tenant.id
        or channel.provider == QA_PLAYGROUND_PROVIDER
    ):
        raise _not_found("channel")
    return channel


def _drop_cache_after_commit(scope: LiteScope, redis: Redis, channel: Channel) -> None:
    """La caché del número se tira tras el commit: antes, un turno a la vez podría
    volver a guardarla con el estado viejo y la pausa no llegaría hasta caducar."""
    provider, identifier = channel.provider, channel.provider_identifier

    async def _drop() -> None:
        await invalidate_tenant_cache(redis, provider, identifier)

    scope.after_commit(_drop)


def _channel_data(channel: Channel) -> dict[str, Any]:
    return {
        "channel_id": str(channel.id),
        "agent_id": str(channel.agent_id) if channel.agent_id else None,
    }


@router.post(
    "/channels/{channel_id}/pause",
    response_model=LiteAgentChannelOut,
    responses={409: {"description": "channel_disconnected"}},
)
async def pause_channel(
    channel_id: uuid.UUID,
    scope: LiteScope = Depends(AGENTS),
    redis: Redis = Depends(get_redis),
) -> LiteAgentChannelOut:
    """Pausar solo este número (27.1): lo que llega espera a una persona con
    «Canal en pausa»."""
    channel = await _channel(scope, channel_id)
    if scope.tenant.status is not TenantStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "not_allowed"})
    try:
        changed = await channel_svc.pause_channel(
            scope.session,
            channel,
            by_kind="client_user",
            by_id=scope.principal.user_id,
            origin=scope.origin,
            actor=scope.principal.actor,
        )
    except channel_svc.ChannelConfigError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code}) from None
    if changed:
        _drop_cache_after_commit(scope, redis, channel)
        _tell_partner(scope, NotificationKind.CHANNEL_PAUSED, _channel_data(channel))
    return _channel_out(channel, client_open=True)


@router.post("/channels/{channel_id}/resume", response_model=LiteAgentChannelOut)
async def resume_channel(
    channel_id: uuid.UUID,
    scope: LiteScope = Depends(AGENTS),
    redis: Redis = Depends(get_redis),
) -> LiteAgentChannelOut:
    """Reanudar el número devuelve el estado de antes de la pausa (27.3)."""
    channel = await _channel(scope, channel_id)
    if scope.tenant.status is not TenantStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "not_allowed"})
    if await channel_svc.resume_channel(
        scope.session, channel, origin=scope.origin, actor=scope.principal.actor
    ):
        _drop_cache_after_commit(scope, redis, channel)
        _tell_partner(scope, NotificationKind.CHANNEL_RESUMED, _channel_data(channel))
    return _channel_out(channel, client_open=True)


__all__ = ["router"]
