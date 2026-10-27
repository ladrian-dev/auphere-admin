"""Spec 026: the home page blocks, built from data already read.

Pure functions: they take the per-client snapshots, the partner's client
rows, the quota state, the credit burn and the template rejections, and
return the response blocks. No database here, so every rule (severity
order, where each problem is fixed, how a trend compares, when credit is
«at risk») is pinned by plain unit tests.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from nexus_api.billing.pricing import CURRENCY, credits_to_cents
from nexus_api.db.models import TenantStatus
from nexus_api.services.console_home import TenantSnapshot

#: D1 — lower is worse: first what leaves the agent unable to answer.
SEVERITY: dict[str, int] = {
    "out_of_quota": 1,
    "no_active_agent": 2,
    "whatsapp_disconnected": 3,
    "needs_reauth": 3,
    "quality_red": 4,
    "failed_messages": 5,
    # Spec 026 (owner, 2026-10-03): running out of balance this month is a
    # warning in «Necesita tu atención», not a block of its own.
    "credit_low": 6,
    "template_rejected": 6,
    "draft_unpublished": 7,
    "provisioning": 8,
}

#: Clients drawn on their own in the daily chart; the rest go together.
TOP_CLIENTS = 5
SHOWN_DAYS = 7


@dataclass(frozen=True)
class ClientRow:
    tenant_id: uuid.UUID
    ref: str
    name: str | None
    status: TenantStatus


@dataclass(frozen=True)
class AttentionItem:
    kind: str
    severity: int
    external_client_ref: str
    client_name: str | None
    count: int | None
    href: str


@dataclass(frozen=True)
class ReviewClient:
    external_client_ref: str
    client_name: str | None
    escalated: int
    payments: int
    unanswered: int
    href: str


@dataclass(frozen=True)
class ReviewBlock:
    escalated: int
    payments: int
    unanswered: int
    clients: list[ReviewClient]


@dataclass(frozen=True)
class TrendClient:
    external_client_ref: str | None
    client_name: str | None
    series: list[int]


@dataclass(frozen=True)
class TrendBlock:
    days: list[date]
    series: list[int]
    current: int
    previous: int | None
    by_client: list[TrendClient]


@dataclass(frozen=True)
class CreditRisk:
    external_client_ref: str
    client_name: str | None
    remaining_cents: int
    days_left: float
    href: str


@dataclass(frozen=True)
class CreditBlock:
    """Spec 027: money for the partner. The runway is computed in credits and
    only the amounts are converted, so ``days_left`` does not depend on
    rounding."""

    available_cents: int | None
    spent_7d_cents: int
    daily_average_cents: int
    days_left: float | None
    at_risk: list[CreditRisk]


@dataclass(frozen=True)
class PortfolioRow:
    external_client_ref: str
    client_name: str | None
    status: str
    conversations_7d: int
    series_7d: list[int]
    last_activity_at: datetime | None
    credit_cap_cents: int | None
    credit_remaining_cents: int | None
    attention: int
    href: str


def fix_href(kind: str, ref: str) -> str:
    """Where each problem is fixed, one click away."""
    base = f"/clients/{ref}"
    return {
        "out_of_quota": f"/usage?client={ref}",
        "credit_low": f"/usage?client={ref}",
        "no_active_agent": f"{base}/agent",
        "whatsapp_disconnected": f"{base}/channels",
        "needs_reauth": f"{base}/channels",
        "quality_red": f"{base}/channels",
        "failed_messages": f"{base}/conversations",
        "template_rejected": f"{base}/channels",
        "draft_unpublished": f"{base}/agent",
        "provisioning": base,
    }[kind]


def _item(kind: str, client: ClientRow, count: int | None = None) -> AttentionItem:
    return AttentionItem(
        kind=kind,
        severity=SEVERITY[kind],
        external_client_ref=client.ref,
        client_name=client.name,
        count=count,
        href=fix_href(kind, client.ref),
    )


def attention_items(
    clients: list[ClientRow],
    snapshots: Mapping[uuid.UUID, TenantSnapshot],
    out_of_quota: Mapping[uuid.UUID, bool],
    templates_rejected: Mapping[uuid.UUID, int],
) -> list[AttentionItem]:
    """Every problem of every client, worst first, then by client name."""
    items: list[AttentionItem] = []
    for c in clients:
        if c.status is TenantStatus.PROVISIONING:
            items.append(_item("provisioning", c))
            continue
        if c.status is not TenantStatus.ACTIVE:
            continue
        if out_of_quota.get(c.tenant_id, False):
            items.append(_item("out_of_quota", c))
        s = snapshots.get(c.tenant_id)
        if s is None:
            continue
        if s.agent_version is None:
            items.append(_item("no_active_agent", c))
        if s.whatsapp_bad:
            items.append(_item("whatsapp_disconnected", c, s.whatsapp_bad))
        if s.needs_reauth:
            items.append(_item("needs_reauth", c))
        if s.whatsapp_quality_red:
            items.append(_item("quality_red", c, s.whatsapp_quality_red))
        if s.failed_messages_24h:
            items.append(_item("failed_messages", c, s.failed_messages_24h))
        rejected = templates_rejected.get(c.tenant_id, 0)
        if rejected:
            items.append(_item("template_rejected", c, rejected))
        if s.stale_drafts:
            items.append(_item("draft_unpublished", c))
    items.sort(key=lambda i: (i.severity, i.client_name or i.external_client_ref))
    return items


def credit_low_items(clients: list[ClientRow], at_risk: list[CreditRisk]) -> list[AttentionItem]:
    """Clients that will run out of balance before the month ends, as
    attention rows: ``count`` is the days they have left at the 7-day pace."""
    names = {c.ref: c for c in clients}
    return [
        _item("credit_low", names[r.external_client_ref], max(1, round(r.days_left)))
        for r in at_risk
        if r.external_client_ref in names
    ]


def merge_attention(items: list[AttentionItem], more: list[AttentionItem]) -> list[AttentionItem]:
    out = [*items, *more]
    out.sort(key=lambda i: (i.severity, i.client_name or i.external_client_ref))
    return out


def review_block(
    clients: list[ClientRow], snapshots: Mapping[uuid.UUID, TenantSnapshot]
) -> ReviewBlock:
    rows: list[ReviewClient] = []
    for c in clients:
        s = snapshots.get(c.tenant_id)
        if s is None or not (s.escalated_recent or s.payments_pending or s.unanswered_7d):
            continue
        rows.append(
            ReviewClient(
                external_client_ref=c.ref,
                client_name=c.name,
                escalated=s.escalated_recent,
                payments=s.payments_pending,
                unanswered=s.unanswered_7d,
                href=f"/clients/{c.ref}/conversations",
            )
        )
    return ReviewBlock(
        escalated=sum(r.escalated for r in rows),
        payments=sum(r.payments for r in rows),
        unanswered=sum(r.unanswered for r in rows),
        clients=rows,
    )


def window(today: date, days: int = SHOWN_DAYS) -> list[date]:
    """The last ``days`` UTC days, oldest first, today last."""
    return [today - timedelta(days=days - 1 - i) for i in range(days)]


def series_for(snapshot: TenantSnapshot | None, days: list[date]) -> list[int]:
    if snapshot is None:
        return [0 for _ in days]
    return [snapshot.daily.get(d, 0) for d in days]


def trend_block(
    clients: list[ClientRow], snapshots: Mapping[uuid.UUID, TenantSnapshot], today: date
) -> TrendBlock:
    shown = window(today)
    before = window(today - timedelta(days=SHOWN_DAYS))
    per_client = [(c, series_for(snapshots.get(c.tenant_id), shown)) for c in clients]
    totals = [sum(series[i] for _, series in per_client) for i in range(len(shown))]
    previous = sum(sum(series_for(snapshots.get(c.tenant_id), before)) for c in clients)
    ranked = sorted((p for p in per_client if sum(p[1]) > 0), key=lambda p: -sum(p[1]))
    by_client = [TrendClient(c.ref, c.name, series) for c, series in ranked[:TOP_CLIENTS]]
    rest = ranked[TOP_CLIENTS:]
    if rest:
        by_client.append(
            TrendClient(
                None, None, [sum(series[i] for _, series in rest) for i in range(len(shown))]
            )
        )
    return TrendBlock(
        days=shown,
        series=totals,
        current=sum(totals),
        previous=previous or None,
        by_client=by_client,
    )


def credit_block(
    clients: list[ClientRow],
    available: int | None,
    burn_7d: Mapping[uuid.UUID | None, int],
    allocations: Mapping[uuid.UUID, tuple[int, int]],
    days_to_month_end: float,
) -> CreditBlock:
    spent = sum(burn_7d.values())
    daily = spent / SHOWN_DAYS
    days_left = (available / daily) if (available is not None and daily > 0) else None
    at_risk: list[CreditRisk] = []
    for c in clients:
        if c.status is not TenantStatus.ACTIVE or c.tenant_id not in allocations:
            continue
        remaining = allocations[c.tenant_id][1]
        client_daily = burn_7d.get(c.tenant_id, 0) / SHOWN_DAYS
        if remaining <= 0 or client_daily <= 0:
            continue  # empty is an «attention» item already, idle is not a risk
        client_days = remaining / client_daily
        if client_days < days_to_month_end:
            at_risk.append(
                CreditRisk(
                    external_client_ref=c.ref,
                    client_name=c.name,
                    remaining_cents=credits_to_cents(remaining),
                    days_left=round(client_days, 1),
                    href=f"/usage?client={c.ref}",
                )
            )
    at_risk.sort(key=lambda r: r.days_left)
    return CreditBlock(
        available_cents=credits_to_cents(available) if available is not None else None,
        spent_7d_cents=credits_to_cents(spent, nearest=True),
        daily_average_cents=credits_to_cents(round(daily), nearest=True),
        days_left=round(days_left, 1) if days_left is not None else None,
        at_risk=at_risk,
    )


def portfolio_rows(
    clients: list[ClientRow],
    snapshots: Mapping[uuid.UUID, TenantSnapshot],
    allocations: Mapping[uuid.UUID, tuple[int, int]],
    attention: list[AttentionItem],
    today: date,
) -> list[PortfolioRow]:
    shown = window(today)
    per_ref: dict[str, int] = {}
    for item in attention:
        per_ref[item.external_client_ref] = per_ref.get(item.external_client_ref, 0) + 1
    rows: list[PortfolioRow] = []
    for c in clients:
        s = snapshots.get(c.tenant_id)
        series = series_for(s, shown)
        alloc = allocations.get(c.tenant_id)
        rows.append(
            PortfolioRow(
                external_client_ref=c.ref,
                client_name=c.name,
                status=c.status.value,
                conversations_7d=sum(series),
                series_7d=series,
                last_activity_at=s.last_activity_at if s is not None else None,
                credit_cap_cents=credits_to_cents(alloc[0]) if alloc else None,
                credit_remaining_cents=credits_to_cents(alloc[1]) if alloc else None,
                attention=per_ref.get(c.ref, 0),
                href=f"/clients/{c.ref}",
            )
        )
    return rows


#: Clients drawn on their own in the spend bar; the rest go together.
SPEND_TOP = 3


@dataclass(frozen=True)
class SpendShare:
    """One slice of the month's spend. ``kind``: ``client`` (one client),
    ``rest`` (the other clients together) or ``outside`` (spent outside any
    client: the Companion and partner-level tests)."""

    kind: str
    external_client_ref: str | None
    client_name: str | None
    cents: int


@dataclass(frozen=True)
class SpendBlock:
    """What the month's credit is worth at the price the partner pays for it
    (``CREDIT_USD_PER_MILLION``). Never Auphere's cost: that is internal."""

    cents: int
    previous_cents: int | None
    projected_cents: int
    currency: str
    by_client: list[SpendShare]


