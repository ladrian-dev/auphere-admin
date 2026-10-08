"""Los agentes de un cliente — spec 030, iteración 3 (R14).

Un cliente puede tener varios agentes; cada número de WhatsApp contesta con
uno (``channels.agent_id``) y cada agente tiene sus versiones. El **agente
principal** es el activo más antiguo: contesta en los números sin agente y es
sobre el que actúa todo lo que no nombra uno (el Companion, el admin, los
crones).

Todas las funciones corren en la sesión del cliente (RLS): ningún id de otro
cliente existe aquí. Ninguna hace commit. Las reglas viven aquí para que la
consola del partner y el admin digan lo mismo:

* el nombre es único entre los activos del cliente (``name_taken``);
* archivar no deja a un número sin quien conteste (``agent_has_channels``) ni
  al cliente sin agentes (``last_agent``) — borrar no existe (§IV);
* un número solo de envío no tiene agente (``channel_send_only``), y un número
  solo se da a un agente con una versión publicada (``agent_not_published``):
  un borrador no contesta, y el despachador se quedaría sin a quién llamar.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    AgentStatus,
    AuditLog,
    Channel,
)
from nexus_api.services.channel_routing import config_agent_enabled


class AgentError(Exception):
    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


async def principal_agent_id(session: AsyncSession) -> uuid.UUID | None:
    """El activo más antiguo del cliente de la sesión."""
    found: uuid.UUID | None = await session.scalar(
        sa.select(Agent.id)
        .where(Agent.status == AgentStatus.ACTIVE.value)
        .order_by(Agent.created_at, Agent.id)
        .limit(1)
    )
    return found


async def agent_for_channel(
    session: AsyncSession, channel_id: uuid.UUID | None
) -> uuid.UUID | None:
    """Quién contesta en ese número: su agente o, sin uno, el principal."""
    if channel_id is not None:
        assigned = await session.scalar(sa.select(Channel.agent_id).where(Channel.id == channel_id))
        if assigned is not None:
            return assigned
    return await principal_agent_id(session)


@dataclass
class AgentView:
    id: uuid.UUID
    name: str
    status: str
    is_principal: bool
    created_at: datetime
    channels: list[tuple[uuid.UUID, str]] = field(default_factory=list)
    active_version: int | None = None
    draft_version: int | None = None


async def list_agents(session: AsyncSession, *, include_archived: bool = False) -> list[AgentView]:
    stmt = sa.select(Agent).order_by(Agent.created_at, Agent.id)
    if not include_archived:
        stmt = stmt.where(Agent.status == AgentStatus.ACTIVE.value)
    agents = list((await session.execute(stmt)).scalars())
    principal = await principal_agent_id(session)
    if not agents:
        return []
    ids = [a.id for a in agents]
    channels: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = {}
    for cid, agent_id, ident in (
        await session.execute(
            sa.select(Channel.id, Channel.agent_id, Channel.provider_identifier)
            .where(Channel.agent_id.in_(ids))
            .order_by(Channel.created_at)
        )
    ).all():
        channels.setdefault(agent_id, []).append((cid, str(ident)))
    versions: dict[uuid.UUID, dict[str, int]] = {}
    for agent_id, version, status in (
        await session.execute(
            sa.select(AgentConfig.agent_id, AgentConfig.version, AgentConfig.status).where(
                AgentConfig.agent_id.in_(ids),
                AgentConfig.status.in_([AgentConfigStatus.ACTIVE, AgentConfigStatus.STAGED]),
            )
        )
    ).all():
        slot = versions.setdefault(agent_id, {})
        key = "active" if status == AgentConfigStatus.ACTIVE else "draft"
        slot[key] = max(slot.get(key, 0), int(version))
    out: list[AgentView] = []
    for a in agents:
        v = versions.get(a.id, {})
        active = v.get("active")
        draft = v.get("draft")
        out.append(
            AgentView(
                id=a.id,
                name=a.name,
                status=a.status,
                is_principal=a.id == principal,
                created_at=a.created_at,
                channels=channels.get(a.id, []),
                active_version=active,
                # A draft counts only if it is newer than what is live.
                draft_version=draft
                if draft is not None and (active is None or draft > active)
                else None,
            )
        )
    return out


def _audit(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor: str,
    action: str,
    target: str,
    after: dict[str, object],
) -> None:
    session.add(
        AuditLog(tenant_id=tenant_id, actor=actor, action=action, target=target, after_json=after)
    )


def _clean_name(name: str) -> str:
    clean = " ".join(name.split())
    if not clean:
        raise AgentError("name_required", 422)
    return clean[:80]


async def _get(session: AsyncSession, agent_id: uuid.UUID) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise AgentError("unknown_agent", 404)
    return agent


async def create_agent(
    session: AsyncSession, tenant_id: uuid.UUID, *, name: str, actor: str
) -> Agent:
    """El agente, sin versiones. Quien llama siembra su borrador v1 (con
    ``stage_from_seed`` y este ``agent_id``) en la misma transacción."""
    agent = Agent(id=uuid.uuid4(), tenant_id=tenant_id, name=_clean_name(name))
    session.add(agent)
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        raise AgentError("name_taken", 409) from None
    _audit(session, tenant_id, actor, "agent.created", f"agent:{agent.id}", {"name": agent.name})
    return agent


async def rename_agent(
    session: AsyncSession, agent_id: uuid.UUID, *, name: str, actor: str
) -> Agent:
    agent = await _get(session, agent_id)
    before = agent.name
    agent.name = _clean_name(name)
    agent.updated_at = datetime.now(UTC)
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        raise AgentError("name_taken", 409) from None
    _audit(
        session,
        agent.tenant_id,
        actor,
        "agent.renamed",
        f"agent:{agent.id}",
        {"from": before, "to": agent.name},
    )
    return agent


async def archive_agent(session: AsyncSession, agent_id: uuid.UUID, *, actor: str) -> Agent:
    agent = await _get(session, agent_id)
    if agent.status == AgentStatus.ARCHIVED.value:
        return agent
    if await session.scalar(
        sa.select(sa.func.count()).select_from(Channel).where(Channel.agent_id == agent.id)
    ):
        raise AgentError("agent_has_channels", 409)
    others = await session.scalar(
        sa.select(sa.func.count())
        .select_from(Agent)
        .where(Agent.status == AgentStatus.ACTIVE.value, Agent.id != agent.id)
    )
    if not others:
        raise AgentError("last_agent", 409)
    agent.status = AgentStatus.ARCHIVED.value
    agent.updated_at = datetime.now(UTC)
    await session.flush()
    _audit(
        session, agent.tenant_id, actor, "agent.archived", f"agent:{agent.id}", {"name": agent.name}
    )
    return agent


async def assign_channel(
    session: AsyncSession, channel_id: uuid.UUID, agent_id: uuid.UUID, *, actor: str
) -> Channel:
    channel = await session.get(Channel, channel_id)
    if channel is None:
        raise AgentError("unknown_channel", 404)
    agent = await _get(session, agent_id)
    if agent.status != AgentStatus.ACTIVE.value:
        raise AgentError("agent_archived", 409)
    if not config_agent_enabled(channel.config):
        raise AgentError("channel_send_only", 409)
    published = await session.scalar(
        sa.select(AgentConfig.id).where(
            AgentConfig.agent_id == agent.id, AgentConfig.status == AgentConfigStatus.ACTIVE
        )
    )
    if published is None:
        raise AgentError("agent_not_published", 409)
    before = channel.agent_id
    channel.agent_id = agent.id
    await session.flush()
    _audit(
        session,
        channel.tenant_id,
        actor,
        "channel.agent_assigned",
        f"channel:{channel.id}",
        {"from": str(before) if before else None, "to": str(agent.id)},
    )
    return channel


__all__ = [
    "AgentError",
    "AgentView",
    "agent_for_channel",
    "archive_agent",
    "assign_channel",
    "create_agent",
    "list_agents",
    "principal_agent_id",
    "rename_agent",
]
