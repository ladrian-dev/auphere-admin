"""Aggregations behind ``GET /console/home`` (CP-08).

Five figures in one response, under one second for a partner the size of
Facelad (≥ 20 clients, ≥ 5 000 conversations, ≥ 50 000 usage rows a
month). Where each figure comes from and why:

- **clients** — ``tenants`` joined to ``partner_tenants``: platform tables,
  no RLS, one query.
- **usage_units** (channel messages of the month vs. cap) — ONE query on
  ``usage_records`` under ``nexus_reporting`` (``console_reporting.py``).
- **conversations_period** and **agents_with_incidents** — need
  ``conversations``, ``messages``, ``channels`` and ``agent_configs``, all
  RLS-forced per tenant and WITHOUT a reporting policy (and we do not
  widen the read-only role to ``messages`` for a home page). So: one
  scoped transaction per ACTIVE client that runs a single statement with
  four scalar sub-selects, on its own pooled session, with bounded
  concurrency (``SNAPSHOT_CONCURRENCY``). Cost is 2 round trips per
  client (``set_config`` + query); at 20 clients that is well under 100 ms
  locally — measured in ``scripts/dev_seed_console_volume.py``'s report.
  If a partner ever has hundreds of clients this is the block to move to
  a materialised counter; the response already isolates it (``errors``).
- **pending_actions** — clients in ``provisioning`` (platform), pending
  invitations (platform), unread ``usage.*`` notifications (platform).

Incident definition (documented here, rendered by the console): an
ACTIVE client whose WhatsApp channel is ``degraded`` or ``disconnected``,
or that has no ACTIVE agent version, or that has ≥ 1 ``failed`` message in
the last 24 h.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
import structlog

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    Message,
    MessageStatus,
)

log = structlog.get_logger(__name__)

SNAPSHOT_CONCURRENCY = 6
INCIDENT_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class TenantSnapshot:
    tenant_id: uuid.UUID
    conversations_month: int
    failed_messages_24h: int
    agent_version: int | None
    whatsapp_channels: int
    whatsapp_bad: int  # degraded | disconnected

    @property
    def issues(self) -> list[str]:
        out: list[str] = []
        if self.whatsapp_bad:
            out.append("whatsapp_degraded")
        if self.agent_version is None:
            out.append("no_active_agent")
        if self.failed_messages_24h > 0:
            out.append("failed_messages_24h")
        return out


@dataclass
class SnapshotResult:
    snapshots: dict[uuid.UUID, TenantSnapshot] = field(default_factory=dict)
    failed: list[uuid.UUID] = field(default_factory=list)


def _snapshot_stmt(
    month_start: datetime, since_24h: datetime
) -> sa.Select[tuple[int, int, int | None, int, int]]:
    conversations = (
        sa.select(sa.func.count())
        .select_from(Conversation)
        .where(Conversation.created_at >= month_start)
        .scalar_subquery()
    )
    failed = (
        sa.select(sa.func.count())
        .select_from(Message)
        .where(Message.status == MessageStatus.FAILED, Message.created_at >= since_24h)
        .scalar_subquery()
    )
    agent = (
        sa.select(AgentConfig.version)
        .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
        .order_by(AgentConfig.version.desc())
        .limit(1)
        .scalar_subquery()
    )
    wa_total = (
        sa.select(sa.func.count())
        .select_from(Channel)
        .where(Channel.type == ChannelType.WHATSAPP)
        .scalar_subquery()
    )
    wa_bad = (
        sa.select(sa.func.count())
        .select_from(Channel)
        .where(
            Channel.type == ChannelType.WHATSAPP,
            Channel.status.in_([ChannelStatus.DEGRADED, ChannelStatus.DISCONNECTED]),
        )
        .scalar_subquery()
    )
    return sa.select(conversations, failed, agent, wa_total, wa_bad)


async def tenant_snapshots(
    tenant_ids: list[uuid.UUID],
    *,
    month_start: datetime,
    now: datetime | None = None,
    concurrency: int = SNAPSHOT_CONCURRENCY,
) -> SnapshotResult:
    """One scoped statement per tenant, ``concurrency`` at a time, each on
    its own pooled session (a session cannot run two transactions at once).
    A tenant whose query fails is reported in ``failed`` and skipped — the
    home page degrades that block instead of failing whole."""
    now = now or datetime.now(UTC)
    since_24h = now - INCIDENT_WINDOW
    stmt = _snapshot_stmt(month_start, since_24h)
    sm = get_sessionmaker()
    sem = asyncio.Semaphore(max(1, concurrency))
    result = SnapshotResult()

    async def _one(tid: uuid.UUID) -> None:
        async with sem:
            try:
                async with sm() as session, tenant_scoped_session(session, tid):
                    row = (await session.execute(stmt)).one()
            except Exception as exc:
                log.warning("console_home.snapshot_failed", tenant_id=str(tid), error=str(exc))
                result.failed.append(tid)
                return
        result.snapshots[tid] = TenantSnapshot(
            tenant_id=tid,
            conversations_month=int(row[0] or 0),
            failed_messages_24h=int(row[1] or 0),
            agent_version=int(row[2]) if row[2] is not None else None,
            whatsapp_channels=int(row[3] or 0),
            whatsapp_bad=int(row[4] or 0),
        )

    await asyncio.gather(*(_one(t) for t in tenant_ids))
    return result


__all__ = [
    "INCIDENT_WINDOW",
    "SNAPSHOT_CONCURRENCY",
    "SnapshotResult",
    "TenantSnapshot",
    "tenant_snapshots",
]
