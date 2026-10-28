"""Consumo por partidas — spec 047, T158 (requisito 46; ``contracts/console-api.md``
§7).

- ``GET /console/usage/summary?period=month``: las tres cifras de arriba («Saldo
  disponible» sin el pool, «En bolsas de clientes» con «aprox.» si hay otra
  moneda, «Gasto del mes» con su proyección a 7 días), las cuatro partidas con
  quién las paga y la tabla por cliente (46.1, 46.2, 46.4).
- ``GET /console/usage/daily?days=7|30|90&client=&line=``: el gasto por día, por
  partida (46.3).
- ``GET /console/usage/detail?days=&client=``: los medidores por cliente, agente,
  partida y origen, con lo que aún no tiene precio (46.6). El CSV es
  ``/console/usage/export.csv``.

Todas las cifras salen de ``services/wallet/usage_lines.py``: la misma cifra en
todas partes (46.7). Dinero: ``{amount_micros, currency}`` en cien milésimas de la
moneda de la cuenta.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import ClientWallet, UsageRecord
from nexus_api.db.models.usage_record import USAGE_LINE_BY_SOURCE
from nexus_api.services.console_reporting import (
    month_bounds,
    partner_mappings,
    reporting_transaction,
)
from nexus_api.services.wallet import alerts as wallet_alerts
from nexus_api.services.wallet import bags, build_budget
from nexus_api.services.wallet.usage_lines import LINES, PAYER, Line, Payer, balances, spend

from .client_bags import Money, _money
from .usage import _scope

router = APIRouter(prefix="/usage")


class LineOut(BaseModel):
    line: Line
    amount: Money
    payer: Payer
    approx: bool
    #: Solo «Construcción y pruebas»: su tope del mes y su estado.
    cap: Money | None = None
    state: Literal["ok", "warning", "exhausted"] | None = None


class ClientUsageOut(BaseModel):
    ref: str
    name: str | None
    bag: Money | None
    month_spent: Money
    days_left: int | None
    refill_up_to: Money | None
    #: «Sin saldo» en rojo, con «Asignar saldo» (46.2).
    empty: bool


class UsageSummaryOut(BaseModel):
    currency: str
    since: datetime
    until: datetime
    available: Money
    in_bags: Money
    in_bags_approx: bool
    month_spend: Money
    projected: Money
    lines: list[LineOut]
    clients: list[ClientUsageOut]


class UsageDailyOut(BaseModel):
    currency: str
    days: list[date]
    lines: list[Line]
    #: Por partida, un importe por día (cien milésimas, moneda de la cuenta).
    series: dict[str, list[int]]
    total: list[int]
    approx_lines: list[Line]


class DetailRowOut(BaseModel):
    ref: str
    agent_id: uuid.UUID | None
    agent_name: str | None = None
    meter: str
    line: str | None
    source: str
    quantity: float
    billable_qty: float
    records: int
    unpriced: int


class UsageDetailOut(BaseModel):
    since: datetime
    until: datetime
    rows: list[DetailRowOut]


#: Lo que el partner paga de su dinero: el gasto del mes (46.1).
_PARTNER_PAYS = ("conversations", "companion")


@router.get("/summary", response_model=UsageSummaryOut)
async def usage_summary(
    principal: ConsolePrincipal = Depends(require_console_principal("usage:read")),
    session: AsyncSession = Depends(get_db_session),
    period: Literal["month"] = Query(default="month"),
) -> UsageSummaryOut:
    partner_id = principal.partner.id
    mappings = await partner_mappings(session, partner_id)
    now = datetime.now(UTC)
    since, until, elapsed, days_in_month = month_bounds(now)
    week_ago = (now - timedelta(days=7)).date()
    window = min(since, datetime.combine(week_ago, time.min, UTC))
    tenant_ids = [m.tenant_id for m in mappings]
    lines = await spend(
        session,
        partner_id=partner_id,
        tenant_ids=tenant_ids,
        since=window,
        until=now,
        with_outside=True,
    )
    currency = lines.currency
    month_day = since.date()

    figures = await balances(partner_id)
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        build = await build_budget.read(s, partner_id)
        clients: list[ClientUsageOut] = []
        today = now.date()
        for m in mappings:
            # La bolsa es del cliente: se lee con su contexto puesto.
            await bags.as_client(s, m.tenant_id)
            bag = await s.get(ClientWallet, m.tenant_id)
            days_left = None
            if bag is not None:
                pace = await wallet_alerts.pace_per_day(s, bag, today)
                days_left = wallet_alerts.days_left(bag.balance_micros, pace)
            clients.append(
                ClientUsageOut(
                    ref=m.external_client_ref,
                    name=m.client_name,
                    bag=_money(bag.balance_micros, bag.currency) if bag is not None else None,
                    month_spent=_money(
                        lines.total(lines=("conversations",), tenant=m.tenant_id, since=month_day),
                        currency,
                    ),
                    days_left=days_left,
                    refill_up_to=_money(bag.refill_up_to_micros, bag.currency)
                    if bag is not None and bag.refill_up_to_micros
                    else None,
                    empty=bag is None or bag.balance_micros <= 0,
                )
            )

    month_spend = lines.total(lines=_PARTNER_PAYS, since=month_day)
    pace7 = lines.total(lines=_PARTNER_PAYS, since=week_ago) / 7
    projected = month_spend + int(pace7 * max(0, days_in_month - elapsed))
    out_lines: list[LineOut] = []
    for line in LINES:
        amount = lines.total(lines=(line,), since=month_day)
        extra: dict[str, object] = {}
        if line == "build":
            # El mes en curso de la partida es el que frena: la misma cifra.
            amount = build.spent_micros
            extra = {"cap": _money(build.cap_micros, currency), "state": build.state}
        out_lines.append(
            LineOut(
                line=line,
                amount=_money(amount, currency),
                payer=PAYER[line],
                approx=line in lines.approx_lines,
                **extra,  # type: ignore[arg-type]
            )
        )
    return UsageSummaryOut(
        currency=currency,
        since=since,
        until=until,
        available=_money(figures.available, currency),
        in_bags=_money(figures.in_bags, currency),
        in_bags_approx=figures.approx,
        month_spend=_money(month_spend, currency),
        projected=_money(projected, currency),
        lines=out_lines,
        clients=clients,
    )


@router.get("/daily", response_model=UsageDailyOut)
async def usage_daily(
    principal: ConsolePrincipal = Depends(require_console_principal("usage:read")),
    session: AsyncSession = Depends(get_db_session),
    days: int = Query(default=30, description="7, 30 o 90"),
    client: str | None = Query(default=None, max_length=255),
    line: Line | None = Query(default=None),
) -> UsageDailyOut:
    if days not in (7, 30, 90):
        raise HTTPException(status_code=422, detail={"code": "days_7_30_or_90"})
    mappings = await partner_mappings(session, principal.partner.id)
    _chosen, by_tenant = _scope(mappings, client)
    today = datetime.now(UTC).date()
    day_list = [today - timedelta(days=days - 1 - i) for i in range(days)]
    chosen_lines: tuple[Line, ...] = (line,) if line is not None else LINES
    result = await spend(
        session,
        partner_id=principal.partner.id,
        tenant_ids=list(by_tenant),
        since=datetime.combine(day_list[0], time.min, UTC),
        until=datetime.now(UTC),
        with_outside=client is None,
        lines=chosen_lines,
    )
    index = {d: i for i, d in enumerate(day_list)}
    series: dict[str, list[int]] = {name: [0] * days for name in chosen_lines}
    for (d, name, _tid), amount in result.cells.items():
        if d in index and name in series:
            series[name][index[d]] += amount
    return UsageDailyOut(
        currency=result.currency,
        days=day_list,
        lines=list(chosen_lines),
        series=series,
        total=[sum(values[i] for values in series.values()) for i in range(days)],
        approx_lines=sorted(result.approx_lines & set(chosen_lines)),  # type: ignore[arg-type]
    )


@router.get("/detail", response_model=UsageDetailOut)
async def usage_detail(
    principal: ConsolePrincipal = Depends(require_console_principal("usage:read")),
    session: AsyncSession = Depends(get_db_session),
    days: int = Query(default=30, ge=1, le=366),
    client: str | None = Query(default=None, max_length=255),
) -> UsageDetailOut:
    """Los medidores, plegados en la pantalla: por cliente, agente, partida y
    origen. ``unpriced`` cuenta lo medido que aún no tiene precio."""
    mappings = await partner_mappings(session, principal.partner.id)
    _chosen, by_tenant = _scope(mappings, client)
    until = datetime.now(UTC)
    since = until - timedelta(days=days)
    rows: list[DetailRowOut] = []
    if by_tenant:
        stmt = (
            sa.select(
                UsageRecord.tenant_id,
                UsageRecord.agent_id,
                UsageRecord.meter,
                UsageRecord.line,
                UsageRecord.source,
                sa.func.coalesce(sa.func.sum(UsageRecord.quantity), 0),
                sa.func.coalesce(sa.func.sum(UsageRecord.billable_qty), 0),
                sa.func.count(),
                sa.func.count().filter(UsageRecord.cost_usd.is_(None)),
            )
            .where(
                UsageRecord.tenant_id.in_(list(by_tenant)),
                UsageRecord.occurred_at >= since,
                UsageRecord.occurred_at < until,
            )
            .group_by(
                UsageRecord.tenant_id,
                UsageRecord.agent_id,
                UsageRecord.meter,
                UsageRecord.line,
                UsageRecord.source,
            )
        )
        async with reporting_transaction(session):
            found = (await session.execute(stmt)).all()
        for tid, agent_id, meter, line, source, qty, billable, count, unpriced in found:
            rows.append(
                DetailRowOut(
                    ref=by_tenant[tid].external_client_ref,
                    agent_id=agent_id,
                    meter=str(meter),
                    line=line or USAGE_LINE_BY_SOURCE.get(str(source)),
                    source=str(source),
                    quantity=float(qty),
                    billable_qty=float(billable),
                    records=int(count),
                    unpriced=int(unpriced),
                )
            )
        rows.sort(key=lambda r: (r.ref, r.line or "", r.meter, r.source, str(r.agent_id)))
        names = await _agent_names({tid for tid, *_rest in found if _rest[0] is not None})
        for row in rows:
            row.agent_name = names.get(row.agent_id) if row.agent_id else None
    return UsageDetailOut(since=since, until=until, rows=rows)


async def _agent_names(tenant_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """El nombre de los agentes que salen en el detalle: cada cliente con su RLS."""
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.models import Agent

    out: dict[uuid.UUID, str] = {}
    for tenant_id in tenant_ids:
        async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
            for agent_id, name in (
                await session.execute(
                    sa.select(Agent.id, Agent.name).where(Agent.tenant_id == tenant_id)
                )
            ).all():
                out[agent_id] = str(name)
    return out