def _share(kind: str, ref: str | None, name: str | None, credits: int) -> SpendShare:
    return SpendShare(kind, ref, name, credits_to_cents(credits, nearest=True))


def spend_block(
    clients: list[ClientRow],
    month_burn: Mapping[uuid.UUID | None, int],
    previous_credits: int,
    *,
    daily_7d: float,
    days_left: float,
) -> SpendBlock:
    """The month so far, split by client, the same days of last month, and
    where it ends at this pace: what is spent plus the last 7 days' daily
    average for the days left. Not «month so far * days / elapsed», which on
    the 2nd of the month multiplies one day by thirty. No spend last month:
    no comparison, never an invented +100 %."""
    month = max(0, sum(month_burn.values()))
    previous = max(0, previous_credits)
    projected = month + max(0.0, daily_7d) * max(0.0, days_left)
    known = {c.tenant_id: c for c in clients}
    ranked = sorted(
        ((known[tid], q) for tid, q in month_burn.items() if tid in known and q > 0),
        key=lambda p: -p[1],
    )
    shares = [_share("client", c.ref, c.name, q) for c, q in ranked[:SPEND_TOP]]
    rest = sum(q for _, q in ranked[SPEND_TOP:])
    if rest > 0:
        shares.append(_share("rest", None, None, rest))
    outside = sum(q for tid, q in month_burn.items() if tid not in known and q > 0)
    if outside > 0:
        shares.append(_share("outside", None, None, outside))
    return SpendBlock(
        cents=credits_to_cents(month, nearest=True),
        previous_cents=credits_to_cents(previous, nearest=True) or None,
        projected_cents=credits_to_cents(round(projected), nearest=True),
        currency=CURRENCY,
        by_client=shares,
    )


