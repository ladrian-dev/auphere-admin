"""La bolsa de cada cliente — spec 047, T156 (requisitos 43.1 a 43.14; research
D25 a D27).

La bolsa es **dinero apartado** para un cliente, en EUR o USD según su país. Cada
traspaso entre la cuenta del partner y una bolsa escribe, en una sola transacción:

- su fila en ``wallet_transfers`` (con su clave de idempotencia y el cambio del
  BCE del día);
- su asiento en el libro de la cuenta (``usage_ledger``: ``bag_assign`` saca,
  ``bag_return`` devuelve; el pool incluido no se asigna nunca);
- su asiento gemelo en la bolsa (``client_wallet_entries``).

Reglas:

- **Asignar** no deja la cuenta por debajo de su límite (lo comprado más la línea
  de crédito, nunca el pool) y repetir la misma clave no asigna dos veces.
- **Bajar** devuelve como mucho lo que queda en la bolsa. **Mover** es atómico, con
  la conversión a la vista. Lo no gastado se queda en la bolsa.
- **Rellenar** (día 1 UTC) sube cada bolsa con relleno hasta su cifra, primero las
  que menos días tienen; lo que no llegó se avisa.
- **El turno** se cobra de la bolsa; si cruza el cero, solo lo que quedaba (el resto
  lo absorbe Auphere, como hoy).
- **El mes** (UTC): al empezar, la base del 20 % es el saldo de ese momento; lo que
  se asigna en el mes la sube (D27).

Las tablas son de dos dueños (``data-model.md`` §7): el libro de la cuenta y los
traspasos son **del partner** (RLS por ``partner_id``); la bolsa, sus asientos y
las peticiones de saldo son **del cliente** (RLS con la política de cliente,
garantía 1). Todo corre en una sesión con el ``app.partner_id`` del partner, y
antes de tocar la bolsa de un cliente se pone su ``app.tenant_id``
(:func:`as_client`), que deja lo pendiente del cliente anterior ya escrito.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    ClientWallet,
    ClientWalletEntry,
    PartnerWallet,
    UsageLedger,
    WalletMigrationProposal,
    WalletTransfer,
)
from nexus_api.db.models.partner_wallet import BUCKET_PURCHASED, KIND_BAG_ASSIGN, KIND_BAG_RETURN
from nexus_api.services.wallet import fx

#: La zona euro: sus clientes tienen la bolsa en EUR; el resto, en USD (D26).
EUROZONE: Final = frozenset(
    {
        "AT", "BE", "HR", "CY", "EE", "FI", "FR", "DE", "GR", "IE", "IT", "LV", "LT", "LU",
        "MT", "NL", "PT", "SK", "SI", "ES",
    }
)  # fmt: skip


class WalletError(Exception):
    """Un error con su código de ``contracts/console-api.md`` §9."""

    def __init__(self, code: str, status: int = 409, **extra: Any) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.extra = extra


@dataclass(frozen=True)
class Debit:
    """Lo que cobró un turno de la bolsa (en su moneda) y cómo quedó."""

    spent: int
    balance_after: int
    emptied: bool
    duplicate: bool = False


async def as_client(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Pone el ``app.tenant_id`` del cliente dentro de la transacción del partner
    (las tablas de la bolsa son del cliente). Antes escribe lo pendiente: una
    fila de otro cliente no se puede escribir con el contexto de este."""
    from nexus_api.core.tenant_context import apply_tenant_to_session

    await session.flush()
    await apply_tenant_to_session(session, tenant_id)


async def partner_tenants(session: AsyncSession, partner_id: uuid.UUID) -> list[uuid.UUID]:
    """Los clientes del partner, para recorrer sus bolsas uno a uno."""
    from nexus_api.db.models import PartnerTenant

    return list(
        (
            await session.scalars(
                sa.select(PartnerTenant.tenant_id)
                .where(PartnerTenant.partner_id == partner_id)
                .order_by(PartnerTenant.tenant_id)
            )
        ).all()
    )


def month_of(now: datetime | None = None) -> date:
    stamp = (now or datetime.now(UTC)).astimezone(UTC)
    return stamp.date().replace(day=1)


def currency_for(country: str | None) -> str:
    return "EUR" if (country or "").upper() in EUROZONE else "USD"


