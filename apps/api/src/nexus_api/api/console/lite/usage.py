"""``/console/lite/usage/*`` — el Consumo de un solo cliente (spec 030, R5).

Las MISMAS funciones que el Consumo del partner (``api/console/usage.py``:
``spend_report``, ``bucket_report``, ``csv_export``) con el cliente de quien
entra como única fila. Lo que es del partner entero no aparece: su saldo, lo
gastado fuera de clientes, su tope de mensajes, sus alertas, y el Playground
(la prueba del partner, no consumo del cliente). Solo módulo ``usage``.

Estas rutas no usan ``lite_scope``: las lecturas del Consumo abren su propia
transacción de informes (``reporting_transaction``), y una transacción abierta
por el ámbito lo impediría. El cliente sale igual de la membresía verificada.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.client_auth import ClientPrincipal, require_client_principal
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Agent, AgentStatus, Channel, Conversation, PartnerTenant
from nexus_api.metering.wallet import AgentFilter, allocations_for, credit_burn
from nexus_api.services.console_home import REVIEW_WINDOW, tenant_snapshots
from nexus_api.services.console_reporting import month_bounds, partner_mappings
from nexus_api.services.lite_home import agent_spend, balance_of

from ..schemas import UsageBucketOut
from ..usage import bucket_report, csv_export, spend_report
from .home import LiteBalanceOut

router = APIRouter(prefix="/usage")
log = structlog.get_logger(__name__)


class LiteUsageMonthOut(BaseModel):
    spent_cents: int
    projection_cents: int | None
    conversations: int | None
    avg_per_conversation_cents: int | None


class AgentUsageOut(BaseModel):
    """Spec 030 (R5.3): one agent's month — only with more than one agent."""

    agent_id: uuid.UUID
    name: str
    conversations: int
    spent_cents: int
    share_pct: int


class LiteUsageSummaryOut(BaseModel):
    balance: LiteBalanceOut | None
    month: LiteUsageMonthOut | None
    by_agent: list[AgentUsageOut] | None = None
    errors: list[str]


class LiteSpendOut(BaseModel):
    currency: str
    days: list[date]
    series_cents: list[int]
    month_cents: int
    projected_cents: int


class LiteUsageDetailOut(BaseModel):
    since: datetime
    until: datetime
    buckets: list[UsageBucketOut]
    totals_by_meter: dict[str, float]
    total_records: int


async def _mapping(session: AsyncSession, principal: ClientPrincipal) -> PartnerTenant:
    mappings = await partner_mappings(session, principal.partner.id)
    for m in mappings:
        if m.tenant_id == principal.tenant_id:
            return m
    # La membresía garantiza el mapeo; si desaparece entre medias, no hay cliente.
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No client access")


