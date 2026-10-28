"""Consumo por partidas — spec 047, T158 (requisito 46; research D29 y D30).

Una sola función reparte el gasto de un periodo por día, partida y cliente, en la
moneda de la cuenta del partner. El resumen, la gráfica, la tabla por cliente y el
detalle leen de ella, así que la misma cifra sale igual en todas partes (46.7).

De dónde sale cada partida (todo del libro, nunca de restar topes):

- **Conversaciones** (la paga la bolsa del cliente): los cobros de turno de las
  bolsas (``client_wallet_entries`` ``debit_turn``) y, para lo cobrado antes de
  las bolsas, los débitos de la cuenta con cliente (``usage_ledger`` ``debit``).
- **Companion y teammates** (la cuenta): los débitos sin cliente.
- **Construcción y pruebas** (Auphere, hasta el tope): lo medido con ese origen, a
  precio (coste por 2,2). El mes en curso es el de ``partner_build_budget``, el
  mismo que frena.
- **Mensajes de Meta** (el negocio, a Meta; D30): la estimación diaria de
  ``messages.cost_usd`` (``daily_cost_snapshots``). Siempre «aprox.».

Lo medido (``usage_records``) se lee en una consulta bajo el rol de informes
(``console_reporting``), con el filtro de clientes del partner; el libro, en la
sesión del partner; y lo que es del cliente (la bolsa y la estimación de Meta),
cliente a cliente con su contexto puesto (garantía 1).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Final, Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import ClientWalletEntry, PartnerWallet, UsageLedger, UsageRecord
from nexus_api.db.models.daily_cost_snapshot import DailyCostSnapshot
from nexus_api.db.models.usage_record import USAGE_LINE_BY_SOURCE
from nexus_api.services.console_reporting import reporting_transaction
from nexus_api.services.wallet import fx
from nexus_api.services.wallet.bags import as_client

Line = Literal["conversations", "meta", "build", "companion"]
Payer = Literal["client_bag", "business_meta", "auphere", "account"]
LINES: Final[tuple[Line, ...]] = ("conversations", "meta", "build", "companion")
#: Quién paga cada partida (46.4).
PAYER: Final[dict[Line, Payer]] = {
    "conversations": "client_bag",
    "meta": "business_meta",
    "build": "auphere",
    "companion": "account",
}
#: Precio = coste por 2,2; en cien milésimas.
PRICE_MULTIPLIER: Final = Decimal("2.2")
UNITS: Final = Decimal(100_000)
BUILD_SOURCES: Final = tuple(s for s, line in USAGE_LINE_BY_SOURCE.items() if line == "build")

Cell = tuple[date, str, uuid.UUID | None]


@dataclass
class Spend:
    """El gasto de un periodo, en la moneda de la cuenta (cien milésimas)."""

    currency: str
    cells: dict[Cell, int] = field(default_factory=lambda: defaultdict(int))
    #: Hubo conversión de moneda o estimación: la cifra va con «aprox.».
    approx_lines: set[str] = field(default_factory=set)

    def total(
        self,
        *,
        lines: tuple[str, ...] | None = None,
        tenant: uuid.UUID | None = None,
        since: date | None = None,
    ) -> int:
        return sum(
            v
            for (day, line, tid), v in self.cells.items()
            if (lines is None or line in lines)
            and (tenant is None or tid == tenant)
            and (since is None or day >= since)
        )


def _utc_day(column: Any) -> sa.ColumnElement[date]:
    return sa.cast(sa.func.timezone("UTC", column), sa.Date)


async def account_currency(partner_id: uuid.UUID) -> str:
    async with get_sessionmaker()() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        found = await session.scalar(
            sa.select(PartnerWallet.currency).where(PartnerWallet.partner_id == partner_id)
        )
    return str(found or "USD")


@dataclass(frozen=True)
class Balances:
    """Las cifras de arriba de Consumo y del Panel (46.1, 48.1), en la moneda de la
    cuenta: lo asignable (sin el pool incluido) y lo que queda en las bolsas."""

    currency: str
    available: int
    in_bags: int
    #: Hay bolsas en otra moneda: «aprox.».
    approx: bool


async def balances(partner_id: uuid.UUID) -> Balances:
    from nexus_api.db.models import ClientWallet
    from nexus_api.services.wallet.bags import as_client, assignable, partner_tenants

    async with get_sessionmaker()() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        account = await session.scalar(
            sa.select(PartnerWallet).where(PartnerWallet.partner_id == partner_id)
        )
        currency = str(account.currency) if account is not None else "USD"
        # Cada bolsa es de su cliente: se suman una a una, por moneda.
        totals: dict[str, int] = defaultdict(int)
        for tenant_id in await partner_tenants(session, partner_id):
            await as_client(session, tenant_id)
            row = (
                await session.execute(
                    sa.select(ClientWallet.currency, ClientWallet.balance_micros).where(
                        ClientWallet.tenant_id == tenant_id
                    )
                )
            ).first()
            if row is not None:
                totals[str(row[0])] += int(row[1] or 0)
        rates = await _rates(session, set(totals), currency)
    return Balances(
        currency=currency,
        available=assignable(account) if account is not None else 0,
        in_bags=sum(fx.convert(total, rates[cur]) for cur, total in totals.items()),
        approx=any(cur != currency and total for cur, total in totals.items()),
    )


async def _rates(
    session: AsyncSession, currencies: set[str], to_currency: str
) -> dict[str, Decimal]:
    today = datetime.now(UTC).date()
    out: dict[str, Decimal] = {}
    for currency in currencies:
        try:
            out[currency], _ = await fx.rate_on(session, today, currency, to_currency)
        except fx.FxUnavailable:
            # Sin cambio publicado no se inventa uno: se lee 1:1 y va «aprox.».
            out[currency] = Decimal(1)
    return out


async def spend(
    reporting: AsyncSession,
    *,
    partner_id: uuid.UUID,
    tenant_ids: list[uuid.UUID],
    since: datetime,
    until: datetime,
    with_outside: bool,
    lines: tuple[str, ...] = LINES,
) -> Spend:
    """El gasto por día, partida y cliente entre ``since`` y ``until``.
    ``with_outside`` suma lo gastado sin cliente (el Companion)."""
    currency = await account_currency(partner_id)
    out = Spend(currency=currency)
    if not tenant_ids and not with_outside:
        return out

    async with get_sessionmaker()() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        if "conversations" in lines or "companion" in lines:
            who: list[sa.ColumnElement[bool]] = []
            if "conversations" in lines and tenant_ids:
                who.append(UsageLedger.tenant_id.in_(tenant_ids))
            if "companion" in lines and with_outside:
                who.append(UsageLedger.tenant_id.is_(None))
            if who:
                day = _utc_day(UsageLedger.created_at)
                for tid, d, total in (
                    await session.execute(
                        sa.select(UsageLedger.tenant_id, day, sa.func.sum(UsageLedger.qty))
                        .where(
                            UsageLedger.partner_id == partner_id,
                            UsageLedger.kind == "debit",
                            UsageLedger.created_at >= since,
                            UsageLedger.created_at < until,
                            sa.or_(*who),
                        )
                        .group_by(UsageLedger.tenant_id, day)
                    )
                ).all():
                    line = "companion" if tid is None else "conversations"
                    out.cells[(d, line, tid)] += int(total or 0)
        usd = (await _rates(session, {"USD"}, currency))["USD"]
        # La bolsa y la estimación de Meta son del cliente: una a una, con su
        # contexto puesto (garantía 1).
        bag_rows: list[tuple[uuid.UUID, date, str, int]] = []
        meta_rows: list[tuple[uuid.UUID, date, int]] = []
        for tid in tenant_ids if ("conversations" in lines or "meta" in lines) else []:
            await as_client(session, tid)
            if "conversations" in lines:
                day = _utc_day(ClientWalletEntry.created_at)
                for d, cur, total in (
                    await session.execute(
                        sa.select(
                            day,
                            ClientWalletEntry.currency,
                            sa.func.sum(-ClientWalletEntry.amount_micros),
                        )
                        .where(
                            ClientWalletEntry.tenant_id == tid,
                            ClientWalletEntry.kind == "debit_turn",
                            ClientWalletEntry.created_at >= since,
                            ClientWalletEntry.created_at < until,
                        )
                        .group_by(day, ClientWalletEntry.currency)
                    )
                ).all():
                    bag_rows.append((tid, d, str(cur), int(total or 0)))
            if "meta" in lines:
                for d, cost in (
                    await session.execute(
                        sa.select(
                            DailyCostSnapshot.day, sa.func.sum(DailyCostSnapshot.cost_usd_total)
                        )
                        .where(
                            DailyCostSnapshot.tenant_id == tid,
                            DailyCostSnapshot.day >= since.date(),
                            DailyCostSnapshot.day < until.date() + timedelta(days=1),
                        )
                        .group_by(DailyCostSnapshot.day)
                    )
                ).all():
                    meta_rows.append((tid, d, int(Decimal(str(cost or 0)) * UNITS)))
        rates = await _rates(session, {r[2] for r in bag_rows}, currency)
    for tid, d, cur, total in bag_rows:
        if cur != currency:
            out.approx_lines.add("conversations")
        out.cells[(d, "conversations", tid)] += fx.convert(total, rates[cur])
    if "meta" in lines and tenant_ids:
        out.approx_lines.add("meta")
    for tid, d, amount in meta_rows:
        out.cells[(d, "meta", tid)] += fx.convert(amount, usd)

    if not tenant_ids:
        return out
    if currency != "USD":
        out.approx_lines.update({"build", "meta"})
    async with reporting_transaction(reporting):
        if "build" in lines:
            day = _utc_day(UsageRecord.occurred_at)
            for tid, d, cost in (
                await reporting.execute(
                    sa.select(UsageRecord.tenant_id, day, sa.func.sum(UsageRecord.cost_usd))
                    .where(
                        UsageRecord.tenant_id.in_(tenant_ids),
                        UsageRecord.source.in_(BUILD_SOURCES),
                        UsageRecord.occurred_at >= since,
                        UsageRecord.occurred_at < until,
                    )
                    .group_by(UsageRecord.tenant_id, day)
                )
            ).all():
                price = Decimal(str(cost or 0)) * PRICE_MULTIPLIER * UNITS
                out.cells[(d, "build", tid)] += fx.convert(int(price), usd)
    return out


__all__ = [
    "BUILD_SOURCES",
    "LINES",
    "PAYER",
    "PRICE_MULTIPLIER",
    "Balances",
    "Line",
    "Payer",
    "Spend",
    "account_currency",
    "balances",
    "spend",
]
