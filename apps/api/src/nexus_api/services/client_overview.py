"""Lo que la lista de clientes y el Panel del cliente leen de la base (spec 047, T065, T067).

Las reglas viven en funciones puras (``attention.py``, ``agent_lifecycle.py`` y
``console_home_blocks.py``); aquí solo se leen los hechos que necesitan, con el
mismo cuidado que ``console_home.tenant_snapshots``:

- las tablas de cada cliente (agentes, versiones, canales, credenciales, la
  ficha) tienen la RLS forzada: se leen **con el cliente puesto**, una
  transacción por cliente, en su sesión y con concurrencia acotada. Un cliente
  cuya lectura falla se omite y el resto responde;
- el libro y las bolsas son del partner (``partner_allocations``,
  ``usage_ledger``): una lectura acotada a su partner para todos sus clientes.

**El estado de cada agente** sale de ``agent_lifecycle.visible_state`` con su
vida derivada de lo que hay hoy: archivado, en pausa porque su cliente está
archivado o en pausa (``client_archived``, ``client_paused``), publicado si
tiene versión activa y borrador si no. La pausa de cada agente con su motivo y
su ``before_pause`` llega con el bloque E (``agents.lifecycle``); hasta
entonces archivar un cliente lo pausa a través del cliente, y restaurarlo los
devuelve a todos a como estaban.

**Un canal**: su estado guardado y la audiencia de la versión activa de su
agente (spec 024): «A todos» si contesta a todos, «Solo mi equipo» si contesta
a una lista. Un canal desconectado solo lo desconecta el partner
(«Desvincular»), así que no cuenta como problema.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import sqlalchemy as sa
import structlog

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    Channel,
    ChannelStatus,
    Conversation,
    ConversationStatus,
    TenantCredentials,
    TenantStatus,
)
from nexus_api.db.models.business import BusinessProfile, BusinessSection
from nexus_api.services.agent_audience import count_of
from nexus_api.services.agent_lifecycle import (
    AgentFacts,
    ChannelFacts,
    VisibleState,
    agent_visible_state,
)
from nexus_api.services.attention import Attention, ClientFacts, attention
from nexus_api.services.channel_config import partner_on_v2
from nexus_api.services.console_home_blocks import (
    PACE_DAYS,
    WARN_SPENT_PCT,
    AgentFigures,
    BagBlock,
    bag_block,
)
from nexus_api.services.console_traffic import customer_conversation_ids, customer_facing_channel

log = structlog.get_logger(__name__)

#: Clientes leídos a la vez (cada uno es una conexión del pool).
CONCURRENCY = 6


@dataclass(frozen=True)
class AgentState:
    agent_id: uuid.UUID
    name: str
    created_at: datetime
    facts: AgentFacts
    visible: VisibleState


@dataclass
class ClientDetail:
    """Lo de un cliente que se lee con su RLS."""

    tenant_id: uuid.UUID
    niche: str | None = None
    agents: list[AgentState] = field(default_factory=list)
    reauth: int = 0
    sections: dict[str, str] = field(default_factory=dict)


def life_of(
    agent_status: str,
    *,
    published: bool,
    tenant_status: TenantStatus,
    lifecycle: str | None = None,
    pause_reason: str | None = None,
) -> tuple[str, str | None]:
    """La vida del agente que se enseña, con su motivo de pausa (ver el módulo).
    La pausa del cliente manda sobre la del agente; la del agente es la guardada
    (spec 047, 0190)."""
    if agent_status == "archived" or lifecycle == "archived":
        return "archived", None
    if tenant_status is TenantStatus.ARCHIVED:
        return "paused", "client_archived"
    if tenant_status is TenantStatus.PAUSED:
        return "paused", "client_paused"
    if lifecycle == "paused":
        return "paused", pause_reason or "manual"
    return ("published" if published else "draft"), None


def _audience(policies: dict[str, Any] | None) -> str:
    mode, _count = count_of(policies or {})
    return "everyone" if mode == "everyone" else "team_only"


def channel_audience(
    stored: str | None, *, strict: bool, published: bool, policies: dict[str, Any] | None
) -> str:
    """La audiencia que se enseña de un canal, con la misma regla que la puerta
    (``admin_gate.audience_suppresses``): la del canal cuando el canal decide
    (``strict``) o ya tiene una; si no, la del agente, como antes de la 047."""
    if strict or (stored and stored != "unset"):
        return stored or "unset"
    return _audience(policies) if published else "unset"


async def read_client(
    session: Any, tenant_id: uuid.UUID, tenant_status: TenantStatus
) -> ClientDetail:
    """Dentro de una transacción con ``tenant_id`` puesto."""
    out = ClientDetail(tenant_id=tenant_id)
    out.niche = await session.scalar(
        sa.select(BusinessProfile.niche).where(BusinessProfile.tenant_id == tenant_id)
    )
    agents = (
        await session.execute(
            sa.select(
                Agent.id,
                Agent.name,
                Agent.status,
                Agent.created_at,
                Agent.lifecycle,
                Agent.pause_reason,
            )
            .where(Agent.tenant_id == tenant_id)
            .order_by(Agent.created_at, Agent.id)
        )
    ).all()
    active_versions = {
        agent_id: policies
        for agent_id, policies in (
            await session.execute(
                sa.select(AgentConfig.agent_id, AgentConfig.policies).where(
                    AgentConfig.tenant_id == tenant_id,
                    AgentConfig.status == AgentConfigStatus.ACTIVE,
                )
            )
        ).all()
    }
    channels = (
        await session.execute(
            sa.select(Channel.agent_id, Channel.status, Channel.audience_mode, Channel.type).where(
                Channel.tenant_id == tenant_id, customer_facing_channel()
            )
        )
    ).all()
    live = [a for a in agents if a.status != "archived"]
    principal = live[0].id if live else None
    by_agent: dict[uuid.UUID | None, list[tuple[ChannelStatus, str, bool]]] = {}
    v2 = await partner_on_v2(session, tenant_id) if channels else False
    for agent_id, status, audience_mode, kind in channels:
        whatsapp = (kind.value if hasattr(kind, "value") else str(kind)) == "whatsapp"
        by_agent.setdefault(agent_id or principal, []).append(
            (status, audience_mode, v2 and whatsapp)
        )
    for a in agents:
        published = a.id in active_versions
        life, reason = life_of(
            a.status,
            published=published,
            tenant_status=tenant_status,
            lifecycle=a.lifecycle,
            pause_reason=a.pause_reason,
        )
        facts = AgentFacts(
            life=life,
            pause_reason=reason,
            channels=tuple(
                ChannelFacts(
                    status=status.value,
                    audience_mode=channel_audience(
                        stored,
                        strict=strict,
                        published=published,
                        policies=active_versions.get(a.id),
                    ),
                    disconnected_on_request=status is ChannelStatus.DISCONNECTED,
                )
                for status, stored, strict in by_agent.get(a.id, [])
            ),
        )
        out.agents.append(
            AgentState(
                agent_id=a.id,
                name=a.name,
                created_at=a.created_at,
                facts=facts,
                visible=agent_visible_state(facts),
            )
        )
    out.reauth = int(
        await session.scalar(
            sa.select(sa.func.count())
            .select_from(TenantCredentials)
            .where(TenantCredentials.needs_reauth.is_(True))
        )
        or 0
    )
    out.sections = {
        section: state
        for section, state in (
            await session.execute(
                sa.select(BusinessSection.section, BusinessSection.state).where(
                    BusinessSection.tenant_id == tenant_id
                )
            )
        ).all()
    }
    return out


async def read_clients(
    tenants: Iterable[tuple[uuid.UUID, TenantStatus]],
) -> dict[uuid.UUID, ClientDetail]:
    """``read_client`` de cada cliente, cada uno con su RLS y su sesión."""
    sm = get_sessionmaker()
    sem = asyncio.Semaphore(CONCURRENCY)
    out: dict[uuid.UUID, ClientDetail] = {}

    async def _one(tenant_id: uuid.UUID, status: TenantStatus) -> None:
        async with sem:
            try:
                async with sm() as session, tenant_scoped_session(session, tenant_id):
                    out[tenant_id] = await read_client(session, tenant_id, status)
            except Exception as exc:  # uno que falla no esconde a los demás
                log.warning(
                    "client_overview.read_failed",
                    tenant_id=str(tenant_id),
                    error=type(exc).__name__,
                )

    await asyncio.gather(*(_one(t, s) for t, s in tenants))
    return out


# ── el dinero, del libro del partner ───────────────────────────────────────────


def pace_window(now: datetime) -> tuple[datetime, list[date]]:
    """Desde cuándo leer el ritmo y los ``PACE_DAYS`` días completos (UTC)."""
    today = now.astimezone(UTC).date()
    days = [today - timedelta(days=PACE_DAYS - i) for i in range(PACE_DAYS)]
    since = datetime.combine(days[0], datetime.min.time(), tzinfo=UTC)
    return since, days


def days_to_month_end(now: datetime) -> float:
    from nexus_api.services.console_home_blocks import days_until
    from nexus_api.services.console_reporting import month_bounds

    _since, until, _elapsed, _days = month_bounds(now)
    return days_until(until, now)


async def bags(
    partner_id: uuid.UUID,
    tenants: list[tuple[uuid.UUID, bool]],
    *,
    now: datetime | None = None,
) -> dict[uuid.UUID, BagBlock]:
    """La bolsa de cada cliente: ``(tenant_id, unlimited)`` → ``BagBlock``."""
    from nexus_api.metering.wallet import (
        allocations_for,
        credit_burn_by_day,
        quota_state,
        read_wallet,
    )

    now = now or datetime.now(UTC)
    ids = [t for t, _u in tenants]
    if not ids:
        return {}
    from_wallets = await _bags_from_wallets(partner_id, tenants, now)
    if from_wallets is not None:
        return from_wallets
    allocations = await allocations_for(partner_id, ids)
    quota = await quota_state(partner_id, ids)
    wallet = await read_wallet(partner_id)
    since, days = pace_window(now)
    try:
        burn = await credit_burn_by_day(partner_id, ids, since, include_outside=False)
    except Exception as exc:
        log.warning("client_overview.burn_unreadable", error=type(exc).__name__)
        burn = {}
    to_month_end = days_to_month_end(now)
    out: dict[uuid.UUID, BagBlock] = {}
    for tenant_id, unlimited in tenants:
        daily = [burn.get((tenant_id, d), 0) for d in days]
        out[tenant_id] = bag_block(
            allocations.get(tenant_id),
            purchased=wallet.purchased_remaining if wallet is not None else None,
            daily_credits=daily,
            out_of_quota=quota.get(tenant_id, True),
            unlimited=unlimited,
            days_to_month_end=to_month_end,
        )
    return out


async def _bags_from_wallets(
    partner_id: uuid.UUID, tenants: list[tuple[uuid.UUID, bool]], now: datetime
) -> dict[uuid.UUID, BagBlock] | None:
    """Spec 047 (46.7): con bolsas, la bolsa del cliente es su ``client_wallets``, en
    su moneda, con las mismas cifras y estados que Consumo y los avisos
    (``wallet.alerts``). ``None``: el partner sigue con ``partner_allocations``."""
    from nexus_api.billing.pricing import credits_to_cents
    from nexus_api.core.partner_context import apply_partner_to_session
    from nexus_api.db.models import ClientWallet
    from nexus_api.services.wallet import alerts as wallet_alerts
    from nexus_api.services.wallet.bags import as_client, bags_active

    today = now.date()
    out: dict[uuid.UUID, BagBlock] = {}
    async with get_sessionmaker()() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        if not await bags_active(session, partner_id):
            return None
        for tenant_id, unlimited in tenants:
            # La bolsa es del cliente: se lee con su contexto puesto.
            await as_client(session, tenant_id)
            bag = await session.get(ClientWallet, tenant_id)
            if unlimited:
                out[tenant_id] = BagBlock(
                    "unlimited", "USD", True, True, None, None, None, None, None, None, False,
                    (), False,
                )  # fmt: skip
                continue
            if bag is None or not (bag.balance_micros or bag.month_base_micros):
                # Cliente nuevo o sin nada este mes: «Sin saldo», con «Asignar saldo».
                out[tenant_id] = BagBlock(
                    "unassigned", bag.currency if bag else "USD", False, False, None, None,
                    None, None, None, None, False, ("empty",), True,
                )  # fmt: skip
                continue
            base, balance, spent = bag.month_base_micros, bag.balance_micros, bag.month_spent_micros
            pace = await wallet_alerts.pace_per_day(session, bag, today)
            pct_spent = round(spent / base * 100, 1) if base > 0 else None
            empty = balance <= 0
            alerts: tuple[str, ...] = ()
            if empty:
                alerts = ("empty",)
            elif pct_spent is not None and pct_spent >= WARN_SPENT_PCT:
                alerts = ("warn_80",)
            out[tenant_id] = BagBlock(
                state=await wallet_alerts.bag_state(session, bag, today),
                currency=bag.currency,
                assigned=True,
                unlimited=False,
                cap_cents=credits_to_cents(base),
                remaining_cents=credits_to_cents(balance),
                spent_cents=credits_to_cents(spent, nearest=True),
                pct_spent=pct_spent,
                pct_left=round(balance / base * 100, 1) if base > 0 else None,
                days_left=wallet_alerts.days_left(balance, pace),
                days_estimable=pace is not None,
                alerts=alerts,
                empty=empty,
            )
    return out


def client_facts(
    ref: str, *, archived: bool, bag: BagBlock | None, detail: ClientDetail | None
) -> ClientFacts:
    """Los hechos de un cliente para la regla única y el orden de la lista."""
    return ClientFacts(
        ref=ref,
        archived=archived,
        bag_empty=bool(bag and bag.empty),
        pct_left=bag.pct_left if bag else None,
        days_left=bag.days_left if bag else None,
        reauth_integrations=detail.reauth if detail else 0,
        agents=tuple(a.facts for a in detail.agents) if detail else (),
    )


def client_attention(
    ref: str, *, archived: bool, bag: BagBlock | None, detail: ClientDetail | None
) -> Attention:
    """La regla única (``attention.py``) sobre los hechos de un cliente."""
    return attention(client_facts(ref, archived=archived, bag=bag, detail=detail))


# ── el mes del Panel ───────────────────────────────────────────────────────────


async def month_conversations(
    session: Any, *, since: datetime, principal: uuid.UUID | None
) -> tuple[int, int, dict[uuid.UUID, int]]:
    """Las conversaciones de clientes finales del mes: cuántas, cuántas pasaron
    a una persona y cuántas de cada agente. Dentro de la transacción del cliente."""
    handed = sa.or_(
        Conversation.status == ConversationStatus.ESCALATED,
        Conversation.assigned_user_id.is_not(None),
        sa.and_(
            Conversation.waiting_reason.is_not(None),
            Conversation.waiting_reason != "out_of_audience",
        ),
    )
    rows = (
        await session.execute(
            sa.select(Channel.agent_id, sa.func.count(), sa.func.count().filter(handed))
            .select_from(Conversation)
            .join(Channel, Channel.id == Conversation.channel_id)
            .where(
                Conversation.created_at >= since,
                Conversation.id.in_(customer_conversation_ids()),
            )
            .group_by(Channel.agent_id)
        )
    ).all()
    total = sum(int(r[1]) for r in rows)
    handed_total = sum(int(r[2]) for r in rows)
    per_agent: dict[uuid.UUID, int] = {}
    for agent_id, count, _h in rows:
        key = agent_id or principal
        if key is not None:
            per_agent[key] = per_agent.get(key, 0) + int(count)
    return total, handed_total, per_agent


def agent_figures(
    detail: ClientDetail,
    *,
    credits: dict[uuid.UUID | None, int],
    cents: dict[uuid.UUID, int],
    conversations: dict[uuid.UUID, int],
) -> list[AgentFigures]:
    """Lo de cada agente del Panel; lo gastado antes de los agentes es del principal."""
    live = [a for a in detail.agents if a.visible.code != "archived"]
    principal = live[0].agent_id if live else None
    out: list[AgentFigures] = []
    for a in detail.agents:
        spent = credits.get(a.agent_id, 0) + (
            credits.get(None, 0) if a.agent_id == principal else 0
        )
        if a.visible.code == "archived" and spent <= 0:
            continue
        out.append(
            AgentFigures(
                agent_id=a.agent_id,
                name=a.name,
                visible=a.visible.code,
                credits=spent,
                cents=cents.get(a.agent_id, 0),
                conversations=conversations.get(a.agent_id, 0),
            )
        )
    return out


__all__ = [
    "CONCURRENCY",
    "AgentState",
    "ClientDetail",
    "agent_figures",
    "bags",
    "client_attention",
    "client_facts",
    "days_to_month_end",
    "life_of",
    "month_conversations",
    "pace_window",
    "read_client",
    "read_clients",
]