async def bags_active(session: AsyncSession, partner_id: uuid.UUID) -> bool:
    """El partner cobra de las bolsas: está en la consola nueva y confirmó el
    reparto, o nunca tuvo asignaciones de antes (55.3). Hasta entonces sigue
    ``partner_allocations``."""
    from nexus_api.db.models import Partner, PartnerAllocation

    v2 = await session.scalar(
        sa.select(Partner.console_v2_enabled_at).where(Partner.id == partner_id)
    )
    if v2 is None:
        return False
    confirmed = await session.scalar(
        sa.select(WalletMigrationProposal.id)
        .where(
            WalletMigrationProposal.partner_id == partner_id,
            WalletMigrationProposal.confirmed_at.is_not(None),
        )
        .limit(1)
    )
    if confirmed is not None:
        return True
    legacy = await session.scalar(
        sa.select(PartnerAllocation.tenant_id)
        .where(PartnerAllocation.partner_id == partner_id)
        .limit(1)
    )
    return legacy is None


_GATE_FACTS = sa.text(
    """
    SELECT p.console_v2_enabled_at IS NOT NULL
           AND (EXISTS (SELECT 1 FROM wallet_migration_proposals w
                         WHERE w.partner_id = p.id AND w.confirmed_at IS NOT NULL)
                OR NOT EXISTS (SELECT 1 FROM partner_allocations a
                                WHERE a.partner_id = p.id)) AS with_bags,
           (SELECT c.balance_micros FROM client_wallets c
             WHERE c.tenant_id = :tenant AND c.partner_id = p.id) AS balance
      FROM partners p
     WHERE p.id = :partner
    """
)


async def gate_facts(
    session: AsyncSession, partner_id: uuid.UUID, tenant_id: uuid.UUID
) -> tuple[bool, int | None]:
    """Para la puerta del turno, en una consulta: si el partner cobra de las bolsas
    (la misma regla que :func:`bags_active`) y el saldo de la bolsa del cliente.
    Con el ``app.partner_id`` del partner puesto; aquí se pone el del cliente."""
    await as_client(session, tenant_id)
    row = (await session.execute(_GATE_FACTS, {"partner": partner_id, "tenant": tenant_id})).first()
    if row is None:
        return False, None
    return bool(row[0]), None if row[1] is None else int(row[1])


def _rearm(bag: ClientWallet) -> None:
    """Subió el saldo: los avisos de la bolsa vuelven a poder salir (44.5)."""
    bag.low_alerted_month = None
    bag.not_enough_alerted_month = None
    bag.empty_alerted_on = None


def _roll(bag: ClientWallet, now: datetime | None = None) -> None:
    """Empieza el mes nuevo: la base es el saldo de ese momento (D27)."""
    current = month_of(now)
    if bag.month != current:
        bag.month = current
        bag.month_base_micros = bag.balance_micros
        bag.month_spent_micros = 0


async def _country_of(tenant_id: uuid.UUID) -> str | None:
    """El país de la ficha del cliente. La ficha tiene RLS por cliente: desde la
    sesión del partner no se ve, así que se lee en la del cliente."""
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models.business import BusinessProfile

    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        country: str | None = await session.scalar(
            sa.select(BusinessProfile.country).where(BusinessProfile.tenant_id == tenant_id)
        )
    return country


def empty_bag(tenant_id: uuid.UUID, partner_id: uuid.UUID, currency: str) -> ClientWallet:
    """Una bolsa vacía en ``currency``. El alta la crea con la moneda elegida
    (requisito 43.3); ``bag_for_update`` la crea con la del país si aún no existe."""
    return ClientWallet(
        tenant_id=tenant_id,
        partner_id=partner_id,
        currency=currency,
        balance_micros=0,
        month=month_of(),
        month_base_micros=0,
        month_spent_micros=0,
    )


async def bag_for_update(
    session: AsyncSession, tenant_id: uuid.UUID, *, partner_id: uuid.UUID | None = None
) -> ClientWallet:
    """La bolsa del cliente, bloqueada; si aún no existe, la crea vacía (43.12).
    Deja puesto el ``app.tenant_id`` del cliente."""
    await as_client(session, tenant_id)
    bag = await session.scalar(
        sa.select(ClientWallet).where(ClientWallet.tenant_id == tenant_id).with_for_update()
    )
    if bag is None:
        if partner_id is None:
            raise WalletError("unknown_client", 404)
        country = await _country_of(tenant_id)
        bag = empty_bag(tenant_id, partner_id, currency_for(country))
        session.add(bag)
        await session.flush()
        bag = await session.scalar(
            sa.select(ClientWallet).where(ClientWallet.tenant_id == tenant_id).with_for_update()
        )
        assert bag is not None
    _roll(bag)
    return bag