def days_until(end: datetime, now: datetime) -> float:
    return max(0.0, (end - now).total_seconds() / 86400)


# ── Spec 047 (T065, T067): la bolsa, el Panel del cliente y las acciones ───────
#
# La bolsa se lee de ``partner_allocations`` hasta la ola 7, en US$. Las cifras
# salen de las mismas cuentas que la consola lite (``lite_home.balance_of``,
# ``spend_block`` y ``split_cents``) para que cuadren al céntimo (requisito
# 14.6); los días, del ritmo medio de los últimos 7 días **completos**, y solo
# con 3 días o más de consumo (14.1, 14.2, ``contracts/events.md`` §1.4).

#: Días completos que cuentan para el ritmo.
PACE_DAYS = 7
#: Con menos días de consumo, los días no se estiman.
MIN_PACE_DAYS = 3
#: El aviso ámbar (requisito 14.1).
WARN_SPENT_PCT = 80
#: «Saldo bajo»: por debajo de este porcentaje de su base (``attention.py``).
LOW_LEFT_PCT = 20
#: Lo que le falta a la ficha, en el orden del Panel (requisito 14.5).
MISSING_ORDER: tuple[str, ...] = ("hours", "services", "locations", "sources", "links")
#: Agentes en «Agentes que más consumen».
TOP_AGENTS = 4


