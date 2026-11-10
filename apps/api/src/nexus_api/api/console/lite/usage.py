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
from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.billing.pricing import credits_to_cents
from nexus_api.config import get_settings
from nexus_api.core.client_auth import ClientPrincipal, require_client_principal
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Agent,
    AgentStatus,
    Channel,
    Conversation,
    PartnerTenant,
    Tenant,
    TenantStatus,
)
from nexus_api.metering.wallet import AgentFilter, allocations_for, credit_burn, read_wallet
from nexus_api.services.console_home import REVIEW_WINDOW, tenant_snapshots
from nexus_api.services.console_home_blocks import ClientRow, SpendBlock, days_until, spend_block
from nexus_api.services.console_reporting import month_bounds, partner_mappings
from nexus_api.services.lite_home import agent_spend, bag_balance, balance_of
from nexus_api.services.wallet.bags import AgentKey, BagSpend, bag_spend

from ..schemas import UsageBucketOut
from ..usage import bucket_report, csv_export, spend_report
from .home import LiteBalanceOut, balance_out

router = APIRouter(prefix="/usage")
log = structlog.get_logger(__name__)


class LiteUsageMonthOut(BaseModel):
    spent_cents: int
    projection_cents: int | None
    conversations: int | None
    avg_per_conversation_cents: int | None
    #: Spec 047: con bolsas, la moneda de la bolsa (EUR o USD); sin ellas, USD.
    currency: str = "USD"


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
    #: Spec 047 (``lite-app-api.md`` §4, ``events.md`` §1.4): ``ok``, ``low``,
    #: ``not_enough`` o ``empty``; ``None`` sin bolsa.
    bag_state: str | None = None
    #: Días que alcanza al ritmo de los últimos 7; ``None`` con menos de 3 días
    #: de consumo («Aún no hay datos para estimarlo»).
    days_left: int | None = None
    #: A quién pedir saldo: «Pídeselo a {partner}».
    partner_name: str = ""


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


def _of_agent(agent: AgentFilter, key: AgentKey) -> bool:
    """The bag's charges of one agent: the principal also owns those without one,
    like :meth:`AgentFilter.clause` in the account's ledger."""
    return key == agent.agent_id or (agent.is_principal and key is None)


def _bag_month(
    found: BagSpend,
    mapping: PartnerTenant,
    *,
    since: datetime,
    until: datetime,
    now: datetime,
    agent: AgentFilter | None = None,
) -> SpendBlock:
    """Spec 047 (46.7): the month of the bag with the partner's sums
    (``spend_block``): what the bag spent this month —the partner's figure— or,
    for one agent, its charges this month; projected at the last 7 days' pace."""
    if agent is None:
        month, recent = found.month, sum(found.last_7d.values())
    else:
        month = sum(v for k, v in found.by_agent(since.date()).items() if _of_agent(agent, k))
        recent = sum(v for k, v in found.last_7d.items() if _of_agent(agent, k))
    row = ClientRow(
        mapping.tenant_id, mapping.external_client_ref, mapping.client_name, TenantStatus.ACTIVE
    )
    return spend_block(
        [row],
        {mapping.tenant_id: month},
        0,
        daily_7d=recent / REVIEW_WINDOW.days,
        days_left=days_until(until, now),
    )


