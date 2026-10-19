"""Admin — what every partner and every client consumed (spec 038).

Two sources, never mixed under one name (spec 033 R7.2):

- **Gasto** (sale price): debits in each partner's ``usage_ledger``, read
  under that partner's GUC (``credit_burn_by_day``). A direct Auphere client
  has no partner wallet, so its spend is zero here.
- **Coste interno** (what the model cost Auphere): ``messages.cost_usd``,
  summed as a decimal under each client's GUC. It includes the Playground,
  because those turns are paid too; message and conversation counts do not.

Each partner and each client is read on its own; one that cannot be read is
named in ``unreadable`` and the rest still comes back.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.partner_wallet import _wallet_out
from nexus_api.api.deps import get_db_session
from nexus_api.billing.pricing import credits_to_cents
from nexus_api.core.security import require_admin_token
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Channel, Partner, Tenant
from nexus_api.db.models.channel import QA_PLAYGROUND_PROVIDER
from nexus_api.db.models.conversation import Conversation, Message, MessageDirection
from nexus_api.metering.wallet import credit_burn_by_day

log = structlog.get_logger(__name__)

#: How many partners or clients are read at once: each read is its own short
#: session, so the view scales with the platform without one long scan.
_PARALLEL = 8

router = APIRouter(dependencies=[Depends(require_admin_token)])


class UsageTotalsOut(BaseModel):
    spend_cents: int
    internal_cost_usd: str
    #: Sale price minus model cost, in US$ (decimal string).
    margin_usd: str
    messages: int
    conversations: int
    active_clients: int


class PartnerUsageRowOut(BaseModel):
    partner_id: uuid.UUID
    name: str
    status: str
    clients: int
    spend_cents: int
    spend_outside_clients_cents: int
    internal_cost_usd: str
    messages: int
    available_cents: int | None


class ClientUsageRowOut(BaseModel):
    tenant_id: uuid.UUID
    name: str
    status: str
    partner_id: uuid.UUID | None
    partner_name: str | None
    spend_cents: int
    internal_cost_usd: str
    messages_inbound: int
    messages_outbound: int
    conversations: int


class DailyUsageOut(BaseModel):
    day: date
    spend_cents: int
    internal_cost_usd: str
    messages: int


class UnreadableOut(BaseModel):
    partners: list[uuid.UUID]
    clients: list[uuid.UUID]


class UsageOverviewOut(BaseModel):
    since: datetime
    until: datetime
    totals: UsageTotalsOut
    partners: list[PartnerUsageRowOut]
    clients: list[ClientUsageRowOut]
    daily: list[DailyUsageOut]
    unreadable: UnreadableOut


def _dec(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.0001")).normalize()) if value else "0"


async def _client_reading(
    tenant_id: uuid.UUID, since: datetime
) -> tuple[dict[date, tuple[int, int, Decimal]], int]:
    """Per UTC day: (inbound, outbound, model cost), and conversations started."""
    day = sa.cast(sa.func.timezone("UTC", Message.created_at), sa.Date)
    real = Channel.provider != QA_PLAYGROUND_PROVIDER
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        rows = await s.execute(
            sa.select(
                day,
                sa.func.count(Message.id).filter(
                    Message.direction == MessageDirection.INBOUND, real
                ),
                sa.func.count(Message.id).filter(
                    Message.direction == MessageDirection.OUTBOUND, real
                ),
                sa.func.coalesce(sa.func.sum(sa.cast(Message.cost_usd, sa.Numeric(20, 8))), 0),
            )
            .select_from(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .join(Channel, Channel.id == Conversation.channel_id)
            .where(Message.created_at >= since)
            .group_by(day)
        )
        per_day = {d: (int(i), int(o), Decimal(c)) for d, i, o, c in rows.all()}
        conversations = await s.scalar(
            sa.select(sa.func.count(Conversation.id))
            .join(Channel, Channel.id == Conversation.channel_id)
            .where(Conversation.created_at >= since, real)
        )
    return per_day, int(conversations or 0)


@router.get("/usage", response_model=UsageOverviewOut)
async def usage_overview(
    days: int = Query(default=30, ge=1, le=365),
    month: bool = Query(default=False, description="From the 1st of this month (UTC)"),
    session: AsyncSession = Depends(get_db_session),
) -> UsageOverviewOut:
    now = datetime.now(UTC)
    since = (
        now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month
        else now - timedelta(days=days)
    )
    async with session.begin():
        tenants = (await session.execute(sa.select(Tenant).order_by(Tenant.name))).scalars().all()
        partners = (
            (await session.execute(sa.select(Partner).order_by(Partner.name))).scalars().all()
        )
    by_partner: dict[uuid.UUID, list[Tenant]] = defaultdict(list)
    for t in tenants:
        if t.partner_id is not None:
            by_partner[t.partner_id].append(t)
    partner_name = {p.id: p.name for p in partners}

    daily_spend: dict[date, int] = defaultdict(int)
    daily_cost: dict[date, Decimal] = defaultdict(Decimal)
    daily_messages: dict[date, int] = defaultdict(int)
    client_spend: dict[uuid.UUID, int] = {}
    unreadable_partners: list[uuid.UUID] = []
    unreadable_clients: list[uuid.UUID] = []

    gate = asyncio.Semaphore(_PARALLEL)

    async def read_partner(
        p: Partner,
    ) -> tuple[Partner, dict[tuple[uuid.UUID | None, date], int] | None, int | None]:
        async with gate:
            try:
                burn = await credit_burn_by_day(
                    p.id, [t.id for t in by_partner.get(p.id, [])], since
                )
            except Exception as exc:  # pragma: no cover - surfaced as a partial state
                log.warning("admin.usage.partner_unreadable", partner_id=str(p.id), error=str(exc))
                burn = None
            try:
                available: int | None = (await _wallet_out(p.id)).available_cents
            except Exception:  # pragma: no cover - a balance that cannot be read is not zero
                available = None
            return p, burn, available

    partner_rows: dict[uuid.UUID, PartnerUsageRowOut] = {}
    for p, burn, available in await asyncio.gather(*(read_partner(p) for p in partners)):
        if burn is None:
            unreadable_partners.append(p.id)
            burn = {}
        outside = 0
        spend = 0
        per_client: dict[uuid.UUID | None, int] = defaultdict(int)
        for (tid, d), credits in burn.items():
            per_client[tid] += credits
            daily_spend[d] += credits_to_cents(credits, nearest=True)
        for tid, credits in per_client.items():
            cents = credits_to_cents(credits, nearest=True)
            spend += cents
            if tid is None:
                outside = cents
            else:
                client_spend[tid] = cents
        partner_rows[p.id] = PartnerUsageRowOut(
            partner_id=p.id,
            name=p.name,
            status=str(getattr(p.status, "value", p.status)),
            clients=len(by_partner.get(p.id, [])),
            spend_cents=spend,
            spend_outside_clients_cents=outside,
            internal_cost_usd="0",
            messages=0,
            available_cents=available,
        )

    client_rows: list[ClientUsageRowOut] = []
    partner_cost: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    partner_messages: dict[uuid.UUID, int] = defaultdict(int)

    async def read_client(
        t: Tenant,
    ) -> tuple[Tenant, tuple[dict[date, tuple[int, int, Decimal]], int] | None]:
        async with gate:
            try:
                return t, await _client_reading(t.id, since)
            except Exception as exc:  # pragma: no cover - partial state
                log.warning("admin.usage.client_unreadable", tenant_id=str(t.id), error=str(exc))
                return t, None

    for t, reading in await asyncio.gather(*(read_client(t) for t in tenants)):
        if reading is None:
            unreadable_clients.append(t.id)
            continue
        per_day, conversations = reading
        inbound = sum(v[0] for v in per_day.values())
        outbound = sum(v[1] for v in per_day.values())
        cost = sum((v[2] for v in per_day.values()), Decimal(0))
        for d, (i, o, c) in per_day.items():
            daily_messages[d] += i + o
            daily_cost[d] += c
        if t.partner_id is not None:
            partner_cost[t.partner_id] += cost
            partner_messages[t.partner_id] += inbound + outbound
        client_rows.append(
            ClientUsageRowOut(
                tenant_id=t.id,
                name=t.name,
                status=str(getattr(t.status, "value", t.status)),
                partner_id=t.partner_id,
                partner_name=partner_name.get(t.partner_id) if t.partner_id else None,
                spend_cents=client_spend.get(t.id, 0),
                internal_cost_usd=_dec(cost),
                messages_inbound=inbound,
                messages_outbound=outbound,
                conversations=conversations,
            )
        )

    for pid, row in partner_rows.items():
        row.internal_cost_usd = _dec(partner_cost.get(pid, Decimal(0)))
        row.messages = partner_messages.get(pid, 0)

    total_spend = sum(r.spend_cents for r in partner_rows.values())
    total_cost = sum((Decimal(r.internal_cost_usd) for r in client_rows), Decimal(0))
    days_seen = sorted(set(daily_spend) | set(daily_cost) | set(daily_messages))
    return UsageOverviewOut(
        since=since,
        until=now,
        totals=UsageTotalsOut(
            spend_cents=total_spend,
            internal_cost_usd=_dec(total_cost),
            margin_usd=_dec(Decimal(total_spend) / 100 - total_cost),
            messages=sum(r.messages_inbound + r.messages_outbound for r in client_rows),
            conversations=sum(r.conversations for r in client_rows),
            active_clients=sum(
                1 for r in client_rows if r.messages_inbound + r.messages_outbound > 0
            ),
        ),
        partners=sorted(partner_rows.values(), key=lambda r: (-r.spend_cents, r.name)),
        clients=sorted(client_rows, key=lambda r: (-r.spend_cents, r.name)),
        daily=[
            DailyUsageOut(
                day=d,
                spend_cents=daily_spend.get(d, 0),
                internal_cost_usd=_dec(daily_cost.get(d, Decimal(0))),
                messages=daily_messages.get(d, 0),
            )
            for d in days_seen
        ],
        unreadable=UnreadableOut(partners=unreadable_partners, clients=unreadable_clients),
    )