@dataclass(frozen=True)
class BagBlock:
    """La bolsa de un cliente, en céntimos de ``currency`` (y en créditos para
    el ritmo, que no depende del redondeo). ``state``: ``ok``, ``low``,
    ``not_enough``, ``empty``, ``unlimited`` o ``unassigned``."""

    state: str
    currency: str
    assigned: bool
    unlimited: bool
    cap_cents: int | None
    remaining_cents: int | None
    spent_cents: int | None
    pct_spent: float | None
    pct_left: float | None
    days_left: float | None
    days_estimable: bool
    alerts: tuple[str, ...]
    #: Para la regla de atención (``attention.ClientFacts``).
    empty: bool


def pace(daily_credits: list[int]) -> tuple[float, int]:
    """El ritmo medio diario de los últimos ``PACE_DAYS`` días completos y en
    cuántos hubo consumo."""
    days = daily_credits[-PACE_DAYS:]
    active = sum(1 for d in days if d > 0)
    return (sum(days) / PACE_DAYS if days else 0.0), active


def bag_block(
    allocation: tuple[int, int] | None,
    *,
    purchased: int | None,
    daily_credits: list[int],
    out_of_quota: bool,
    unlimited: bool,
    days_to_month_end: float,
) -> BagBlock:
    """La bolsa (ver arriba). ``out_of_quota`` es ``wallet.quota_state``: la
    definición de «no puede atender por saldo» que usa la puerta del turno."""
    if unlimited:
        return BagBlock(
            "unlimited", CURRENCY, True, True, None, None, None, None, None, None, False, (), False
        )
    if allocation is None:
        return BagBlock(
            "unassigned",
            CURRENCY,
            False,
            False,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            (),
            True,
        )
    cap, remaining = allocation
    if purchased is not None:
        # Nunca más que el dinero que existe (spec 033, como la consola lite).
        remaining = max(0, min(remaining, purchased))
    spent = max(0, cap - remaining)
    daily, active_days = pace(daily_credits)
    estimable = active_days >= MIN_PACE_DAYS and daily > 0
    days = round(remaining / daily, 1) if estimable else None
    pct_spent = round(spent / cap * 100, 1) if cap > 0 else None
    pct_left = round(remaining / cap * 100, 1) if cap > 0 else None
    empty = out_of_quota or remaining <= 0
    alerts: tuple[str, ...] = ()
    if empty:
        alerts = ("empty",)
    elif pct_spent is not None and pct_spent >= WARN_SPENT_PCT:
        alerts = ("warn_80",)
    if empty:
        state = "empty"
    elif pct_left is not None and pct_left < LOW_LEFT_PCT:
        state = "low"
    elif days is not None and days < days_to_month_end:
        state = "not_enough"
    else:
        state = "ok"
    return BagBlock(
        state=state,
        currency=CURRENCY,
        assigned=True,
        unlimited=False,
        cap_cents=credits_to_cents(cap),
        remaining_cents=credits_to_cents(remaining),
        spent_cents=credits_to_cents(spent, nearest=True),
        pct_spent=pct_spent,
        pct_left=pct_left,
        days_left=days,
        days_estimable=estimable,
        alerts=alerts,
        empty=empty,
    )


