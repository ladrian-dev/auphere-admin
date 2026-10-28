"""El Panel del partner con la consola nueva — spec 047, T163 (requisito 48).

Cinco bloques, cada uno con su periodo (48.3), y «Necesita tu atención»:

- **Gasto del mes**: los 3 clientes que más gastan, el resto y las demás partidas,
  de ``wallet.usage_lines.spend`` — la misma función que Consumo, así que para el
  mismo periodo las cifras coinciden.
- **Conversaciones** de los últimos 7 días contra los 7 anteriores: el bloque de
  tendencia de hoy (``conversations_trend``), que el Panel cita con su periodo.
- **Clientes atendiendo**: los que tienen algún agente «Atendiendo», sobre los no
  archivados, y cuántos siguen en alta.
- **Saldo disponible** y lo que hay en las bolsas (``usage_lines.balances``).
- **Conversaciones por día** (7 días): «Resueltas sin persona» y «Pasadas a una
  persona», contadas por el estado de cada conversación, nunca por su texto (48.4).

«Necesita tu atención» es la regla única (``attention.py``) de cada cliente, de más
a menos grave, cada fila con su arreglo (48.2). Sin nada que arreglar,
``all_serving``: «Todos tus clientes están atendiendo».
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Final

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Channel, Conversation, ConversationStatus, TenantStatus
from nexus_api.services import client_overview
from nexus_api.services.attention import ATTENTION_REASONS
from nexus_api.services.console_reporting import month_bounds
from nexus_api.services.console_traffic import customer_conversation_ids
from nexus_api.services.wallet.usage_lines import Balances, balances, spend

log = structlog.get_logger(__name__)

#: El arreglo de cada motivo: la acción que el Panel pinta y adónde lleva.
#: ``{ref}`` es la referencia del cliente.
FIXES: Final[dict[str, tuple[str, str]]] = {
    "no_balance": ("assign_balance", "/clients/{ref}?assign=1"),
    "low_balance": ("assign_balance", "/clients/{ref}?assign=1"),
    "channel_problem": ("fix_channel", "/clients/{ref}/channels"),
    "integration_reauth": ("reconnect", "/clients/{ref}/integrations"),
    "agent_cap": ("raise_cap", "/clients/{ref}/agents"),
    "agent_without_channel": ("connect_channel", "/clients/{ref}/channels"),
    "no_agents": ("new_agent", "/clients/{ref}/agents/new"),
}
#: Quien no puede asignar pide (45.7).
REQUEST_INSTEAD: Final = frozenset({"no_balance", "low_balance"})
TOP_CLIENTS: Final = 3
DAYS: Final = 7


@dataclass(frozen=True)
class Client:
    tenant_id: uuid.UUID
    ref: str
    name: str | None
    status: TenantStatus


@dataclass(frozen=True)
class SpendShare:
    kind: str  # client · rest · line
    ref: str | None
    name: str | None
    line: str | None
    amount: int
    approx: bool = False


@dataclass(frozen=True)
class AttentionRow:
    ref: str
    name: str | None
    code: str
    count: int
    severity: int
    action: str
    href: str


@dataclass
class Panel:
    currency: str
    month_since: datetime
    month_until: datetime
    spend: list[SpendShare] = field(default_factory=list)
    spend_total: int = 0
    serving: int = 0
    not_archived: int = 0
    onboarding: int = 0
    balances: Balances | None = None
    days: list[date] = field(default_factory=list)
    resolved: list[int] = field(default_factory=list)
    handed: list[int] = field(default_factory=list)
    attention: list[AttentionRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def all_serving(self) -> bool:
        return not self.attention and not self.errors


def _handed() -> sa.ColumnElement[bool]:
    """«Pasada a una persona»: la misma definición que el Panel del cliente
    (``client_overview.month_conversations``)."""
    return sa.or_(
        Conversation.status == ConversationStatus.ESCALATED,
        Conversation.assigned_user_id.is_not(None),
        sa.and_(
            Conversation.waiting_reason.is_not(None),
            Conversation.waiting_reason != "out_of_audience",
        ),
    )


async def _daily(tenant_id: uuid.UUID, since: datetime) -> dict[date, tuple[int, int]]:
    day = sa.cast(sa.func.timezone("UTC", Conversation.created_at), sa.Date)
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        rows = (
            await session.execute(
                sa.select(day, sa.func.count(), sa.func.count().filter(_handed()))
                .select_from(Conversation)
                .join(Channel, Channel.id == Conversation.channel_id)
                .where(
                    Conversation.created_at >= since,
                    Conversation.id.in_(customer_conversation_ids()),
                )
                .group_by(day)
            )
        ).all()
    return {d: (int(total), int(handed)) for d, total, handed in rows}


async def build_panel(
    reporting: AsyncSession,
    *,
    partner_id: uuid.UUID,
    clients: list[Client],
    can_assign: bool,
    now: datetime | None = None,
) -> Panel:
    """``reporting``: la sesión de la petición (las lecturas de varios clientes van
    bajo el rol de informes, como en Consumo)."""
    now = now or datetime.now(UTC)
    since, until, _elapsed, _days = month_bounds(now)
    live = [c for c in clients if c.status is not TenantStatus.ARCHIVED]
    panel = Panel(currency="USD", month_since=since, month_until=until)

    # ── el dinero ─────────────────────────────────────────────────────────
    try:
        figures = await balances(partner_id)
        panel.balances = figures
        panel.currency = figures.currency
        month = await spend(
            reporting,
            partner_id=partner_id,
            tenant_ids=[c.tenant_id for c in clients],
            since=since,
            until=now,
            with_outside=True,
        )
        per_client: dict[uuid.UUID, int] = defaultdict(int)
        for (_d, line, tid), amount in month.cells.items():
            if line == "conversations" and tid is not None:
                per_client[tid] += amount
        by_id = {c.tenant_id: c for c in clients}
        ranked = sorted(per_client.items(), key=lambda kv: (-kv[1], by_id[kv[0]].ref))
        for tid, amount in ranked[:TOP_CLIENTS]:
            if amount > 0:
                c = by_id[tid]
                panel.spend.append(SpendShare("client", c.ref, c.name, "conversations", amount))
        rest = sum(amount for _tid, amount in ranked[TOP_CLIENTS:])
        if rest:
            panel.spend.append(SpendShare("rest", None, None, "conversations", rest))
        for line in ("companion", "build", "meta"):
            amount = month.total(lines=(line,))
            if amount:
                panel.spend.append(
                    SpendShare("line", None, None, line, amount, line in month.approx_lines)
                )
        # El total es lo que paga el partner, como «Gasto del mes» de Consumo.
        panel.spend_total = month.total(lines=("conversations", "companion"))
    except Exception as exc:
        log.warning("partner_panel.money_failed", error=type(exc).__name__)
        panel.errors.append("money")

    # ── clientes, atención y conversaciones por día ──────────────────────
    panel.not_archived = len(live)
    try:
        details = await client_overview.read_clients((c.tenant_id, c.status) for c in live)
        bag_blocks = await client_overview.bags(
            partner_id, [(c.tenant_id, False) for c in live], now=now
        )
        rows: list[AttentionRow] = []
        for c in live:
            detail = details.get(c.tenant_id)
            if detail is not None and any(a.visible.code == "serving" for a in detail.agents):
                panel.serving += 1
            found = client_overview.client_attention(
                c.ref, archived=False, bag=bag_blocks.get(c.tenant_id), detail=detail
            )
            for reason in found.reasons:
                action, href = FIXES[reason.code]
                if reason.code in REQUEST_INSTEAD and not can_assign:
                    action = "request_balance"
                rows.append(
                    AttentionRow(
                        ref=c.ref,
                        name=c.name,
                        code=reason.code,
                        count=reason.count,
                        severity=ATTENTION_REASONS.index(reason.code),
                        action=action,
                        href=href.format(ref=c.ref),
                    )
                )
        panel.attention = sorted(rows, key=lambda r: (r.severity, r.ref))
        panel.onboarding = panel.not_archived - panel.serving
    except Exception as exc:
        log.warning("partner_panel.attention_failed", error=type(exc).__name__)
        panel.errors.append("attention")

    today = now.date()
    panel.days = [today - timedelta(days=DAYS - 1 - i) for i in range(DAYS)]
    start = datetime.combine(panel.days[0], datetime.min.time(), UTC)
    totals = [0] * DAYS
    handed = [0] * DAYS
    index = {d: i for i, d in enumerate(panel.days)}
    try:
        sem = asyncio.Semaphore(client_overview.CONCURRENCY)

        async def _one(tenant_id: uuid.UUID) -> dict[date, tuple[int, int]]:
            async with sem:
                return await _daily(tenant_id, start)

        per_tenant = await asyncio.gather(*(_one(c.tenant_id) for c in live))
        for daily in per_tenant:
            for d, (total, h) in daily.items():
                if d in index:
                    totals[index[d]] += total
                    handed[index[d]] += h
        panel.handed = handed
        panel.resolved = [t - h for t, h in zip(totals, handed, strict=True)]
    except Exception as exc:
        log.warning("partner_panel.daily_failed", error=type(exc).__name__)
        panel.errors.append("conversations_per_day")
    return panel


__all__ = ["FIXES", "AttentionRow", "Client", "Panel", "SpendShare", "build_panel"]
