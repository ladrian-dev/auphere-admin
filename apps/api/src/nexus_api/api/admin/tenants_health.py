"""Admin — the health of every client, for the client list (spec 036).

One row per client with what the operator scans for: live and failing
channels, the main channel, the published version of the principal agent,
open and recent conversations, and connectors asking to reconnect.

``channels``, ``conversations``, ``agent_configs`` and ``tenant_connectors``
are tenant tables with RLS, so each client is read **under its own GUC**
(``tenant_scoped_session``). A client that cannot be read is named in
``unreadable`` and the rest of the list still comes back. The Playground's
channel and its conversations never count.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.security import require_admin_token
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AgentConfig, Channel, Tenant, TenantConnector
from nexus_api.db.models.agent import Agent, AgentConfigStatus, AgentStatus
from nexus_api.db.models.channel import QA_PLAYGROUND_PROVIDER
from nexus_api.db.models.conversation import Conversation, ConversationStatus

log = structlog.get_logger(__name__)

router = APIRouter(dependencies=[Depends(require_admin_token)])

#: Channel states that need someone (an active one serves; disconnected is retired).
_CHANNEL_ATTENTION = ("degraded", "paused")
#: Connector states that need someone to reconnect.
_CONNECTOR_ATTENTION = ("needs_reauth", "error")
_OPEN = (ConversationStatus.OPEN, ConversationStatus.ESCALATED)


class PrimaryChannelOut(BaseModel):
    type: str
    identifier: str
    status: str


class TenantHealthOut(BaseModel):
    tenant_id: uuid.UUID
    channels_active: int
    channels_attention: int
    primary_channel: PrimaryChannelOut | None
    #: Published version of the principal agent; ``None`` = nothing published.
    agent_version: int | None
    open_conversations: int
    conversations_7d: int
    last_message_at: datetime | None
    connectors_attention: int


class TenantsHealthOut(BaseModel):
    clients: list[TenantHealthOut]
    unreadable: list[uuid.UUID]


def _value(v: object) -> str:
    return str(getattr(v, "value", v))


async def _health(s: AsyncSession, tenant_id: uuid.UUID, since: datetime) -> TenantHealthOut:
    channels = (
        (
            await s.execute(
                sa.select(Channel)
                .where(Channel.provider != QA_PLAYGROUND_PROVIDER)
                .order_by(Channel.created_at)
            )
        )
        .scalars()
        .all()
    )
    live = [c for c in channels if _value(c.status) == "active"]
    attention = [c for c in channels if _value(c.status) in _CHANNEL_ATTENTION]
    # The main channel: the first that serves, else the first that is failing.
    primary = live[0] if live else (attention[0] if attention else None)

    real = sa.select(Channel.id).where(Channel.provider != QA_PLAYGROUND_PROVIDER)
    open_count, recent, last = (
        await s.execute(
            sa.select(
                sa.func.count().filter(Conversation.status.in_(_OPEN)),
                sa.func.count().filter(Conversation.last_message_at >= since),
                sa.func.max(Conversation.last_message_at),
            ).where(Conversation.channel_id.in_(real))
        )
    ).one()

    # The principal agent is the oldest active one (spec 030).
    principal = (
        await s.execute(
            sa.select(Agent.id)
            .where(Agent.status == AgentStatus.ACTIVE.value)
            .order_by(Agent.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    version_q = sa.select(sa.func.max(AgentConfig.version)).where(
        AgentConfig.status == AgentConfigStatus.ACTIVE
    )
    if principal is not None:
        version_q = version_q.where(AgentConfig.agent_id == principal)
    version = (await s.execute(version_q)).scalar_one_or_none()

    broken = (
        await s.execute(
            sa.select(sa.func.count()).where(
                sa.cast(TenantConnector.status, sa.String).in_(_CONNECTOR_ATTENTION)
            )
        )
    ).scalar_one()

    return TenantHealthOut(
        tenant_id=tenant_id,
        channels_active=len(live),
        channels_attention=len(attention),
        primary_channel=(
            PrimaryChannelOut(
                type=_value(primary.type),
                identifier=primary.provider_identifier,
                status=_value(primary.status),
            )
            if primary
            else None
        ),
        agent_version=version,
        open_conversations=open_count or 0,
        conversations_7d=recent or 0,
        last_message_at=last,
        connectors_attention=broken or 0,
    )


@router.get("/tenants-health/{tenant_id}", response_model=TenantHealthOut)
async def tenant_health(tenant_id: uuid.UUID) -> TenantHealthOut:
    """One client's health, for the header of its profile."""
    since = datetime.now(UTC) - timedelta(days=7)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        return await _health(s, tenant_id, since)


@router.get("/tenants-health", response_model=TenantsHealthOut)
async def tenants_health(session: AsyncSession = Depends(get_db_session)) -> TenantsHealthOut:
    async with session.begin():
        ids = (await session.execute(sa.select(Tenant.id).order_by(Tenant.name))).scalars().all()
    since = datetime.now(UTC) - timedelta(days=7)
    sm = get_sessionmaker()
    out: list[TenantHealthOut] = []
    unreadable: list[uuid.UUID] = []
    for tenant_id in ids:
        try:
            async with sm() as s, tenant_scoped_session(s, tenant_id):
                out.append(await _health(s, tenant_id, since))
        except Exception as exc:  # pragma: no cover - surfaced as a partial state
            log.warning("admin.tenants_health.unreadable", tenant_id=str(tenant_id), error=str(exc))
            unreadable.append(tenant_id)
    return TenantsHealthOut(clients=out, unreadable=unreadable)
