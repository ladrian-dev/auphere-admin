"""Las transiciones de la vida de un agente — spec 047, T123 (requisitos 25 a 28;
``data-model.md`` §12).

```text
          publicar                pausar (persona | sin saldo | tope | cliente)
draft ─────────────▶ published ◀────────────────────────────▶ paused
  │                      │            reanudar (devuelve before_pause)  │
  └──── archivar ────────┴───────────────▶ archived ◀───────────────────┘
                                             │ restaurar
                                             ▼
                                           paused
```

- **Pausar** guarda el motivo, quién, desde dónde y lo que había antes; los
  mensajes se siguen guardando y van a la Bandeja con su motivo (27.2). Pausar no
  toca los canales (25.4).
- **Reanudar** devuelve lo de antes (27.3). La pausa del sistema (sin saldo, tope
  del agente) solo la deshace el sistema, y solo la suya: un agente que una
  persona pausó sigue en pausa cuando vuelve el saldo (27.4).
- **Archivar** pide el destino de cada número (otro agente o en pausa) y nunca
  borra nada (28.1, 28.3). El agente por defecto exige elegir otro antes (28.4).
- **Restaurar** deja el agente en pausa (28.2).
- **El agente por defecto** cambia de forma atómica: siempre hay exactamente uno
  entre los no archivados (26.2).

``status`` sigue a la vida en lo que la de hoy sabe decir (``archived``).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final, Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    AgentStatus,
    AuditLog,
    Channel,
    ChannelStatus,
    Conversation,
    ConversationStatus,
)

PauseReason = Literal["manual", "no_balance", "agent_cap", "client_paused", "client_archived"]
ActorKind = Literal["partner_member", "client_user", "operator", "system"]
#: La pausa que pone y quita el sistema, no una persona (27.4, 27.5).
SYSTEM_REASONS: Final = frozenset({"no_balance", "agent_cap"})


class AgentStateError(Exception):
    def __init__(self, code: str, status: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def _audit(
    agent: Agent,
    actor: str,
    action: str,
    after: Mapping[str, Any],
    before: Mapping[str, Any] | None = None,
) -> AuditLog:
    return AuditLog(
        tenant_id=agent.tenant_id,
        actor=actor,
        action=action,
        target=f"agent:{agent.id}",
        before_json=dict(before) if before is not None else None,
        after_json=dict(after),
    )


async def _published(session: AsyncSession, agent: Agent) -> bool:
    found = await session.scalar(
        sa.select(AgentConfig.id).where(
            AgentConfig.tenant_id == agent.tenant_id,
            AgentConfig.agent_id == agent.id,
            AgentConfig.status == AgentConfigStatus.ACTIVE,
        )
    )
    return found is not None


async def open_conversations(session: AsyncSession, agent: Agent) -> int:
    """Las conversaciones en curso en los números del agente (27.8: pausar con
    conversaciones abiertas pide confirmación y dice cuántas)."""
    return int(
        await session.scalar(
            sa.select(sa.func.count())
            .select_from(Conversation)
            .join(Channel, Channel.id == Conversation.channel_id)
            .where(
                Conversation.tenant_id == agent.tenant_id,
                Channel.agent_id == agent.id,
                Conversation.status.in_([ConversationStatus.OPEN, ConversationStatus.ESCALATED]),
            )
        )
        or 0
    )


def mark_published(agent: Agent) -> None:
    """Publicar la primera versión saca al agente del borrador; publicar en pausa
    no lo reanuda."""
    if agent.lifecycle == "draft":
        agent.lifecycle = "published"


async def pause(
    session: AsyncSession,
    agent: Agent,
    *,
    reason: PauseReason = "manual",
    by_kind: ActorKind,
    by_id: str | None,
    origin: str,
    actor: str,
    note: str | None = None,
) -> Agent:
    if agent.lifecycle == "archived":
        raise AgentStateError("agent_archived")
    if agent.lifecycle == "paused":
        if agent.pause_reason == reason or reason in SYSTEM_REASONS:
            return agent
        # Una persona que pausa un agente que el sistema pausó se queda la pausa:
        # al volver el saldo no se reanuda solo.
        agent.pause_reason = reason
    else:
        agent.before_pause = {"lifecycle": agent.lifecycle}
        agent.lifecycle = "paused"
        agent.pause_reason = reason
    agent.paused_at = datetime.now(UTC)
    agent.paused_by_kind = by_kind
    agent.paused_by_id = by_id
    agent.paused_origin = origin
    session.add(
        _audit(
            agent,
            actor,
            "agent.paused",
            {"reason": reason, "by": by_kind, "origin": origin, "note": note},
        )
    )
    await session.flush()
    return agent


async def resume(
    session: AsyncSession,
    agent: Agent,
    *,
    by_kind: ActorKind,
    by_id: str | None,
    origin: str,
    actor: str,
    system_reason: PauseReason | None = None,
) -> Agent:
    """Devuelve lo que había antes de la pausa. ``system_reason``: la reanudación
    del sistema, que solo deshace su propia pausa (27.4)."""
    if agent.lifecycle != "paused":
        if agent.lifecycle == "archived":
            raise AgentStateError("agent_archived")
        return agent
    if system_reason is not None and agent.pause_reason != system_reason:
        return agent
    before = dict(agent.before_pause or {})
    target = before.get("lifecycle")
    if target not in {"draft", "published"}:
        target = "published" if await _published(session, agent) else "draft"
    previous_reason = agent.pause_reason
    agent.lifecycle = target
    agent.pause_reason = None
    agent.paused_at = None
    agent.paused_by_kind = None
    agent.paused_by_id = None
    agent.paused_origin = None
    agent.before_pause = None
    session.add(
        _audit(
            agent,
            actor,
            "agent.resumed",
            {"to": target, "by": by_kind, "origin": origin},
            {"reason": previous_reason},
        )
    )
    await session.flush()
    return agent


async def pause_for_balance(session: AsyncSession) -> list[uuid.UUID]:
    """La bolsa del cliente se vació: sus agentes publicados se pausan (27.4)."""
    out: list[uuid.UUID] = []
    for agent in (
        await session.scalars(
            sa.select(Agent).where(
                Agent.tenant_id == require_current_tenant(), Agent.lifecycle == "published"
            )
        )
    ).all():
        await pause(
            session,
            agent,
            reason="no_balance",
            by_kind="system",
            by_id=None,
            origin="system",
            actor="system",
        )
        out.append(agent.id)
    return out


async def resume_after_balance(session: AsyncSession) -> list[uuid.UUID]:
    """Volvió el saldo: se reanudan **solo** los que el sistema pausó por eso."""
    out: list[uuid.UUID] = []
    for agent in (
        await session.scalars(
            sa.select(Agent).where(
                Agent.tenant_id == require_current_tenant(),
                Agent.lifecycle == "paused",
                Agent.pause_reason == "no_balance",
            )
        )
    ).all():
        await resume(
            session,
            agent,
            by_kind="system",
            by_id=None,
            origin="system",
            actor="system",
            system_reason="no_balance",
        )
        out.append(agent.id)
    return out


async def resume_after_cap(
    session: AsyncSession, *, month_start: datetime | None = None, agent_id: uuid.UUID | None = None
) -> list[uuid.UUID]:
    """El tope del agente ya no manda (44.3): empezó el mes (``month_start``: los
    pausados antes de ese momento) o se subió su tope (``agent_id``). Solo deshace
    la pausa ``agent_cap`` del sistema."""
    stmt = sa.select(Agent).where(
        Agent.tenant_id == require_current_tenant(),
        Agent.lifecycle == "paused",
        Agent.pause_reason == "agent_cap",
    )
    if month_start is not None:
        stmt = stmt.where(Agent.paused_at < month_start)
    if agent_id is not None:
        stmt = stmt.where(Agent.id == agent_id)
    out: list[uuid.UUID] = []
    for agent in (await session.scalars(stmt)).all():
        await resume(
            session,
            agent,
            by_kind="system",
            by_id=None,
            origin="system",
            actor="system",
            system_reason="agent_cap",
        )
        out.append(agent.id)
    return out


async def set_default(session: AsyncSession, agent: Agent, *, actor: str) -> Agent:
    """El agente por defecto, de forma atómica (26.2): se quita al anterior y se
    pone a este en la misma transacción, con el cliente bloqueado."""
    if agent.lifecycle == "archived":
        raise AgentStateError("agent_archived")
    tenant_id = require_current_tenant()
    previous = await session.scalar(
        sa.select(Agent)
        .where(
            Agent.tenant_id == tenant_id, Agent.is_default.is_(True), Agent.lifecycle != "archived"
        )
        .with_for_update()
    )
    if previous is not None and previous.id == agent.id:
        return agent
    if previous is not None:
        previous.is_default = False
        await session.flush()
    agent.is_default = True
    session.add(
        _audit(
            agent,
            actor,
            "agent.default_changed",
            {"to": str(agent.id)},
            {"from": str(previous.id) if previous else None},
        )
    )
    await session.flush()
    return agent


async def archive(
    session: AsyncSession,
    agent: Agent,
    *,
    channels: Mapping[uuid.UUID, uuid.UUID | Literal["pause"]],
    actor: str,
) -> Agent:
    """Archivar (28.1): cada número del agente pasa a otro agente o queda en pausa.
    Nada se borra (28.3)."""
    if agent.lifecycle == "archived":
        return agent
    if agent.is_default:
        raise AgentStateError("default_agent_required")
    own = (
        await session.scalars(
            sa.select(Channel).where(
                Channel.tenant_id == agent.tenant_id, Channel.agent_id == agent.id
            )
        )
    ).all()
    missing = [str(c.id) for c in own if c.id not in channels]
    if missing:
        raise AgentStateError("channel_destination_required", 422)
    moved: dict[str, str] = {}
    for channel in own:
        target = channels[channel.id]
        if target == "pause":
            channel.status = ChannelStatus.PAUSED
            moved[str(channel.id)] = "paused"
            continue
        to = await session.get(Agent, target)
        if (
            to is None
            or to.tenant_id != agent.tenant_id
            or to.lifecycle == "archived"
            or to.id == agent.id
        ):
            raise AgentStateError("unknown_target_agent", 422)
        channel.agent_id = to.id
        moved[str(channel.id)] = str(to.id)
    before = agent.lifecycle
    agent.lifecycle = "archived"
    agent.status = AgentStatus.ARCHIVED.value
    agent.pause_reason = None
    agent.before_pause = None
    session.add(_audit(agent, actor, "agent.archived", {"channels": moved}, {"lifecycle": before}))
    await session.flush()
    return agent


async def restore(session: AsyncSession, agent: Agent, *, actor: str) -> Agent:
    """Restaurar (28.2): vuelve en pausa, para que nadie lo active sin querer."""
    if agent.lifecycle != "archived":
        raise AgentStateError("not_archived")
    agent.status = AgentStatus.ACTIVE.value
    agent.lifecycle = "paused"
    agent.pause_reason = "manual"
    agent.before_pause = {"lifecycle": "published" if await _published(session, agent) else "draft"}
    agent.paused_at = datetime.now(UTC)
    agent.paused_by_kind = "partner_member"
    agent.paused_origin = "console"
    session.add(_audit(agent, actor, "agent.restored", {"lifecycle": "paused"}))
    await session.flush()
    return agent


__all__ = [
    "SYSTEM_REASONS",
    "AgentStateError",
    "archive",
    "mark_published",
    "open_conversations",
    "pause",
    "pause_for_balance",
    "restore",
    "resume",
    "resume_after_balance",
    "resume_after_cap",
    "set_default",
]