@router.get("/summary", response_model=LiteUsageSummaryOut)
async def usage_summary(
    principal: ClientPrincipal = Depends(require_client_principal("usage")),
    session: AsyncSession = Depends(get_db_session),
) -> LiteUsageSummaryOut:
    now = datetime.now(UTC)
    since, until, _e, _d = month_bounds(now)
    errors: list[str] = []
    tid = principal.tenant_id
    balance: LiteBalanceOut | None = None
    bag_state: str | None = None
    days_left: int | None = None
    try:
        # Spec 047 (46.7): con bolsas, la misma cifra que la consola del partner.
        raw = await bag_balance(principal.partner.id, tid, now)
        if raw is None:
            burn = await credit_burn(principal.partner.id, [tid], now - REVIEW_WINDOW)
            allocation = (await allocations_for(principal.partner.id, [tid])).get(tid)
            wallet = await read_wallet(principal.partner.id)
            if wallet is None:
                raise RuntimeError("wallet unreadable")
            raw = balance_of(allocation, burn.get(tid, 0), wallet.purchased_remaining)
        # La zona del negocio, en una lectura propia: esta ruta abre sus
        # transacciones más abajo y la sesión de la petición no puede empezar una.
        async with get_sessionmaker()() as tz_session:
            tenant = await tz_session.get(Tenant, tid)
        balance = balance_out(raw, tz_name=tenant.timezone if tenant is not None else None, now=now)
        bag_state = raw.state
        days_left = int(raw.days_left) if raw.days_left is not None else None
    except Exception as exc:
        log.warning("lite_usage.balance_failed", error=str(exc))
        errors.append("balance")
    month: LiteUsageMonthOut | None = None
    agent_burn: Mapping[AgentKey, int] | None = None
    try:
        mapping = await _mapping(session, principal)
        # Spec 047 (46.7): con bolsas el turno se cobra solo de la bolsa y el libro
        # de la cuenta no lo ve (bug ``gasto-del-mes-a-cero-con-bolsas``).
        from_bag = await bag_spend(principal.partner.id, tid, since=since, now=now)
        if from_bag is not None:
            block = _bag_month(from_bag, mapping, since=since, until=until, now=now)
            spent, projected, currency = block.cents, block.projected_cents, from_bag.currency
            agent_burn = from_bag.by_agent(since.date())
        else:
            spend = await spend_report(
                principal.partner.id, [mapping], {tid: mapping}, 7, whole_portfolio=False
            )
            spent, projected, currency = spend.month_cents, spend.projected_cents, spend.currency
        snap = await tenant_snapshots([tid], month_start=since, now=now)
        snapshot = snap.snapshots.get(tid)
        conversations = snapshot.conversations_month if snapshot is not None else None
        nothing = spent == 0 and projected == 0
        month = LiteUsageMonthOut(
            spent_cents=spent,
            projection_cents=None if nothing else projected,
            conversations=conversations,
            avg_per_conversation_cents=(round(spent / conversations) if conversations else None),
            currency=currency,
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("lite_usage.month_failed", error=str(exc))
        errors.append("month")
    by_agent: list[AgentUsageOut] | None = None
    if month is not None:
        try:
            by_agent = await _usage_by_agent(
                principal, since=since, total_cents=month.spent_cents, burn=agent_burn
            )
        except Exception as exc:
            log.warning("lite_usage.by_agent_failed", error=str(exc))
            errors.append("by_agent")
    return LiteUsageSummaryOut(
        balance=balance,
        month=month,
        by_agent=by_agent,
        errors=errors,
        bag_state=bag_state,
        days_left=days_left,
        partner_name=_ask_whom(principal),
    )


def _ask_whom(principal: ClientPrincipal) -> str:
    """«Pídeselo a {partner}» (sin botón de pedir: specs 031 R4.4 y 044 R13.4).
    El cliente de Auphere se lo pide a Auphere, como en ``/me``."""
    partner = principal.partner
    if partner.slug in get_settings().auphere_partner_slug_set:
        return "Auphere"
    return partner.name


async def _usage_by_agent(
    principal: ClientPrincipal,
    *,
    since: datetime,
    total_cents: int,
    burn: Mapping[AgentKey, int] | None = None,
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
            burn=burn,
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
    chosen = await _agent_filter(principal, agent) if agent is not None else None
    now = datetime.now(UTC)
    day_list = [now.date() - timedelta(days=days - 1 - i) for i in range(days)]
    month_start, until, _elapsed, _days = month_bounds(now)
    # Spec 047 (46.7): con bolsas, los cobros de la bolsa por día, en su moneda.
    from_bag = await bag_spend(
        principal.partner.id,
        principal.tenant_id,
        since=min(datetime.combine(day_list[0], time.min, tzinfo=UTC), month_start),
        now=now,
    )
    if from_bag is not None:
        per_day = dict.fromkeys(day_list, 0)
        for (day, key), amount in from_bag.cells.items():
            if day in per_day and (chosen is None or _of_agent(chosen, key)):
                per_day[day] += amount
        block = _bag_month(from_bag, mapping, since=month_start, until=until, now=now, agent=chosen)
        return LiteSpendOut(
            currency=from_bag.currency,
            days=day_list,
            series_cents=[credits_to_cents(per_day[d], nearest=True) for d in day_list],
            month_cents=block.cents,
            projected_cents=block.projected_cents,
        )
    report = await spend_report(
        principal.partner.id,
        [mapping],
        {principal.tenant_id: mapping},
        days,
        whole_portfolio=False,
        agent=chosen,
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