async def _account(session: AsyncSession, partner_id: uuid.UUID) -> PartnerWallet:
    row = await session.scalar(
        sa.select(PartnerWallet).where(PartnerWallet.partner_id == partner_id).with_for_update()
    )
    if row is None:
        raise WalletError("insufficient_account", available_micros=0)
    return row


def assignable(account: PartnerWallet) -> int:
    """Lo que la cuenta puede apartar: lo comprado más lo que queda de la línea de
    crédito. El pool incluido no se asigna (43.4)."""
    from nexus_api.metering.wallet import _snapshot

    return _snapshot(account).spendable_purchased


async def _existing(
    session: AsyncSession, partner_id: uuid.UUID, key: str
) -> WalletTransfer | None:
    found: WalletTransfer | None = await session.scalar(
        sa.select(WalletTransfer).where(
            WalletTransfer.partner_id == partner_id, WalletTransfer.idempotency_key == key
        )
    )
    return found


def _entry(
    bag: ClientWallet,
    *,
    kind: str,
    amount: int,
    transfer: WalletTransfer | None = None,
    usage_ref: str | None = None,
    agent_id: uuid.UUID | None = None,
) -> ClientWalletEntry:
    return ClientWalletEntry(
        tenant_id=bag.tenant_id,
        partner_id=bag.partner_id,
        transfer_id=transfer.id if transfer is not None else None,
        kind=kind,
        amount_micros=amount,
        balance_after_micros=bag.balance_micros,
        currency=bag.currency,
        usage_ref=usage_ref,
        agent_id=agent_id,
    )


async def assign(
    session: AsyncSession,
    *,
    partner_id: uuid.UUID,
    tenant_id: uuid.UUID,
    amount: int,
    idempotency_key: str,
    actor: str,
    kind: str = "assign",
    in_bag_currency: bool = False,
) -> WalletTransfer:
    """Apartar ``amount`` para el cliente (43.3): en la moneda de la cuenta o, con
    ``in_bag_currency``, en la de la bolsa (lo que la consola enseña)."""
    if amount <= 0:
        raise WalletError("invalid_amount", 422)
    done = await _existing(session, partner_id, idempotency_key)
    if done is not None:
        return done
    account = await _account(session, partner_id)
    bag = await bag_for_update(session, tenant_id, partner_id=partner_id)
    rate, fx_date = await fx.rate_on(
        session, datetime.now(UTC).date(), account.currency, bag.currency
    )
    if in_bag_currency:
        client_amount = amount
        amount = fx.convert(client_amount, Decimal(1) / rate)
    else:
        client_amount = fx.convert(amount, rate)
    available = assignable(account)
    if amount > available:
        raise WalletError(
            "insufficient_account",
            available_micros=available,
            currency=account.currency,
            missing_micros=amount - available,
        )
    transfer = WalletTransfer(
        id=uuid.uuid4(),
        partner_id=partner_id,
        kind=kind,
        to_tenant_id=tenant_id,
        partner_amount_micros=amount,
        partner_currency=account.currency,
        client_amount_micros=client_amount,
        client_currency=bag.currency,
        fx_rate=rate,
        fx_date=fx_date,
        idempotency_key=idempotency_key,
        actor_id=actor,
    )
    session.add(transfer)
    # Sin relación ORM entre los dos: el traspaso va antes que sus asientos (FK).
    await session.flush()
    account.purchased_remaining = int(account.purchased_remaining) - amount
    session.add(
        UsageLedger(
            partner_id=partner_id,
            tenant_id=tenant_id,
            qty=amount,
            bucket=BUCKET_PURCHASED,
            kind=KIND_BAG_ASSIGN,
            idempotency_key=f"bag:{transfer.id}",
            fx=rate,
        )
    )
    bag.balance_micros += client_amount
    bag.month_base_micros += client_amount
    bag.revision += 1
    _rearm(bag)
    session.add(
        _entry(
            bag,
            kind=kind if kind in {"refill", "migration"} else "assign",
            amount=client_amount,
            transfer=transfer,
        )
    )
    await session.flush()
    return transfer


