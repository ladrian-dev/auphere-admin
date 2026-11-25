"""El Panel del partner con la consola nueva — spec 047, T163 (requisito 48).

Cinco bloques, cada uno con su periodo (48.3), y «Necesita tu atención»:

- **Gasto del mes**: los 3 clientes que más gastan, el resto y las demás partidas,
  de ``wallet.usage_lines.spend`` — la misma función que Consumo, así que para el
  mismo periodo las cifras coinciden.
- **Conversaciones** del mes, del día 1 a hoy, contra los mismos días del mes
  pasado (``previous_total``; owner, 2026-11-22: las métricas son del mes).
- **Clientes atendiendo**: los que tienen algún agente «Atendiendo», sobre los no
  archivados, y cuántos siguen en alta.
- **Saldo disponible** y lo que hay en las bolsas (``usage_lines.balances``).
- **Conversaciones por día** (el mes, del día 1 a hoy): «Resueltas sin persona» y
  «Pasadas a una persona», contadas por el estado de cada conversación, nunca por su texto (48.4).

«Necesita tu atención» es la regla única (``attention.py``) de cada cliente, de más
a menos grave, cada fila con su arreglo (48.2). Sin nada que arreglar,
``all_serving``: «Todos tus clientes están atendiendo».

Spec 071: la lista es **la de** ``attention_live.live_attention`` —lo del partner y lo de
cada cliente—, la misma que ``GET /console/attention`` para quien mira. El Panel no
vuelve a leer a los clientes: la lista le da las fichas que leyó.
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
from nexus_api.services import attention_live, client_overview
from nexus_api.services.attention import AttentionItem
from nexus_api.services.attention_live import Client, Gate
from nexus_api.services.console_reporting import month_bounds
from nexus_api.services.console_traffic import customer_conversation_ids
from nexus_api.services.wallet.usage_lines import Balances, balances, spend

log = structlog.get_logger(__name__)

TOP_CLIENTS: Final = 3


@dataclass(frozen=True)
class SpendShare:
    kind: str  # client · rest · line
    ref: str | None
    name: str | None
    line: str | None
    amount: int
    approx: bool = False


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
    #: Owner, 2026-11-22: los mismos días del mes pasado (del 1 al mismo día), para la tendencia.
    previous_total: int | None = None
    attention: list[AttentionItem] = field(default_factory=list)
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
    gate: Gate,
    now: datetime | None = None,
) -> Panel:
    """``reporting``: la sesión de la petición (las lecturas de varios clientes van
    bajo el rol de informes, como en Consumo). ``gate``: quien mira (spec 071)."""
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
            with_outside=False,
            lines=("conversations", "client_tests"),
        )
        per_client: dict[uuid.UUID, int] = defaultdict(int)
        for (_d, line, tid), amount in month.cells.items():
            # Lo que le gasta su bolsa, como «Gasto del mes» de Consumo (46.7).
            if line in {"conversations", "client_tests"} and tid is not None:
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
        # Spec 072 (3.1, 3.2, D2): las partes son solo las bolsas de sus clientes y
        # suman el total, el mismo «Gasto del mes» de Consumo. Construcción (la paga
        # Auphere), Meta (el negocio) y Companion (la cuenta) no entran: Construcción
        # tiene su línea propia y Companion vive en el detalle de Consumo.
        panel.spend_total = sum(per_client.values())
    except Exception as exc:
        log.warning("partner_panel.money_failed", error=type(exc).__name__)
        panel.errors.append("money")

    # ── clientes, atención y conversaciones por día ──────────────────────
    panel.not_archived = len(live)
    # La lista, la misma de ``GET /console/attention`` (spec 071). Si la parte de
    # clientes falla entera, el bloque sale ``null`` como antes; una parte que falla
    # sin tumbarla se dice (research.md §R10).
    listed = await attention_live.live_attention(partner_id, gate=gate, clients=clients, now=now)
    if listed.clients_failed:
        panel.errors.append("attention")
    else:
        for c in live:
            detail = listed.details.get(c.tenant_id)
            if detail is not None and any(a.visible.code == "serving" for a in detail.agents):
                panel.serving += 1
        panel.attention = listed.items
        panel.onboarding = panel.not_archived - panel.serving
        panel.errors += [f"attention.{part}" for part in listed.errors]

    # Owner, 2026-11-22: las métricas del Panel son del mes, del día 1 a hoy, como el
    # gasto. La tendencia compara con los mismos días del mes pasado.
    today = now.date()
    first = today.replace(day=1)
    panel.days = [first + timedelta(days=i) for i in range(today.day)]
    prev_first = (first - timedelta(days=1)).replace(day=1)
    prev_last = min(prev_first + timedelta(days=today.day - 1), first - timedelta(days=1))
    start = datetime.combine(prev_first, datetime.min.time(), UTC)
    totals = [0] * len(panel.days)
    handed = [0] * len(panel.days)
    previous = 0
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
                elif prev_first <= d <= prev_last:
                    previous += total
        panel.handed = handed
        panel.previous_total = previous
        panel.resolved = [t - h for t, h in zip(totals, handed, strict=True)]
    except Exception as exc:
        log.warning("partner_panel.daily_failed", error=type(exc).__name__)
        panel.errors.append("conversations_per_day")
    return panel


__all__ = ["Client", "Gate", "Panel", "SpendShare", "build_panel"]
