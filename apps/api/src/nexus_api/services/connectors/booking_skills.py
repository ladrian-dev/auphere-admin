"""Connecting something the agent can book with turns booking on — owner, 2026-11-03.

A connector's tools that write are born blocked, so connecting Calendly left an agent
that could see free slots and not take one. The list below says, per connector, what
making a booking takes. Connecting one puts those tools in the agent's **draft**, never
in what it answers with: the person still saves it, and its tests go stale.

A new connector that books is one more line here. What cancels stays out: it is a
decision about the customer's booking, so a person opts in.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any, Final

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    Agent,
    AgentConnectorActivation,
    AgentStatus,
    AuditLog,
    Connector,
    TenantConnector,
    ToolCatalog,
    ToolStatus,
)

log = structlog.get_logger(__name__)

#: What making a booking takes, per connector. Google Calendar has no reading of events
#: here on purpose: their titles name other customers. A slug the provider does not
#: return is skipped, so a wrong one is never written to an agent.
BOOKING_TOOLS: Final[dict[str, tuple[str, ...]]] = {
    "calendly": (
        "CALENDLY_WHO_AM_I",
        "CALENDLY_LIST_EVENT_TYPES",
        "CALENDLY_LIST_EVENT_TYPE_AVAILABLE_TIMES",
        "CALENDLY_POST_INVITEE",
        "CALENDLY_CREATE_SINGLE_USE_SCHEDULING_LINK",
    ),
    "googlecalendar": (
        "GOOGLECALENDAR_FIND_FREE_SLOTS",
        "GOOGLECALENDAR_CREATE_EVENT",
    ),
}

#: What actually takes a booking in a connector's calendar.
_BOOKS: Final = frozenset(
    {
        "CALENDLY_POST_INVITEE",
        "CALENDLY_CREATE_SINGLE_USE_SCHEDULING_LINK",
        "GOOGLECALENDAR_CREATE_EVENT",
    }
)

#: An agent with Auphere's own calendar does not get a second one: it would book in both.
_OWN_CALENDAR: Final = "reservas.create"


def books(slug: str) -> bool:
    return slug in BOOKING_TOOLS


def books_elsewhere(tools: Iterable[str] | None) -> bool:
    """The other way round: this agent already books through a connector, so
    switching Reservas on must not give it a second calendar."""
    return not _BOOKS.isdisjoint(tools or ())


def _valid_spec(spec: dict[str, Any]) -> bool:
    from pydantic import ValidationError

    from nexus_api.services.agent_spec.schema import AgentSpec

    try:
        AgentSpec.model_validate(spec)
    except ValidationError:
        return False
    return True


async def _agent_or_principal(
    session: AsyncSession, agent_id: uuid.UUID | None
) -> uuid.UUID | None:
    if agent_id is not None:
        return agent_id
    first: uuid.UUID | None = await session.scalar(
        sa.select(Agent.id)
        .where(Agent.status == AgentStatus.ACTIVE.value)
        .order_by(Agent.created_at)
        .limit(1)
    )
    return first


async def enable_booking_skills(
    session: AsyncSession,
    *,
    connector: Connector,
    install: TenantConnector,
    agent_id: uuid.UUID | None,
    actor: str,
) -> list[str]:
    """Put what ``connector`` needs to book in the draft of ``agent_id`` (the client's
    first agent if none was named). Returns what it added. Never stops a connection:
    if the draft cannot take them, the person turns them on from Skills."""
    names = BOOKING_TOOLS.get(connector.slug)
    if not names:
        return []
    target_agent = await _agent_or_principal(session, agent_id)
    if target_agent is None:
        return []
    try:
        async with session.begin_nested():
            return await _write_draft(session, connector, install, target_agent, names, actor)
    except Exception as exc:
        log.warning(
            "connector.booking_skills_failed",
            connector=connector.slug,
            agent_id=str(target_agent),
            error=type(exc).__name__,
        )
        return []


async def enable_after_sync(
    session: AsyncSession,
    *,
    connector: Connector,
    install: TenantConnector,
    actor: str,
) -> None:
    """A sync reaches the agents connected before the catalog had these tools: each
    one this connection is activated for, unless only to read. Once per agent: what
    a person took out of a draft afterwards stays out."""
    if not books(connector.slug):
        return
    agents = await session.scalars(
        sa.select(AgentConnectorActivation.agent_id)
        .join(Agent, Agent.id == AgentConnectorActivation.agent_id)
        .where(
            AgentConnectorActivation.connector_id == install.id,
            AgentConnectorActivation.permission != "read",
            Agent.status == AgentStatus.ACTIVE.value,
        )
    )
    for agent_id in list(agents):
        if await _already_enabled(session, connector, install, agent_id):
            continue
        await enable_booking_skills(
            session, connector=connector, install=install, agent_id=agent_id, actor=actor
        )


async def _already_enabled(
    session: AsyncSession, connector: Connector, install: TenantConnector, agent_id: uuid.UUID
) -> bool:
    found = await session.scalar(
        sa.select(AuditLog.id)
        .where(
            AuditLog.tenant_id == install.tenant_id,
            AuditLog.action == "connector.tools_auto_enabled",
            AuditLog.target == f"connector:{connector.slug}",
            AuditLog.after_json["agent_id"].astext == str(agent_id),
            AuditLog.after_json["booking"].as_boolean().is_(True),
        )
        .limit(1)
    )
    return found is not None


async def _write_draft(
    session: AsyncSession,
    connector: Connector,
    install: TenantConnector,
    agent_id: uuid.UUID,
    names: tuple[str, ...],
    actor: str,
) -> list[str]:
    from nexus_api.services.agent_config_service import AgentConfigService
    from nexus_api.services.testing.suites import mark_stale

    svc = AgentConfigService(session)
    draft = await svc.configs.get_draft(agent_id=agent_id)
    base = draft if draft is not None else await svc.configs.draft_base(agent_id=agent_id)
    if base is None:
        return []
    current = list(base.tools or [])
    if _OWN_CALENDAR in current:
        return []
    offered = set(
        await session.scalars(
            sa.select(ToolCatalog.name).where(
                ToolCatalog.connector_id == connector.id,
                ToolCatalog.name.in_(names),
                ToolCatalog.status == ToolStatus.ACTIVE,
            )
        )
    )
    added = [name for name in names if name in offered and name not in current]
    # What writes needs more than «read», or the turn would still hide it.
    activation = await session.scalar(
        sa.select(AgentConnectorActivation).where(
            AgentConnectorActivation.agent_id == agent_id,
            AgentConnectorActivation.connector_id == install.id,
        )
    )
    if activation is not None and activation.permission == "read":
        activation.permission = "read_write"
    if not added:
        return []
    tools = [*current, *added]
    await svc._validate_tools(tools)
    write = await svc.open_draft(actor=actor, agent_id=agent_id)
    target = write.draft
    target.tools = tools
    if target.spec:
        spec = dict(target.spec)
        spec["tools"] = list(dict.fromkeys([*(spec.get("tools") or []), *added]))
        if not _valid_spec(spec):
            raise ValueError("the agent's document cannot take these tools")
        target.spec = spec
    await svc.finish_draft(write, actor=actor)
    await mark_stale(session, agent_id)
    session.add(
        AuditLog(
            tenant_id=install.tenant_id,
            actor=actor,
            action="connector.tools_auto_enabled",
            target=f"connector:{connector.slug}",
            after_json={"tools_added": added, "agent_id": str(agent_id), "booking": True},
        )
    )
    await session.flush()
    return added


__all__ = [
    "BOOKING_TOOLS",
    "books",
    "books_elsewhere",
    "enable_after_sync",
    "enable_booking_skills",
]
