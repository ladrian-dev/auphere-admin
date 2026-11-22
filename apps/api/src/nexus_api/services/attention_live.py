"""«Lo que te necesita», leído en vivo — spec 071 (requisitos 1 y 2).

La regla es ``attention.py`` y es pura; aquí se leen sus hechos y se arma **la lista**
de un partner: lo suyo (la partida de construcción, la cuenta, el cobro) y lo de cada
cliente. La leen tres sitios, y ninguno la recalcula:

- el Panel (``/console/home`` → ``panel.attention``, ``partner_panel.build_panel``);
- ``GET /console/attention`` (la campana, «Ahora», y los avisos de Consumo);
- :func:`resolve_cleared`, que resuelve los avisos guardados cuya condición ya no está.

**Aislamiento (garantía 1).** El partner llega siempre del servidor (el principal, el
cron o el mapeo de un cliente), nunca de un argumento del llamante. Los clientes son los
de ``partner_tenants`` de ese partner; cada ficha y cada bolsa se leen con el contexto
de su cliente, y la cuenta y la partida con el del partner (RLS). La resolución filtra
por ``partner_id``. Lo barre ``tests/isolation/test_071_attention_scope.py``.

**Lo que no se sabe no se dice, ni se resuelve (§V).** Cada parte se lee en su ``try``
y ``errors`` dice cuál falló (``partner``, ``clients``). La lista guarda qué se leyó
(``partner_read``, ``read_refs``) y :func:`resolve_cleared` solo resuelve eso.

**Quien mira.** Con una :class:`Gate`, cada fila sale solo si quien mira tiene su
permiso y el partner su módulo (research.md §R9). Sin puerta, la verdad entera: es lo
que necesita la resolución.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    ConsoleNotification,
    NotificationAudience,
    Partner,
    PartnerSubscription,
    PartnerTenant,
    PartnerWallet,
    Tenant,
    TenantStatus,
    UsageLedger,
)
from nexus_api.db.models.membership import STATE_PAYMENT_FAILED, STATE_UNPAID
from nexus_api.db.models.partner_wallet import (
    BUCKET_PURCHASED,
    KIND_BAG_ASSIGN,
    KIND_BAG_RETURN,
    KIND_DEBIT,
    KIND_EXPIRY,
)
from nexus_api.services.attention import (
    CONDITION_CODES,
    PARTNER_CONDITION_KINDS,
    AccountFacts,
    AttentionItem,
    BagFigures,
    BuildFacts,
    PartnerFacts,
    buy_first_when_empty,
    client_items,
    order_items,
    partner_items,
    still_listed,
)

if TYPE_CHECKING:
    from nexus_api.core.console_auth import ConsolePrincipal
    from nexus_api.services.client_overview import ClientDetail
    from nexus_api.services.console_home_blocks import BagBlock

log = structlog.get_logger(__name__)

#: El cobro que falló y sigue sin pagar (research.md §R5).
BILLING_FAILED_STATES: Final = frozenset({STATE_PAYMENT_FAILED, STATE_UNPAID})
#: El ritmo de la cuenta, como el de las bolsas (``wallet.alerts``).
PACE_DAYS: Final = 7
MIN_PACE_DAYS: Final = 3
#: De qué lectura sale cada código del partner.
_FAMILY: Final[dict[str, str]] = {
    "build_cap_exhausted": "build",
    "build_cap_warning": "build",
    "account_empty": "account",
    "account_low": "account",
    "billing_payment_failed": "billing",
}


@dataclass(frozen=True)
class Client:
    """Un cliente del partner, de ``partner_tenants``."""

    tenant_id: uuid.UUID
    ref: str
    name: str | None
    status: TenantStatus


@dataclass(frozen=True)
class Gate:
    """Lo que quien mira puede ver: sus permisos y los módulos de su partner."""

    permissions: frozenset[str]
    modules: frozenset[str]

    @classmethod
    def of(cls, principal: ConsolePrincipal) -> Gate:
        return cls(
            permissions=frozenset(principal.permissions),
            modules=frozenset(principal.partner.ordered_console_modules()),
        )

    @property
    def clients(self) -> bool:
        return "clients:read" in self.permissions and "clients" in self.modules

    @property
    def build(self) -> bool:
        return "usage:read" in self.permissions and "usage" in self.modules

    @property
    def account(self) -> bool:
        return "usage:read" in self.permissions and bool({"usage", "billing"} & self.modules)

    @property
    def billing(self) -> bool:
        return "billing:read" in self.permissions and "billing" in self.modules

    @property
    def can_assign(self) -> bool:
        return "usage:write" in self.permissions

    @property
    def can_buy(self) -> bool:
        """Comprar saldo (Facturación): owner y billing."""
        return "billing:manage" in self.permissions


@dataclass
class AttentionList:
    """La lista y lo que se sabe de ella."""

    items: list[AttentionItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    #: Las lecturas del partner que salieron bien (``build``, ``account``, ``billing``).
    partner_read: set[str] = field(default_factory=set)
    #: Los clientes cuyo estado se leyó entero (los archivados cuentan: no necesitan nada).
    read_refs: set[str] = field(default_factory=set)
    #: Todos los clientes del partner, cuando se pudieron leer (``None``: no se sabe).
    all_refs: set[str] | None = None
    #: La parte de clientes falló entera.
    clients_failed: bool = False
    #: Lo leído de cada cliente, para el Panel («Clientes atendiendo»).
    details: dict[uuid.UUID, ClientDetail] = field(default_factory=dict)


# ── las lecturas del partner ───────────────────────────────────────────────────


async def partner_clients(partner_id: uuid.UUID) -> list[Client]:
    async with get_sessionmaker()() as session, session.begin():
        rows = (
            await session.execute(
                sa.select(
                    PartnerTenant.tenant_id,
                    PartnerTenant.external_client_ref,
                    PartnerTenant.client_name,
                    Tenant.status,
                )
                .join(Tenant, Tenant.id == PartnerTenant.tenant_id)
                .where(PartnerTenant.partner_id == partner_id)
                .order_by(PartnerTenant.external_client_ref)
            )
        ).all()
    return [Client(tid, ref, name, status) for tid, ref, name, status in rows]


async def build_facts(partner_id: uuid.UUID) -> BuildFacts | None:
    """La partida del mes, con el estado que frena (``build_budget.read``). ``None``
    para los partners sin la consola nueva, que no la tienen."""
    from nexus_api.services.wallet import build_budget

    async with get_sessionmaker()() as session, session.begin():
        v2 = await session.scalar(
            sa.select(Partner.console_v2_enabled_at).where(Partner.id == partner_id)
        )
        if v2 is None:
            return None
        await apply_partner_to_session(session, partner_id)
        state = await build_budget.read(session, partner_id)
        currency = await session.scalar(
            sa.select(PartnerWallet.currency).where(PartnerWallet.partner_id == partner_id)
        )
    return BuildFacts(
        cap_micros=state.cap_micros,
        spent_micros=state.spent_micros,
        state=state.state,
        currency=str(currency or "USD"),
    )


def _outflow() -> sa.ColumnElement[Any]:
    """Lo que sale de la cuenta en un asiento: gasto, asignación a una bolsa o
    caducidad; lo que vuelve de una bolsa resta (research.md §R2)."""
    return sa.case(
        (
            UsageLedger.kind.in_((KIND_DEBIT, KIND_BAG_ASSIGN, KIND_EXPIRY)),
            UsageLedger.qty,
        ),
        (UsageLedger.kind == KIND_BAG_RETURN, -UsageLedger.qty),
        else_=0,
    )


async def account_facts(partner_id: uuid.UUID, now: datetime | None = None) -> AccountFacts | None:
    """La cuenta del partner para la regla (D2, research.md §R2 y §R3). ``None`` si no
    tiene cuenta."""
    from nexus_api.metering.wallet import _snapshot, purchased_spent_since
    from nexus_api.services.console_reporting import month_bounds
    from nexus_api.services.wallet.bags import assignable
    from nexus_api.services.wallet_alerts import _percent_used

    now = now or datetime.now(UTC)
    since, _until, _elapsed, _days = month_bounds(now)
    today = now.astimezone(UTC).date()
    pace_start = datetime.combine(today - timedelta(days=PACE_DAYS), datetime.min.time(), UTC)
    pace_end = datetime.combine(today, datetime.min.time(), UTC)
    async with get_sessionmaker()() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        account = await session.scalar(
            sa.select(PartnerWallet).where(PartnerWallet.partner_id == partner_id)
        )
        if account is None:
            return None
        purchased = UsageLedger.bucket == BUCKET_PURCHASED
        mine = UsageLedger.partner_id == partner_id
        out_month = int(
            await session.scalar(
                sa.select(sa.func.coalesce(sa.func.sum(_outflow()), 0)).where(
                    mine, purchased, UsageLedger.created_at >= since
                )
            )
            or 0
        )
        day = sa.cast(sa.func.timezone("UTC", UsageLedger.created_at), sa.Date)
        per_day = [
            int(total or 0)
            for _d, total in (
                await session.execute(
                    sa.select(day, sa.func.sum(_outflow()))
                    .where(
                        mine,
                        purchased,
                        UsageLedger.created_at >= pace_start,
                        UsageLedger.created_at < pace_end,
                    )
                    .group_by(day)
                )
            ).all()
        ]
        available = assignable(account)
        snapshot = _snapshot(account)
        currency = str(account.currency or "USD")
    base = available + max(0, out_month)
    active = [d for d in per_day if d > 0]
    pace = sum(active) / PACE_DAYS if len(active) >= MIN_PACE_DAYS else None
    # El porcentaje con que avisa ``wallet_alerts`` (sus mismas funciones): la regla
    # nunca dice menos que el aviso (research.md §R3).
    try:
        notice: float | None = _percent_used(
            snapshot.purchased_remaining, await purchased_spent_since(partner_id, since)
        )
    except Exception as exc:  # el emisor tampoco avisa si no lo lee
        log.warning("attention.account_notice_unreadable", error=type(exc).__name__)
        notice = None
    return AccountFacts(
        available_micros=available,
        currency=currency,
        pct_left=round(available / base * 100, 1) if base > 0 else None,
        days_left=int(available // pace) if pace else None,
        notice_pct_used=notice,
    )


async def billing_failed(partner_id: uuid.UUID) -> bool:
    """El último cobro de la suscripción falló y sigue sin pagar (research.md §R5)."""
    async with get_sessionmaker()() as session, session.begin():
        state = await session.scalar(
            sa.select(PartnerSubscription.state).where(PartnerSubscription.partner_id == partner_id)
        )
    return state in BILLING_FAILED_STATES


# ── la lista ───────────────────────────────────────────────────────────────────


def _bag_figures(block: BagBlock | None) -> BagFigures | None:
    if block is None:
        return None
    return BagFigures(
        balance_micros=block.balance_micros, currency=block.currency, days_left=block.days_left
    )


async def _partner_part(
    partner_id: uuid.UUID, gate: Gate | None, out: AttentionList, now: datetime
) -> PartnerFacts:
    build: BuildFacts | None = None
    account: AccountFacts | None = None
    failed = False
    broken = False
    if gate is None or gate.build:
        try:
            build = await build_facts(partner_id)
            out.partner_read.add("build")
        except Exception as exc:
            log.warning("attention.build_unreadable", error=type(exc).__name__)
            broken = True
    if gate is None or gate.account:
        try:
            account = await account_facts(partner_id, now)
            out.partner_read.add("account")
        except Exception as exc:
            log.warning("attention.account_unreadable", error=type(exc).__name__)
            broken = True
    if gate is None or gate.billing:
        try:
            failed = await billing_failed(partner_id)
            out.partner_read.add("billing")
        except Exception as exc:
            log.warning("attention.billing_unreadable", error=type(exc).__name__)
            broken = True
    if broken:
        out.errors.append("partner")
    return PartnerFacts(build=build, account=account, billing_failed=failed)


async def _clients_part(
    partner_id: uuid.UUID,
    gate: Gate | None,
    out: AttentionList,
    *,
    clients: list[Client] | None,
    refs: Collection[str] | None,
    now: datetime,
) -> None:
    from nexus_api.services import client_overview

    try:
        every = clients if clients is not None else await partner_clients(partner_id)
        out.all_refs = {c.ref for c in every}
        wanted = [c for c in every if refs is None or c.ref in refs]
        live = [c for c in wanted if c.status is not TenantStatus.ARCHIVED]
        # Un cliente archivado no necesita atención: se sabe sin leerlo.
        out.read_refs.update(c.ref for c in wanted if c.status is TenantStatus.ARCHIVED)
        if not live:
            return
        out.details = await client_overview.read_clients((c.tenant_id, c.status) for c in live)
        bags = await client_overview.bags(partner_id, [(c.tenant_id, False) for c in live], now=now)
    except Exception as exc:
        log.warning("attention.clients_unreadable", error=type(exc).__name__)
        out.errors.append("clients")
        out.clients_failed = True
        out.all_refs = None
        return
    can_assign = gate is None or gate.can_assign
    partial = False
    for c in live:
        detail = out.details.get(c.tenant_id)
        if detail is None:
            # Su ficha no se leyó: sin ella diría «sin agentes» y callaría un canal
            # caído. Se dice que la lista es parcial y no se toca nada suyo.
            partial = True
            continue
        bag = bags.get(c.tenant_id)
        found = client_overview.client_attention(c.ref, archived=False, bag=bag, detail=detail)
        out.items += client_items(
            c.ref, c.name, found, can_assign=can_assign, bag=_bag_figures(bag)
        )
        out.read_refs.add(c.ref)
    if partial:
        out.errors.append("clients")


async def live_attention(
    partner_id: uuid.UUID,
    *,
    gate: Gate | None = None,
    clients: list[Client] | None = None,
    refs: Collection[str] | None = None,
    now: datetime | None = None,
) -> AttentionList:
    """**La** lista del partner, de peor a mejor (``contracts/api.md``).

    ``gate``: quien mira (``None``: todo, para resolver). ``clients``: los clientes ya
    leídos (el Panel); si no, se leen. ``refs``: solo esos clientes (resolver tras
    tocar uno); lo del partner se lee siempre.
    """
    now = now or datetime.now(UTC)
    out = AttentionList()
    facts = await _partner_part(partner_id, gate, out, now)
    items = partner_items(facts)
    if gate is None or gate.clients:
        await _clients_part(partner_id, gate, out, clients=clients, refs=refs, now=now)
    out.items = order_items([*items, *out.items])
    if gate is not None:
        out.items = buy_first_when_empty(out.items, can_buy=gate.can_buy)
    return out


# ── los avisos que se resuelven solos (requisito 2) ────────────────────────────


async def _on_new_console(partner_id: uuid.UUID) -> bool:
    async with get_sessionmaker()() as session, session.begin():
        found = await session.scalar(
            sa.select(Partner.console_v2_enabled_at).where(Partner.id == partner_id)
        )
    return found is not None


async def _live_for_resolving(
    partner_id: uuid.UUID, refs: Collection[str] | None, now: datetime
) -> AttentionList | None:
    """La lista entera (sin puerta), o ``None`` si el partner no tiene la consola nueva
    (research.md §R6). Cada lectura en su sesión corta, **antes** de abrir la
    transacción que escribe: una transacción abierta que espera a otras sesiones se
    bloquea con cualquier ``LOCK`` que se ponga en medio (lo vio un ``TRUNCATE``)."""
    if not await _on_new_console(partner_id):
        return None
    return await live_attention(partner_id, refs=refs, now=now)


async def _apply_cleared(
    session: AsyncSession,
    partner_id: uuid.UUID,
    listed: AttentionList,
    *,
    refs: Collection[str] | None,
    now: datetime,
) -> int:
    partner_codes = {i.code for i in listed.items if i.scope == "partner"}
    by_ref: dict[str, set[str]] = defaultdict(set)
    for item in listed.items:
        if item.ref is not None:
            by_ref[item.ref].add(item.code)
    pending = (
        await session.execute(
            sa.select(
                ConsoleNotification.id,
                ConsoleNotification.kind,
                ConsoleNotification.external_client_ref,
            ).where(
                ConsoleNotification.partner_id == partner_id,
                ConsoleNotification.audience == NotificationAudience.PARTNER.value,
                ConsoleNotification.handled_at.is_(None),
                ConsoleNotification.kind.in_(tuple(CONDITION_CODES)),
            )
        )
    ).all()
    cleared: list[uuid.UUID] = []
    for notice_id, kind, ref in pending:
        code = CONDITION_CODES[kind]
        if kind in PARTNER_CONDITION_KINDS:
            if _FAMILY[code] in listed.partner_read and not still_listed(code, partner_codes):
                cleared.append(notice_id)
            continue
        if ref is None or (refs is not None and ref not in refs):
            continue
        if ref in listed.read_refs:
            if not still_listed(code, by_ref[ref]):
                cleared.append(notice_id)
        elif refs is None and listed.all_refs is not None and ref not in listed.all_refs:
            # Ya no es un cliente del partner: no puede necesitarle.
            cleared.append(notice_id)
    if cleared:
        await session.execute(
            sa.update(ConsoleNotification)
            .where(ConsoleNotification.id.in_(cleared))
            .values(handled_at=now, dedupe_key=None)
            .execution_options(synchronize_session=False)
        )
        log.info("attention.resolved", partner_id=str(partner_id), count=len(cleared))
    return len(cleared)


async def resolve_cleared(
    session: AsyncSession,
    partner_id: uuid.UUID,
    *,
    refs: Collection[str] | None = None,
    now: datetime | None = None,
) -> int:
    """Resuelve los avisos de condición pendientes del partner cuyo código ya no está en
    su lista: ``handled_at = now()`` y la ``dedupe_key`` libre, para que una vuelta del
    problema vuelva a avisar (2.2). No envía nada (D3). Devuelve cuántos.

    Escribe en la transacción de ``session`` (``console_notifications`` es de
    plataforma); la lista se lee antes, en sesiones propias: **llamar con el cambio ya
    confirmado** y sin nada leído aún en ``session``. Solo los partners con la consola
    nueva (research.md §R6) y solo los avisos del partner, no la copia de la persona del
    cliente (§R7). ``refs``: solo los avisos de esos clientes (más los del partner).
    """
    now = now or datetime.now(UTC)
    listed = await _live_for_resolving(partner_id, refs, now)
    if listed is None:
        return 0
    return await _apply_cleared(session, partner_id, listed, refs=refs, now=now)


async def resolve_cleared_detached(
    partner_id: uuid.UUID, *, refs: Iterable[str] | None = None
) -> int:
    """:func:`resolve_cleared` en su propia sesión, que solo se abre para escribir.
    Nunca lanza: resolver un aviso no puede deshacer lo que ya pasó."""
    wanted = None if refs is None else frozenset(refs)
    now = datetime.now(UTC)
    try:
        listed = await _live_for_resolving(partner_id, wanted, now)
        if listed is None:
            return 0
        async with get_sessionmaker()() as session, session.begin():
            return await _apply_cleared(session, partner_id, listed, refs=wanted, now=now)
    except Exception as exc:
        log.warning(
            "attention.resolve_failed", partner_id=str(partner_id), error=type(exc).__name__
        )
        return 0


async def resolve_cleared_for_tenant(tenant_id: uuid.UUID) -> int:
    """Tras arreglar algo de un cliente (un canal, un conector): su partner, solo él."""
    try:
        async with get_sessionmaker()() as session, session.begin():
            row = (
                await session.execute(
                    sa.select(PartnerTenant.partner_id, PartnerTenant.external_client_ref).where(
                        PartnerTenant.tenant_id == tenant_id
                    )
                )
            ).first()
    except Exception as exc:
        log.warning("attention.resolve_failed", error=type(exc).__name__)
        return 0
    if row is None:
        return 0
    return await resolve_cleared_detached(row.partner_id, refs=[row.external_client_ref])


__all__ = [
    "BILLING_FAILED_STATES",
    "AttentionList",
    "Client",
    "Gate",
    "account_facts",
    "billing_failed",
    "build_facts",
    "live_attention",
    "partner_clients",
    "resolve_cleared",
    "resolve_cleared_detached",
    "resolve_cleared_for_tenant",
]