@router.get("/summary", response_model=LiteUsageSummaryOut)
async def usage_summary(
    principal: ClientPrincipal = Depends(require_client_principal("usage")),
    session: AsyncSession = Depends(get_db_session),
) -> LiteUsageSummaryOut:
    now = datetime.now(UTC)
    since, _until, _e, _d = month_bounds(now)
    errors: list[str] = []
    tid = principal.tenant_id
    balance: LiteBalanceOut | None = None
    try:
        burn = await credit_burn(principal.partner.id, [tid], now - REVIEW_WINDOW)
        allocation = (await allocations_for(principal.partner.id, [tid])).get(tid)
        balance = LiteBalanceOut.model_validate(
            balance_of(allocation, burn.get(tid, 0)), from_attributes=True
        )
    except Exception as exc:
        log.warning("lite_usage.balance_failed", error=str(exc))
        errors.append("balance")
    month: LiteUsageMonthOut | None = None
    try:
        mapping = await _mapping(session, principal)
        spend = await spend_report(
            principal.partner.id, [mapping], {tid: mapping}, 7, whole_portfolio=False
        )
        snap = await tenant_snapshots([tid], month_start=since, now=now)
        snapshot = snap.snapshots.get(tid)
        conversations = snapshot.conversations_month if snapshot is not None else None
        nothing = spend.month_cents == 0 and spend.projected_cents == 0
        month = LiteUsageMonthOut(
            spent_cents=spend.month_cents,
            projection_cents=None if nothing else spend.projected_cents,
            conversations=conversations,
            avg_per_conversation_cents=(
                round(spend.month_cents / conversations) if conversations else None
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("lite_usage.month_failed", error=str(exc))
        errors.append("month")
    by_agent: list[AgentUsageOut] | None = None
    if month is not None:
        try:
            by_agent = await _usage_by_agent(principal, since=since, total_cents=month.spent_cents)
        except Exception as exc:
            log.warning("lite_usage.by_agent_failed", error=str(exc))
            errors.append("by_agent")
    return LiteUsageSummaryOut(balance=balance, month=month, by_agent=by_agent, errors=errors)


async def _usage_by_agent(
    principal: ClientPrincipal, *, since: datetime, total_cents: int
) -> list[AgentUsageOut] | None:
    """Spend split to the cent (``agent_spend``) plus the month's conversations
    on each agent's numbers — a number without an agent is the principal's.

    The route's session is not RLS-scoped (the reports open their own
    transactions), so these reads open one of the client's: RLS plus the
    tenant filter written out, not the filter alone."""
    sm = get_sessionmaker()
    async with sm() as scoped, tenant_scoped_session(scoped, principal.tenant_id):
        spend = await agent_spend(
            scoped,
            partner_id=principal.partner.id,
            tenant_id=principal.tenant_id,
            since=since,
            total_cents=total_cents,
        )
        if spend is None:
            return None
        principal_agent = spend[0].agent_id
        who = sa.func.coalesce(Channel.agent_id, principal_agent)
        rows = (
            await scoped.execute(
                sa.select(who, sa.func.count(Conversation.id))
                .join(Channel, Channel.id == Conversation.channel_id)
                .where(
                    Conversation.tenant_id == principal.tenant_id,
                    Conversation.created_at >= since,
                    Channel.provider != "qa_playground",
                )
                .group_by(who)
            )
        ).all()
    counts: dict[uuid.UUID, int] = {agent: int(n) for agent, n in rows}
    return [
        AgentUsageOut(
            agent_id=s.agent_id,
            name=s.name,
            conversations=int(counts.get(s.agent_id, 0)),
            spent_cents=s.cents,
            share_pct=round(100 * s.cents / total_cents) if total_cents else 0,
        )
        for s in spend
    ]


async def _agent_filter(principal: ClientPrincipal, agent: uuid.UUID) -> AgentFilter:
    """One of the client's active agents, or 404 — never another client's.
    Read in a session of the client's (RLS) with the tenant written out too:
    the route's own session is not RLS-scoped."""
    sm = get_sessionmaker()
    async with sm() as scoped, tenant_scoped_session(scoped, principal.tenant_id):
        ids = list(
            (
                await scoped.execute(
                    sa.select(Agent.id)
                    .where(
                        Agent.tenant_id == principal.tenant_id,
                        Agent.status == AgentStatus.ACTIVE.value,
                    )
                    .order_by(Agent.created_at, Agent.id)
                )
            ).scalars()
        )
    if agent not in ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent")
    return AgentFilter(agent_id=agent, is_principal=agent == ids[0])


@router.get(
    "/spend", response_model=LiteSpendOut, responses={404: {"description": "Unknown agent"}}
)
async def usage_spend(
    principal: ClientPrincipal = Depends(require_client_principal("usage")),
    session: AsyncSession = Depends(get_db_session),
    days: int = Query(default=30, ge=1, le=90),
    agent: uuid.UUID | None = Query(default=None, description="Only this agent (spec 030)"),
) -> LiteSpendOut:
    mapping = await _mapping(session, principal)
    report = await spend_report(
        principal.partner.id,
        [mapping],
        {principal.tenant_id: mapping},
        days,
        whole_portfolio=False,
        agent=await _agent_filter(principal, agent) if agent is not None else None,
    )
    return LiteSpendOut(
        currency=report.currency,
        days=report.days,
        series_cents=report.series_cents,
        month_cents=report.month_cents,
        projected_cents=report.projected_cents,
    )


@router.get("/detail", response_model=LiteUsageDetailOut)
async def usage_detail(
    principal: ClientPrincipal = Depends(require_client_principal("usage")),
    session: AsyncSession = Depends(get_db_session),
    days: int = Query(default=30, ge=1, le=366),
) -> LiteUsageDetailOut:
    until = datetime.now(UTC)
    since = until - timedelta(days=days)
    mapping = await _mapping(session, principal)
    buckets, totals, records, _unpriced = await bucket_report(
        session, {principal.tenant_id: mapping}, since, until, source="channel"
    )
    return LiteUsageDetailOut(
        since=since, until=until, buckets=buckets, totals_by_meter=totals, total_records=records
    )


@router.get("/export.csv", response_class=StreamingResponse)
async def usage_export(
    principal: ClientPrincipal = Depends(require_client_principal("usage")),
    session: AsyncSession = Depends(get_db_session),
    days: int = Query(default=30, ge=1, le=366),
    lang: str = Query(default="es", pattern="^(es|en)$"),
) -> StreamingResponse:
    mapping = await _mapping(session, principal)
    by_tenant: dict[uuid.UUID, PartnerTenant] = {principal.tenant_id: mapping}
    return csv_export(session, by_tenant, days, source="channel", lang=lang)