async def lower(
    session: AsyncSession,
    *,
    partner_id: uuid.UUID,
    tenant_id: uuid.UUID,
    amount: int,
    idempotency_key: str,
    actor: str,
) -> WalletTransfer:
    """Devolver a la cuenta ``amount`` (en la moneda de la bolsa): como mucho lo
    que queda (43.5)."""
    if amount <= 0:
        raise WalletError("invalid_amount", 422)
    done = await _existing(session, partner_id, idempotency_key)
    if done is not None:
        return done
    bag = await bag_for_update(session, tenant_id, partner_id=partner_id)
    if amount > bag.balance_micros:
        raise WalletError("bag_below_spent", available_micros=bag.balance_micros)
    account = await _account(session, partner_id)
    rate, fx_date = await fx.rate_on(
        session, datetime.now(UTC).date(), bag.currency, account.currency
    )
    back = fx.convert(amount, rate)
    transfer = WalletTransfer(
        id=uuid.uuid4(),
        partner_id=partner_id,
        kind="lower",
        from_tenant_id=tenant_id,
        partner_amount_micros=back,
        partner_currency=account.currency,
        client_amount_micros=amount,
        client_currency=bag.currency,
        fx_rate=rate,
        fx_date=fx_date,
        idempotency_key=idempotency_key,
        actor_id=actor,
    )
    session.add(transfer)
    # Sin relación ORM entre los dos: el traspaso va antes que sus asientos (FK).
    await session.flush()
    bag.balance_micros -= amount
    bag.revision += 1
    account.purchased_remaining = int(account.purchased_remaining) + back
    if back > 0:
        session.add(
            UsageLedger(
                partner_id=partner_id,
                tenant_id=tenant_id,
                qty=back,
                bucket=BUCKET_PURCHASED,
                kind=KIND_BAG_RETURN,
                idempotency_key=f"bag:{transfer.id}",
                fx=rate,
            )
        )
    session.add(_entry(bag, kind="lower", amount=-amount, transfer=transfer))
    await session.flush()
    return transfer


async def move(
    session: AsyncSession,
    *,
    partner_id: uuid.UUID,
    from_tenant_id: uuid.UUID,
    to_tenant_id: uuid.UUID,
    amount: int,
    idempotency_key: str,
    actor: str,
) -> WalletTransfer:
    """Mover ``amount`` (en la moneda de la bolsa de origen) entre dos bolsas del
    partner, en una sola transacción y con la conversión a la vista (43.6)."""
    if amount <= 0:
        raise WalletError("invalid_amount", 422)
    if from_tenant_id == to_tenant_id:
        raise WalletError("same_client", 422)
    done = await _existing(session, partner_id, idempotency_key)
    if done is not None:
        return done
    # Siempre en el mismo orden: dos movimientos cruzados no se bloquean.
    first, second = sorted([from_tenant_id, to_tenant_id], key=str)
    bags = {
        first: await bag_for_update(session, first, partner_id=partner_id),
        second: await bag_for_update(session, second, partner_id=partner_id),
    }
    source, target = bags[from_tenant_id], bags[to_tenant_id]
    if amount > source.balance_micros:
        raise WalletError("bag_below_spent", available_micros=source.balance_micros)
    rate, fx_date = await fx.rate_on(
        session, datetime.now(UTC).date(), source.currency, target.currency
    )
    received = fx.convert(amount, rate)
    transfer = WalletTransfer(
        id=uuid.uuid4(),
        partner_id=partner_id,
        kind="move",
        from_tenant_id=from_tenant_id,
        to_tenant_id=to_tenant_id,
        partner_amount_micros=0,
        partner_currency=source.currency,
        client_amount_micros=received,
        client_currency=target.currency,
        fx_rate=rate,
        fx_date=fx_date,
        idempotency_key=idempotency_key,
        actor_id=actor,
    )
    session.add(transfer)
    # Sin relación ORM entre los dos: el traspaso va antes que sus asientos (FK).
    await session.flush()
    # Cada bolsa con su cliente puesto: la de origen, y después la de destino.
    await as_client(session, from_tenant_id)
    source.balance_micros -= amount
    source.revision += 1
    session.add(_entry(source, kind="move_out", amount=-amount, transfer=transfer))
    await as_client(session, to_tenant_id)
    target.balance_micros += received
    target.month_base_micros += received
    target.revision += 1
    _rearm(target)
    session.add(_entry(target, kind="move_in", amount=received, transfer=transfer))
    await session.flush()
    return transfer