def first_missing(states: Mapping[str, str]) -> str | None:
    """Lo primero que le falta a la ficha (requisito 14.5); ``None`` si nada."""
    for section in MISSING_ORDER:
        if states.get(section, "pending") == "pending":
            return section
    return None


@dataclass(frozen=True)
class AgentFigures:
    agent_id: uuid.UUID
    name: str
    visible: str
    credits: int
    cents: int
    conversations: int


@dataclass(frozen=True)
class AgentShare:
    agent_id: uuid.UUID
    name: str
    cents: int
    share_pct: float


def spend_shares(figures: list[AgentFigures]) -> list[AgentShare]:
    """La barra del consumo repartida por agente, de más a menos."""
    total = sum(f.credits for f in figures)
    ranked = sorted((f for f in figures if f.credits > 0), key=lambda f: (-f.credits, f.name))
    return [
        AgentShare(
            agent_id=f.agent_id,
            name=f.name,
            cents=f.cents,
            share_pct=round(f.credits / total * 100, 1) if total else 0.0,
        )
        for f in ranked
    ]


def top_spenders(figures: list[AgentFigures], limit: int = TOP_AGENTS) -> list[AgentFigures]:
    """Los que más consumen: primero el consumo, después las conversaciones."""
    return sorted(figures, key=lambda f: (-f.credits, -f.conversations, f.name))[:limit]


def per_conversation_cents(cents: int, conversations: int) -> int | None:
    return round(cents / conversations) if conversations > 0 else None


@dataclass(frozen=True)
class MonthBlock:
    period_start: date
    period_end: date
    conversations: int
    handed_to_person: int
    resolved_without_person: int
    resolved_pct: float | None


def month_block(start: date, end: date, conversations: int, handed: int) -> MonthBlock:
    handed = max(0, min(handed, conversations))
    resolved = conversations - handed
    return MonthBlock(
        period_start=start,
        period_end=end,
        conversations=conversations,
        handed_to_person=handed,
        resolved_without_person=resolved,
        resolved_pct=round(resolved / conversations * 100, 1) if conversations else None,
    )


def client_actions(permissions: frozenset[str] | set[str], *, archived: bool) -> list[str]:
    """Lo que el menú ⋯ ofrece a esta persona (requisito 7.6): lo que no puede
    no sale, salvo «Asignar saldo», que pasa a «Pedir saldo»."""
    out: list[str] = []
    if "clients:write" in permissions:
        out.append("edit")
    out.append("assign_balance" if "usage:write" in permissions else "request_balance")
    if "agents:write" in permissions and not archived:
        out.append("new_agent")
    if "clients:write" in permissions:
        out.append("restore" if archived else "archive")
    if "clients:delete" in permissions:
        out.append("delete")
    return out


__all__ = [
    "MISSING_ORDER",
    "SEVERITY",
    "AgentFigures",
    "AgentShare",
    "BagBlock",
    "ClientRow",
    "MonthBlock",
    "attention_items",
    "bag_block",
    "client_actions",
    "credit_block",
    "credit_low_items",
    "days_until",
    "first_missing",
    "fix_href",
    "merge_attention",
    "month_block",
    "pace",
    "per_conversation_cents",
    "portfolio_rows",
    "review_block",
    "spend_block",
    "spend_shares",
    "top_spenders",
    "trend_block",
    "window",
]
