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
from datetime import UTC, date, datetime, timedelta
from typing import Any

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
    ConversationStatus,
    Message,
    MessageDirection,
    MessageStatus,
    PaymentReview,
    TenantCredentials,
)
from nexus_api.db.models.payment_review import REVIEW_PENDING
from nexus_api.services.agent_audience import AudienceMode, count_of
from nexus_api.services.console_traffic import customer_conversation_ids, customer_facing_channel

log = structlog.get_logger(__name__)

SNAPSHOT_CONCURRENCY = 6
INCIDENT_WINDOW = timedelta(hours=24)
#: Spec 026: «por revisar» and the portfolio look at the last 7 days.
REVIEW_WINDOW = timedelta(days=7)
#: Spec 026 (D5): 14 days of daily conversations, 7 shown and 7 to compare.
TREND_DAYS = 14
#: Spec 026: a draft older than this is «cambios sin publicar».
STALE_DRAFT = timedelta(days=1)


@dataclass(frozen=True)
class TenantSnapshot:
    tenant_id: uuid.UUID
    conversations_month: int
    failed_messages_24h: int
    agent_version: int | None
    whatsapp_channels: int
    whatsapp_bad: int  # degraded | disconnected
    #: Spec 017 (R1.1): any ACTIVE customer-facing channel counts as «canal»
    #: (WhatsApp today; Instagram and Messenger tomorrow). The Playground never.
    active_channels: int = 0
    #: Spec 024 (Requisito 3.1): who the ACTIVE agent answers. ``None`` when
    #: there is no active version.
    audience_mode: AudienceMode | None = None
    audience_count: int = 0
    # ── spec 026 ────────────────────────────────────────────────────────
    #: ESCALATED conversations whose customer wrote in the last 7 days (D2).
    escalated_recent: int = 0
    payments_pending: int = 0
    #: Inbounds the agent did not answer (allowed-numbers list) in 7 days.
    unanswered_7d: int = 0
    whatsapp_quality_red: int = 0
    needs_reauth: int = 0
    #: A STAGED version older than ``STALE_DRAFT``.
    stale_drafts: int = 0
    waba_ids: tuple[str, ...] = ()
    last_activity_at: datetime | None = None
    #: ``date → conversations`` for the last ``TREND_DAYS`` UTC days.
    daily: dict[date, int] = field(default_factory=dict)

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
    month_start: datetime, since_24h: datetime, now: datetime | None = None
) -> sa.Select[tuple[Any, ...]]:
    # Playground traffic is not customer traffic (``console_traffic``).
    conversations = (
        sa.select(sa.func.count())
        .select_from(Conversation)
        .where(
            Conversation.created_at >= month_start,
            Conversation.id.in_(customer_conversation_ids()),
        )
        .scalar_subquery()
    )
    failed = (
        sa.select(sa.func.count())
        .select_from(Message)
        .where(
            Message.status == MessageStatus.FAILED,
            Message.created_at >= since_24h,
            Message.conversation_id.in_(customer_conversation_ids()),
        )
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
    active_channels = (
        sa.select(sa.func.count())
        .select_from(Channel)
        .where(Channel.status == ChannelStatus.ACTIVE, customer_facing_channel())
        .scalar_subquery()
    )
    policies = (
        sa.select(AgentConfig.policies)
        .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
        .order_by(AgentConfig.version.desc())
        .limit(1)
        .scalar_subquery()
    )
    now = now or datetime.now(UTC)
    since_7d = now - REVIEW_WINDOW
    escalated = (
        sa.select(sa.func.count())
        .select_from(Conversation)
        .where(
            Conversation.status == ConversationStatus.ESCALATED,
            Conversation.last_inbound_at >= since_7d,
            Conversation.id.in_(customer_conversation_ids()),
        )
        .scalar_subquery()
    )
    payments = (
        sa.select(sa.func.count())
        .select_from(PaymentReview)
        .where(PaymentReview.status == REVIEW_PENDING)
        .scalar_subquery()
    )
    unanswered = (
        sa.select(sa.func.count())
        .select_from(Message)
        .where(
            Message.direction == MessageDirection.INBOUND,
            Message.skipped_reason.is_not(None),
            Message.created_at >= since_7d,
        )
        .scalar_subquery()
    )
    quality_red = (
        sa.select(sa.func.count())
        .select_from(Channel)
        .where(
            Channel.type == ChannelType.WHATSAPP,
            Channel.status == ChannelStatus.ACTIVE,
            Channel.config["quality_rating"].astext == "RED",
        )
        .scalar_subquery()
    )
    reauth = (
        sa.select(sa.func.count())
        .select_from(TenantCredentials)
        .where(TenantCredentials.needs_reauth.is_(True))
        .scalar_subquery()
    )
    drafts = (
        sa.select(sa.func.count())
        .select_from(AgentConfig)
        .where(
            AgentConfig.status == AgentConfigStatus.STAGED,
            AgentConfig.created_at < now - STALE_DRAFT,
        )
        .scalar_subquery()
    )
    wabas = (
        sa.select(sa.func.array_agg(sa.distinct(Channel.config["waba_id"].astext)))
        .where(Channel.type == ChannelType.WHATSAPP, Channel.config["waba_id"].astext.is_not(None))
        .scalar_subquery()
    )
    last_activity = (
        # The latest customer message, or the latest conversation start
        # when the business wrote first (GREATEST skips NULLs in Postgres).
        sa.select(
            sa.func.greatest(
                sa.func.max(Conversation.last_inbound_at), sa.func.max(Conversation.created_at)
            )
        )
        .where(Conversation.id.in_(customer_conversation_ids()))
        .scalar_subquery()
    )
    return sa.select(
        conversations,
        failed,
        agent,
        wa_total,
        wa_bad,
        active_channels,
        policies,
        escalated,
        payments,
        unanswered,
        quality_red,
        reauth,
        drafts,
        wabas,
        last_activity,
    )


def _daily_stmt(since: datetime) -> sa.Select[tuple[Any, int]]:
    """Customer conversations started per UTC day since ``since`` (D5)."""
    day = sa.func.date_trunc("day", sa.func.timezone("UTC", Conversation.created_at))
    return (
        sa.select(day, sa.func.count())
        .where(
            Conversation.created_at >= since,
            Conversation.id.in_(customer_conversation_ids()),
        )
        .group_by(day)
    )


def trend_start(now: datetime) -> datetime:
    """Midnight UTC ``TREND_DAYS - 1`` days ago: today is the last bucket."""
    today = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=TREND_DAYS - 1)


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
    stmt = _snapshot_stmt(month_start, since_24h, now)
    daily_stmt = _daily_stmt(trend_start(now))
    sm = get_sessionmaker()
    sem = asyncio.Semaphore(max(1, concurrency))
    result = SnapshotResult()

    async def _one(tid: uuid.UUID) -> None:
        async with sem:
            try:
                async with sm() as session, tenant_scoped_session(session, tid):
                    row = (await session.execute(stmt)).one()
                    daily_rows = (await session.execute(daily_stmt)).all()
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
            active_channels=int(row[5] or 0),
            audience_mode=count_of(row[6])[0] if row[2] is not None else None,
            audience_count=count_of(row[6])[1] if row[2] is not None else 0,
            escalated_recent=int(row[7] or 0),
            payments_pending=int(row[8] or 0),
            unanswered_7d=int(row[9] or 0),
            whatsapp_quality_red=int(row[10] or 0),
            needs_reauth=int(row[11] or 0),
            stale_drafts=int(row[12] or 0),
            waba_ids=tuple(w for w in (row[13] or []) if w),
            last_activity_at=row[14],
            daily={d.date(): int(c) for d, c in daily_rows if d is not None},
        )

    await asyncio.gather(*(_one(t) for t in tenant_ids))
    return result


__all__ = [
    "INCIDENT_WINDOW",
    "REVIEW_WINDOW",
    "SNAPSHOT_CONCURRENCY",
    "TREND_DAYS",
    "SnapshotResult",
    "TenantSnapshot",
    "tenant_snapshots",
    "trend_start",
]