async def change_currency(
    session: AsyncSession, *, partner_id: uuid.UUID, tenant_id: uuid.UUID, currency: str, actor: str
) -> ClientWallet:
    """Cambiar la moneda de una bolsa convierte su saldo al cambio del día (43.3);
    la consola lo confirma antes."""
    if currency not in {"EUR", "USD"}:
        raise WalletError("invalid_currency", 422)
    bag = await bag_for_update(session, tenant_id, partner_id=partner_id)
    if bag.currency == currency:
        return bag
    rate, fx_date = await fx.rate_on(session, datetime.now(UTC).date(), bag.currency, currency)
    old_balance = bag.balance_micros
    new_balance = fx.convert(old_balance, rate)
    transfer = WalletTransfer(
        id=uuid.uuid4(),
        partner_id=partner_id,
        kind="currency_change",
        from_tenant_id=tenant_id,
        to_tenant_id=tenant_id,
        partner_currency=bag.currency,
        client_amount_micros=new_balance,
        client_currency=currency,
        fx_rate=rate,
        fx_date=fx_date,
        idempotency_key=f"currency:{tenant_id}:{bag.revision}",
        actor_id=actor,
    )
    session.add(transfer)
    # Sin relación ORM entre los dos: el traspaso va antes que sus asientos (FK).
    await session.flush()
    bag.currency = currency
    bag.balance_micros = new_balance
    bag.month_base_micros = fx.convert(bag.month_base_micros, rate)
    bag.month_spent_micros = fx.convert(bag.month_spent_micros, rate)
    if bag.refill_up_to_micros:
        bag.refill_up_to_micros = fx.convert(bag.refill_up_to_micros, rate) or None
    bag.revision += 1
    session.add(
        _entry(bag, kind="currency_change", amount=new_balance - old_balance, transfer=transfer)
    )
    await session.flush()
    return bag


async def debit_turn(
    session: AsyncSession,
    *,
    partner_id: uuid.UUID,
    tenant_id: uuid.UUID,
    amount_usd: int,
    usage_ref: str,
    agent_id: uuid.UUID | None,
) -> Debit:
    """Cobrar un turno (``amount_usd`` en cien milésimas de USD, la unidad de la
    medición) de la bolsa, en su moneda. Si cruza el cero, solo lo que quedaba; la
    misma ``usage_ref`` no cobra dos veces (43.8)."""
    await as_client(session, tenant_id)
    seen = await session.scalar(
        sa.select(ClientWalletEntry.amount_micros).where(ClientWalletEntry.usage_ref == usage_ref)
    )
    bag = await bag_for_update(session, tenant_id, partner_id=partner_id)
    if seen is not None:
        return Debit(
            spent=-int(seen), balance_after=bag.balance_micros, emptied=False, duplicate=True
        )
    rate, _fx_date = await fx.rate_on(session, datetime.now(UTC).date(), "USD", bag.currency)
    wanted = fx.convert(amount_usd, rate)
    spent = min(wanted, bag.balance_micros)
    was = bag.balance_micros
    bag.balance_micros -= spent
    bag.month_spent_micros += spent
    session.add(
        _entry(bag, kind="debit_turn", amount=-spent, usage_ref=usage_ref, agent_id=agent_id)
    )
    await session.flush()
    return Debit(
        spent=spent, balance_after=bag.balance_micros, emptied=was > 0 and bag.balance_micros == 0
    )


