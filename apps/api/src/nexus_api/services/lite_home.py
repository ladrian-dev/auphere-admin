"""El Panel de un solo cliente — spec 030 (Requisito 4, plan D8 a D10).

Calcula con **las mismas funciones** que el Inicio del partner
(``api/console/home.py``): ``tenant_snapshots``, ``trend_block``,
``review_block``, ``credit_burn``, ``allocations_for`` y ``spend_block``, con
una lista de clientes de un solo elemento. Por eso cada cifra coincide al
céntimo con la que el partner ve de ese cliente (CE-003), y una corrección en
el Inicio del partner llega aquí sin que nadie se acuerde.

Lo que es del partner entero —su saldo, lo gastado fuera de clientes, sus
alertas— no se calcula para el cliente: del libro solo se toman las filas de
SU tenant (``credit_burn`` devuelve también la clave ``None`` del Companion).

Cada bloque que falla se anota en ``errors`` y sale ``None``: el Panel lo dice
y pinta el resto (constitución §V). Nunca un cero donde no se sabe.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.billing.pricing import credits_to_cents
from nexus_api.db.models import Agent, AgentStatus, TenantStatus
from nexus_api.metering.wallet import (
    allocations_for,
    credit_burn,
    credit_burn_by_agent,
    read_wallet,
)
from nexus_api.services import inbox_view
from nexus_api.services.console_home import REVIEW_WINDOW, tenant_snapshots
from nexus_api.services.console_home_blocks import (
    SHOWN_DAYS,
    ClientRow,
    days_until,
    spend_block,
    trend_block,
)
from nexus_api.services.console_reporting import month_bounds

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class DayCount:
    day: date
    count: int


@dataclass(frozen=True)
class LiteConversations:
    last_7d: int
    prev_7d: int | None
    daily: list[DayCount]


@dataclass(frozen=True)
class LiteSpendMonth:
    total_cents: int
    by_agent: list[AgentSpend] | None = None


@dataclass(frozen=True)
class LiteWaiting:
    count: int
    first_conversation_id: uuid.UUID | None


@dataclass(frozen=True)
class LiteBalance:
    assigned: bool
    remaining_cents: int | None
    cap_cents: int | None
    days_left: float | None
    #: Spec 047: la bolsa va en la moneda del cliente (EUR o USD).
    currency: str = "USD"
    #: Spec 047 (``events.md`` §1.4): ``ok``, ``low``, ``not_enough`` o ``empty``;
    #: ``None`` sin bolsa (o con las asignaciones de antes).
    state: str | None = None


def balance_horizon(
    balance: LiteBalance, *, tz_name: str | None, now: datetime
) -> tuple[int, date | None]:
    """Spec 045 (R4): ``(month_days_left, runs_out_on)`` en la zona del negocio.

    ``month_days_left`` son los días del mes que quedan, hoy incluido.
    ``runs_out_on`` es hoy más los días enteros que dura el saldo al ritmo de
    los últimos 7 días; ``None`` sin gasto o sin saldo asignado. Con el saldo
    agotado, hoy."""
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
    today = now.astimezone(tz).date()
    next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_days_left = (next_month - today).days
    if not balance.assigned or balance.days_left is None:
        return month_days_left, None
    if (balance.remaining_cents or 0) <= 0:
        return month_days_left, today
    return month_days_left, today + timedelta(days=int(balance.days_left))


@dataclass(frozen=True)
class LiteAttention:
    kind: str  # waiting | balance_out | balance_low
    count: int | None = None
    days_left: float | None = None


@dataclass
class LiteHome:
    spend_month: LiteSpendMonth | None = None
    conversations: LiteConversations | None = None
    waiting: LiteWaiting | None = None
    balance: LiteBalance | None = None
    attention: list[LiteAttention] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def balance_of(
    allocation: tuple[int, int] | None, burn_7d: int, purchased: int | None = None
) -> LiteBalance:
    """El saldo del cliente: lo que le queda de su tope y para cuántos días
    alcanza al ritmo de los últimos 7 días — la misma cuenta que
    ``credit_block`` hace por cliente para el riesgo.

    Spec 033 (R6.2): **nunca más que el dinero que existe**. El tope es un
    límite de gasto, no una reserva: si al partner le quedan US$ 5 de saldo
    recargado, el cliente no puede gastar más de US$ 5 aunque su tope diga
    30. ``purchased`` es ese saldo; ``None`` = no se pudo leer, y entonces se
    pinta el tope tal cual (el error de lectura lo marca quien llama)."""
    if allocation is None:
        return LiteBalance(assigned=False, remaining_cents=None, cap_cents=None, days_left=None)
    cap, remaining = allocation
    if purchased is not None:
        remaining = max(0, min(remaining, purchased))
    daily = burn_7d / SHOWN_DAYS
    days = round(remaining / daily, 1) if (daily > 0 and remaining > 0) else None
    return LiteBalance(
        assigned=True,
        remaining_cents=credits_to_cents(remaining),
        cap_cents=credits_to_cents(cap),
        days_left=0.0 if (remaining <= 0 and daily > 0) else days,
    )


async def bag_balance(
    partner_id: uuid.UUID, tenant_id: uuid.UUID, now: datetime
) -> LiteBalance | None:
    """Spec 047 (46.7): con bolsas, el saldo del cliente es su bolsa, igual que en
    la consola del partner (``client_overview``); ``None`` si el partner sigue con
    ``partner_allocations``."""
    from nexus_api.core.partner_context import apply_partner_to_session
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import ClientWallet
    from nexus_api.services.wallet import alerts as wallet_alerts
    from nexus_api.services.wallet.bags import as_client, bags_active

    async with get_sessionmaker()() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        if not await bags_active(session, partner_id):
            return None
        await as_client(session, tenant_id)
        bag = await session.get(ClientWallet, tenant_id)
        if bag is None or not (bag.balance_micros or bag.month_base_micros):
            return LiteBalance(
                assigned=False,
                remaining_cents=None,
                cap_cents=None,
                days_left=None,
                currency=bag.currency if bag else "USD",
                state="empty" if bag is not None else None,
            )
        pace = await wallet_alerts.pace_per_day(session, bag, now.date())
        left = wallet_alerts.days_left(bag.balance_micros, pace)
        return LiteBalance(
            assigned=True,
            remaining_cents=credits_to_cents(bag.balance_micros),
            cap_cents=credits_to_cents(bag.month_base_micros),
            days_left=0.0 if bag.balance_micros <= 0 else (None if left is None else float(left)),
            currency=bag.currency,
            state=await wallet_alerts.bag_state(session, bag, now.date()),
        )


@dataclass(frozen=True)
class AgentSpend:
    agent_id: uuid.UUID
    name: str
    cents: int
    credits: int


def split_cents(total_cents: int, credits: list[int]) -> list[int]:
    """``total_cents`` shared in proportion to ``credits``, by largest
    remainder, so the parts add up to the total **to the cent** — the total is
    what the client reads above the breakdown, and a sum that does not match
    it is a screen that lies (§V)."""
    whole = sum(credits)
    if whole <= 0 or total_cents <= 0:
        return [0 for _ in credits]
    exact = [total_cents * c / whole for c in credits]
    parts = [int(x) for x in exact]
    left = total_cents - sum(parts)
    order = sorted(range(len(credits)), key=lambda i: exact[i] - parts[i], reverse=True)
    for i in order[:left]:
        parts[i] += 1
    return parts


async def agent_spend(
    session: AsyncSession,
    *,
    partner_id: uuid.UUID,
    tenant_id: uuid.UUID,
    since: datetime,
    total_cents: int,
) -> list[AgentSpend] | None:
    """Spec 030 (R4.2, R5.3): the month's spend per agent, or ``None`` with a
    single agent — a one-row breakdown says nothing. What was spent before
    agents existed is the principal's; an archived agent appears only if it
    spent something."""
    agents = (
        await session.execute(
            sa.select(Agent.id, Agent.name, Agent.status)
            .where(Agent.tenant_id == tenant_id)
            .order_by(Agent.created_at, Agent.id)
        )
    ).all()
    active = [a for a in agents if a.status == AgentStatus.ACTIVE.value]
    if len(active) < 2:
        return None
    burn = await credit_burn_by_agent(partner_id, tenant_id, since)
    principal = active[0].id
    rows = [
        (a.id, a.name, burn.get(a.id, 0) + (burn.get(None, 0) if a.id == principal else 0))
        for a in agents
        if a.status == AgentStatus.ACTIVE.value or burn.get(a.id, 0) > 0
    ]
    cents = split_cents(total_cents, [c for _i, _n, c in rows])
    return [
        AgentSpend(agent_id=i, name=str(n), cents=cents[k], credits=c)
        for k, (i, n, c) in enumerate(rows)
    ]


def balance_notice(balance: LiteBalance, days_to_month_end: float) -> str | None:
    """«Necesita tu atención» sobre el saldo: ``balance_out`` (agotado),
    ``balance_low`` (al ritmo de los últimos 7 días no llega a fin de mes) o
    nada. **Una sola regla** para el Panel y para la campana del cliente
    (``wallet_alerts.evaluate_client_balance_alerts``): si dijeran cosas
    distintas, una de las dos mentiría (§V)."""
    if not balance.assigned:
        return None
    if (balance.remaining_cents or 0) <= 0:
        return "balance_out"
    if balance.days_left is not None and balance.days_left < days_to_month_end:
        return "balance_low"
    return None


async def lite_home(
    session: AsyncSession,
    *,
    partner_id: uuid.UUID,
    tenant_id: uuid.UUID,
    client_ref: str,
    client_name: str,
    tenant_status: TenantStatus,
    with_inbox: bool,
    now: datetime | None = None,
) -> LiteHome:
    now = now or datetime.now(UTC)
    since, until, _elapsed, _days = month_bounds(now)
    out = LiteHome()
    row = ClientRow(tenant_id, client_ref, client_name, tenant_status)

    # ── conversaciones y lo que espera (snapshot del cliente) ─────────
    try:
        snap = await tenant_snapshots([tenant_id], month_start=since, now=now)
        if snap.failed:
            raise RuntimeError("snapshot failed")
        trend = trend_block([row], snap.snapshots, now.date())
        out.conversations = LiteConversations(
            last_7d=trend.current,
            prev_7d=trend.previous,
            daily=[DayCount(d, n) for d, n in zip(trend.days, trend.series, strict=True)],
        )
    except Exception as exc:
        log.warning("lite_home.snapshot_failed", error=str(exc))
        out.errors.append("conversations")

    # ── lo que espera a una persona: el número de la Bandeja (spec 045) ──
    if with_inbox:
        try:
            _unread, waiting = await inbox_view.counts(session, me="")
            out.waiting = LiteWaiting(
                count=waiting,
                first_conversation_id=await inbox_view.first_waiting(session) if waiting else None,
            )
        except Exception as exc:
            log.warning("lite_home.waiting_failed", error=str(exc))
            out.errors.append("conversations")

    # ── saldo y gasto (libro del partner, solo las filas del cliente) ──
    burn_7d = 0
    try:
        burn = await credit_burn(partner_id, [tenant_id], now - REVIEW_WINDOW)
        burn_7d = burn.get(tenant_id, 0)
        from_bag = await bag_balance(partner_id, tenant_id, now)
        if from_bag is not None:
            out.balance = from_bag
        else:
            allocation = (await allocations_for(partner_id, [tenant_id])).get(tenant_id)
            wallet = await read_wallet(partner_id)
            if wallet is None:
                raise RuntimeError("wallet unreadable")
            out.balance = balance_of(allocation, burn_7d, wallet.purchased_remaining)
    except Exception as exc:
        log.warning("lite_home.balance_failed", error=str(exc))
        out.errors.append("balance")
    try:
        month_burn = await credit_burn(partner_id, [tenant_id], since)
        prev_start = (since - timedelta(days=1)).replace(day=1)
        prev = await credit_burn(partner_id, [tenant_id], prev_start, prev_start + (now - since))
        block = spend_block(
            [row],
            {tenant_id: month_burn.get(tenant_id, 0)},
            prev.get(tenant_id, 0),
            daily_7d=burn_7d / REVIEW_WINDOW.days,
            days_left=days_until(until, now),
        )
        out.spend_month = LiteSpendMonth(
            total_cents=block.cents,
            by_agent=await agent_spend(
                session,
                partner_id=partner_id,
                tenant_id=tenant_id,
                since=since,
                total_cents=block.cents,
            ),
        )
    except Exception as exc:
        log.warning("lite_home.spend_failed", error=str(exc))
        out.errors.append("spend")

    # ── necesita tu atención ──────────────────────────────────────────
    if out.waiting is not None and out.waiting.count > 0:
        out.attention.append(LiteAttention(kind="waiting", count=out.waiting.count))
    balance = out.balance
    notice = balance_notice(balance, days_until(until, now)) if balance is not None else None
    if notice == "balance_out":
        out.attention.append(LiteAttention(kind="balance_out"))
    elif notice == "balance_low" and balance is not None:
        out.attention.append(LiteAttention(kind="balance_low", days_left=balance.days_left))
    return out


__all__ = [
    "AgentSpend",
    "LiteHome",
    "agent_spend",
    "bag_balance",
    "balance_notice",
    "balance_of",
    "lite_home",
    "split_cents",
]