async def currency_of(partner_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    """La moneda de la bolsa del cliente: la guardada o, si aún no tiene, la de su
    país (43.3)."""
    from nexus_api.core.partner_context import apply_partner_to_session
    from nexus_api.db.base import get_sessionmaker

    async with get_sessionmaker()() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        await as_client(session, tenant_id)
        stored = await session.scalar(
            sa.select(ClientWallet.currency).where(ClientWallet.tenant_id == tenant_id)
        )
    return str(stored) if stored else currency_for(await _country_of(tenant_id))


async def balance_left(partner_id: uuid.UUID, tenant_id: uuid.UUID) -> tuple[int, str] | None:
    """Lo que queda en la bolsa del cliente, en su moneda, o ``None`` si nada."""
    from nexus_api.core.partner_context import apply_partner_to_session
    from nexus_api.db.base import get_sessionmaker

    async with get_sessionmaker()() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        await as_client(session, tenant_id)
        row = (
            await session.execute(
                sa.select(ClientWallet.balance_micros, ClientWallet.currency).where(
                    ClientWallet.tenant_id == tenant_id
                )
            )
        ).first()
    if row is None or row[0] <= 0:
        return None
    return int(row[0]), str(row[1])


async def return_all(*, partner_id: uuid.UUID, tenant_id: uuid.UUID, actor: str) -> int:
    """Antes de borrar un cliente, su bolsa vuelve entera a la cuenta (43.13).

    En su propia transacción y antes del borrado: si el borrado fallara después,
    el dinero ya está a salvo en la cuenta y el cliente sigue archivado con la
    bolsa a cero. Devuelve lo devuelto, en la moneda de la bolsa."""
    from nexus_api.core.partner_context import apply_partner_to_session
    from nexus_api.db.base import get_sessionmaker

    async with get_sessionmaker()() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        await as_client(session, tenant_id)
        bag = await session.scalar(
            sa.select(ClientWallet).where(ClientWallet.tenant_id == tenant_id).with_for_update()
        )
        if bag is None or bag.balance_micros <= 0:
            return 0
        amount = bag.balance_micros
        await lower(
            session,
            partner_id=partner_id,
            tenant_id=tenant_id,
            amount=amount,
            idempotency_key=f"delete:{tenant_id}",
            actor=actor,
        )
    return amount


async def refill_all(
    session: AsyncSession, *, partner_id: uuid.UUID, now: datetime | None = None
) -> list[dict[str, Any]]:
    """El relleno del día 1 UTC (43.7): cada bolsa con relleno sube hasta su cifra,
    primero las que antes se quedarían sin saldo; lo que no llegó se devuelve
    para avisar. Idempotente por mes."""
    month = month_of(now)
    # Primero, con quién: las bolsas con relleno y cuántos días les quedan.
    order: list[tuple[float, uuid.UUID]] = []
    for tenant_id in await partner_tenants(session, partner_id):
        await as_client(session, tenant_id)
        found = await session.scalar(
            sa.select(ClientWallet).where(
                ClientWallet.tenant_id == tenant_id, ClientWallet.refill_up_to_micros.is_not(None)
            )
        )
        if found is None:
            continue
        pace = found.month_spent_micros / max(1, datetime.now(UTC).day)
        order.append((found.balance_micros / pace if pace else float("inf"), tenant_id))

    shortfalls: list[dict[str, Any]] = []
    for _days, tenant_id in sorted(order, key=lambda o: (o[0], str(o[1]))):
        bag = await bag_for_update(session, tenant_id, partner_id=partner_id)
        _roll(bag, now)
        need = int(bag.refill_up_to_micros or 0) - bag.balance_micros
        if need <= 0:
            continue
        account = await _account(session, partner_id)
        rate, _ = await fx.rate_on(session, month, bag.currency, account.currency)
        cost = fx.convert(need, rate)
        available = assignable(account)
        if available <= 0:
            shortfalls.append({"tenant_id": str(bag.tenant_id), "missing_micros": need})
            continue
        paid = min(cost, available)
        await assign(
            session,
            partner_id=partner_id,
            tenant_id=bag.tenant_id,
            amount=paid,
            idempotency_key=f"refill:{month.isoformat()}:{bag.tenant_id}",
            actor="system:refill",
            kind="refill",
        )
        if paid < cost:
            # Lo que faltó, en la moneda de la bolsa (el aviso lo dice así).
            got = fx.convert(paid, Decimal(1) / rate)
            shortfalls.append({"tenant_id": str(bag.tenant_id), "missing_micros": need - got})
    return shortfalls


__all__ = [
    "EUROZONE",
    "Debit",
    "WalletError",
    "as_client",
    "assign",
    "assignable",
    "bag_for_update",
    "bags_active",
    "balance_left",
    "change_currency",
    "currency_for",
    "currency_of",
    "debit_turn",
    "gate_facts",
    "lower",
    "month_of",
    "move",
    "partner_tenants",
    "refill_all",
    "return_all",
]
