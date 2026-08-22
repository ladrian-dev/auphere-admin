"""Libro Fase 3 — saldo, asignación y débito.

Unidad: ``quota_tokens()`` (C3). Este módulo no cambia esa política;
solo mueve enteros de cuota entre cubos.

Fail-closed: si el libro no se puede leer, el saldo es 0 y no hay LLM.
Se gasta ``included`` (si no ha caducado) y después ``purchased``.
El débito es idempotente por ``idempotency_key``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.partner_wallet import (
    BUCKET_INCLUDED,
    BUCKET_PURCHASED,
    PartnerAllocation,
    PartnerWallet,
    UsageLedger,
)
from nexus_api.db.models.tenant import Tenant

log = structlog.get_logger(__name__)

_PARTNER_OF_TENANT = sa.text("SELECT partner_id FROM partner_tenants WHERE tenant_id = :t LIMIT 1")


class OverAllocation(Exception):
    """La suma de caps superaría el wallet (included efectivo + purchased)."""


@dataclass(frozen=True)
class WalletSnapshot:
    partner_id: uuid.UUID
    included_remaining: int
    purchased_remaining: int
    included_expires_at: datetime | None
    available: int

    @property
    def empty(self) -> bool:
        return self.available <= 0


@dataclass(frozen=True)
class DebitResult:
    spent: int
    from_included: int
    from_purchased: int
    duplicate: bool


def _now() -> datetime:
    return datetime.now(UTC)


def effective_included(
    remaining: int, expires_at: datetime | None, *, now: datetime | None = None
) -> int:
    """Included que todavía se puede gastar. Caducado = 0."""
    if remaining <= 0:
        return 0
    if expires_at is None:
        return 0
    stamp = now or _now()
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= stamp:
        return 0
    return remaining


def split_spend(qty: int, included: int, purchased: int) -> tuple[int, int]:
    """Parte ``qty``: included primero, luego purchased. Nunca negativo."""
    if qty <= 0:
        return 0, 0
    take = min(qty, max(0, included) + max(0, purchased))
    from_included = min(take, max(0, included))
    from_purchased = take - from_included
    return from_included, from_purchased


def _as_int(value: Any) -> int:
    if value is None:
        return 0
    return int(value)


async def partner_id_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID | None:
    """Partner dueño del tenant, o None. No lanza."""
    found = await session.scalar(_PARTNER_OF_TENANT, {"t": str(tenant_id)})
    if found is not None:
        return uuid.UUID(str(found))
    row = await session.scalar(sa.select(Tenant.partner_id).where(Tenant.id == tenant_id))
    if row is None:
        return None
    return uuid.UUID(str(row))


def _snapshot(row: PartnerWallet, *, now: datetime | None = None) -> WalletSnapshot:
    included = effective_included(row.included_remaining, row.included_expires_at, now=now)
    purchased = max(0, _as_int(row.purchased_remaining))
    return WalletSnapshot(
        partner_id=row.partner_id,
        included_remaining=included,
        purchased_remaining=purchased,
        included_expires_at=row.included_expires_at,
        available=included + purchased,
    )


async def _load_wallet_for_update(
    session: AsyncSession, partner_id: uuid.UUID
) -> PartnerWallet | None:
    row = await session.scalar(
        sa.select(PartnerWallet).where(PartnerWallet.partner_id == partner_id).with_for_update()
    )
    return row if isinstance(row, PartnerWallet) else None


def _expire_included(row: PartnerWallet, *, now: datetime | None = None) -> None:
    stamp = now or _now()
    expired = effective_included(row.included_remaining, row.included_expires_at, now=stamp) == 0
    if (
        expired
        and row.included_remaining
        and (row.included_expires_at is None or row.included_expires_at <= stamp)
    ):
        row.included_remaining = 0
        row.updated_at = stamp


async def read_wallet(partner_id: uuid.UUID) -> WalletSnapshot | None:
    """Saldo bajo RLS. None si no hay fila. None (y log) si el libro no se lee."""
    try:
        sm = get_sessionmaker()
        async with sm() as session, session.begin():
            await apply_partner_to_session(session, partner_id)
            row = await session.get(PartnerWallet, partner_id)
            if row is None:
                return None
            return _snapshot(row)
    except Exception as exc:
        log.warning("wallet.unreadable", partner_id=str(partner_id), error=str(exc))
        return None


async def companion_wallet_remaining(partner_id: uuid.UUID) -> int:
    """Saldo del cubo reserva (wallet) que gasta el Companion."""
    snap = await read_wallet(partner_id)
    if snap is None:
        return 0
    return snap.available


async def companion_allocation_remaining(partner_id: uuid.UUID, tenant_id: uuid.UUID | None) -> int:
    """``remaining`` de la asignación del cliente del hilo.

    Sin tenant, sin fila, remaining 0 o libro ilegible → 0 (fail-closed).
    No mira ``partner_wallets``: ese cubo es reserva / no asignado.
    """
    if tenant_id is None:
        return 0
    try:
        sm = get_sessionmaker()
        async with sm() as session, session.begin():
            await apply_partner_to_session(session, partner_id)
            remaining = await session.scalar(
                sa.select(PartnerAllocation.remaining).where(
                    PartnerAllocation.partner_id == partner_id,
                    PartnerAllocation.tenant_id == tenant_id,
                )
            )
            return max(0, _as_int(remaining))
    except Exception as exc:
        log.warning(
            "wallet.allocation_unreadable",
            partner_id=str(partner_id),
            tenant_id=str(tenant_id),
            error=str(exc),
        )
        return 0


async def allow_channel_turn(tenant_id: uuid.UUID) -> bool:
    """¿Puede el canal abrir el pipeline?

    Sin partner (tenant directo / tests legacy) → sí, el libro no aplica.
    Con partner: wallet 0, sin asignación, asignación 0 o libro ilegible → no.
    """
    try:
        sm = get_sessionmaker()
        async with sm() as session, session.begin():
            partner_id = await partner_id_for_tenant(session, tenant_id)
            if partner_id is None:
                return True
            await apply_partner_to_session(session, partner_id)
            row = await session.get(PartnerWallet, partner_id)
            if row is None:
                return False
            if _snapshot(row).empty:
                return False
            alloc = await session.scalar(
                sa.select(PartnerAllocation).where(
                    PartnerAllocation.partner_id == partner_id,
                    PartnerAllocation.tenant_id == tenant_id,
                )
            )
            return not (alloc is None or _as_int(alloc.remaining) <= 0)
    except Exception as exc:
        log.warning("wallet.channel_unreadable", tenant_id=str(tenant_id), error=str(exc))
        return False


async def add_purchased(partner_id: uuid.UUID, qty: int) -> WalletSnapshot:
    """Recarga manual: suma al cubo purchased. No caduca. Staging / admin."""
    if qty <= 0:
        raise ValueError("top-up qty must be > 0")
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        row = await _load_wallet_for_update(session, partner_id)
        if row is None:
            row = PartnerWallet(
                partner_id=partner_id,
                included_remaining=0,
                purchased_remaining=0,
            )
            session.add(row)
            await session.flush()
        row.purchased_remaining = _as_int(row.purchased_remaining) + qty
        row.updated_at = _now()
        await session.flush()
        return _snapshot(row)


async def set_allocation(
    partner_id: uuid.UUID, tenant_id: uuid.UUID, cap: int
) -> PartnerAllocation:
    """Crea o actualiza el cap de un tenant. Suma de caps ≤ wallet."""
    if cap < 0:
        raise ValueError("cap must be >= 0")
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        wallet = await _load_wallet_for_update(session, partner_id)
        if wallet is None:
            raise OverAllocation("no wallet")
        available = _snapshot(wallet).available
        others = _as_int(
            await session.scalar(
                sa.select(sa.func.coalesce(sa.func.sum(PartnerAllocation.cap), 0)).where(
                    PartnerAllocation.partner_id == partner_id,
                    PartnerAllocation.tenant_id != tenant_id,
                )
            )
        )
        if others + cap > available:
            raise OverAllocation(f"sum of caps {others + cap} exceeds wallet {available}")
        row = await session.scalar(
            sa.select(PartnerAllocation)
            .where(
                PartnerAllocation.partner_id == partner_id,
                PartnerAllocation.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        if row is None:
            row = PartnerAllocation(
                partner_id=partner_id,
                tenant_id=tenant_id,
                cap=cap,
                remaining=cap,
            )
            session.add(row)
        else:
            delta = cap - _as_int(row.cap)
            row.cap = cap
            if delta < 0:
                row.remaining = min(_as_int(row.remaining), cap)
            else:
                row.remaining = _as_int(row.remaining) + delta
            row.updated_at = _now()
        await session.flush()
        await session.refresh(row)
        return row


async def debit_wallet(
    *,
    partner_id: uuid.UUID,
    qty: int,
    idempotency_key: str,
    tenant_id: uuid.UUID | None = None,
    usage_record_id: uuid.UUID | None = None,
    companion_run_id: uuid.UUID | None = None,
) -> DebitResult:
    """Debita ``qty`` (unidad C3). Included primero. Misma clave = no dobla.

    Si no queda nada, ``spent=0`` y no escribe asiento (no se gasta sin cuota).
    Un débito partido en dos cubos usa ``{key}:included`` y ``{key}:purchased``.
    """
    if qty <= 0:
        return DebitResult(spent=0, from_included=0, from_purchased=0, duplicate=False)
    try:
        return await _debit_locked(
            partner_id=partner_id,
            qty=qty,
            idempotency_key=idempotency_key,
            tenant_id=tenant_id,
            usage_record_id=usage_record_id,
            companion_run_id=companion_run_id,
        )
    except Exception as exc:
        if isinstance(exc, IntegrityError):
            return DebitResult(spent=0, from_included=0, from_purchased=0, duplicate=True)
        log.warning(
            "wallet.debit_failed",
            partner_id=str(partner_id),
            key=idempotency_key,
            error=str(exc),
        )
        raise


async def _debit_locked(
    *,
    partner_id: uuid.UUID,
    qty: int,
    idempotency_key: str,
    tenant_id: uuid.UUID | None,
    usage_record_id: uuid.UUID | None,
    companion_run_id: uuid.UUID | None,
) -> DebitResult:
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        already = await session.scalar(
            sa.select(sa.func.count())
            .select_from(UsageLedger)
            .where(
                UsageLedger.idempotency_key.in_(
                    (f"{idempotency_key}:included", f"{idempotency_key}:purchased")
                )
            )
        )
        if _as_int(already) > 0:
            return DebitResult(spent=0, from_included=0, from_purchased=0, duplicate=True)

        wallet = await _load_wallet_for_update(session, partner_id)
        if wallet is None:
            return DebitResult(spent=0, from_included=0, from_purchased=0, duplicate=False)
        _expire_included(wallet)
        snap = _snapshot(wallet)
        from_included, from_purchased = split_spend(
            qty, snap.included_remaining, snap.purchased_remaining
        )
        spent = from_included + from_purchased
        if spent <= 0:
            return DebitResult(spent=0, from_included=0, from_purchased=0, duplicate=False)

        if from_included:
            wallet.included_remaining = snap.included_remaining - from_included
        if from_purchased:
            wallet.purchased_remaining = snap.purchased_remaining - from_purchased
        wallet.updated_at = _now()

        if tenant_id is not None:
            alloc = await session.scalar(
                sa.select(PartnerAllocation)
                .where(
                    PartnerAllocation.partner_id == partner_id,
                    PartnerAllocation.tenant_id == tenant_id,
                )
                .with_for_update()
            )
            if alloc is not None:
                alloc.remaining = max(0, _as_int(alloc.remaining) - spent)
                alloc.updated_at = _now()

        if from_included:
            session.add(
                UsageLedger(
                    partner_id=partner_id,
                    tenant_id=tenant_id,
                    qty=from_included,
                    bucket=BUCKET_INCLUDED,
                    usage_record_id=usage_record_id,
                    companion_run_id=companion_run_id,
                    idempotency_key=f"{idempotency_key}:included",
                    fx=None,
                )
            )
        if from_purchased:
            session.add(
                UsageLedger(
                    partner_id=partner_id,
                    tenant_id=tenant_id,
                    qty=from_purchased,
                    bucket=BUCKET_PURCHASED,
                    usage_record_id=usage_record_id,
                    companion_run_id=companion_run_id,
                    idempotency_key=f"{idempotency_key}:purchased",
                    fx=None,
                )
            )
        await session.flush()
        return DebitResult(
            spent=spent,
            from_included=from_included,
            from_purchased=from_purchased,
            duplicate=False,
        )


async def debit_allocation(
    *,
    partner_id: uuid.UUID,
    tenant_id: uuid.UUID,
    qty: int,
    idempotency_key: str,
    usage_record_id: uuid.UUID | None = None,
    companion_run_id: uuid.UUID | None = None,
) -> DebitResult:
    """Debita solo ``partner_allocations.remaining`` del cliente.

    No toca ``partner_wallets`` (reserva). Misma clave = no dobla.
    Si no hay asignación o remaining es 0, ``spent=0`` y no escribe asiento.
    """
    if qty <= 0:
        return DebitResult(spent=0, from_included=0, from_purchased=0, duplicate=False)
    try:
        return await _debit_allocation_locked(
            partner_id=partner_id,
            tenant_id=tenant_id,
            qty=qty,
            idempotency_key=idempotency_key,
            usage_record_id=usage_record_id,
            companion_run_id=companion_run_id,
        )
    except Exception as exc:
        if isinstance(exc, IntegrityError):
            return DebitResult(spent=0, from_included=0, from_purchased=0, duplicate=True)
        log.warning(
            "wallet.allocation_debit_failed",
            partner_id=str(partner_id),
            tenant_id=str(tenant_id),
            key=idempotency_key,
            error=str(exc),
        )
        raise


async def _debit_allocation_locked(
    *,
    partner_id: uuid.UUID,
    tenant_id: uuid.UUID,
    qty: int,
    idempotency_key: str,
    usage_record_id: uuid.UUID | None,
    companion_run_id: uuid.UUID | None,
) -> DebitResult:
    sm = get_sessionmaker()
    key = f"{idempotency_key}:allocation"
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        already = await session.scalar(
            sa.select(sa.func.count())
            .select_from(UsageLedger)
            .where(UsageLedger.idempotency_key == key)
        )
        if _as_int(already) > 0:
            return DebitResult(spent=0, from_included=0, from_purchased=0, duplicate=True)

        alloc = await session.scalar(
            sa.select(PartnerAllocation)
            .where(
                PartnerAllocation.partner_id == partner_id,
                PartnerAllocation.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        if alloc is None:
            return DebitResult(spent=0, from_included=0, from_purchased=0, duplicate=False)
        spent = min(qty, max(0, _as_int(alloc.remaining)))
        if spent <= 0:
            return DebitResult(spent=0, from_included=0, from_purchased=0, duplicate=False)

        alloc.remaining = _as_int(alloc.remaining) - spent
        alloc.updated_at = _now()
        session.add(
            UsageLedger(
                partner_id=partner_id,
                tenant_id=tenant_id,
                qty=spent,
                bucket=BUCKET_INCLUDED,
                usage_record_id=usage_record_id,
                companion_run_id=companion_run_id,
                idempotency_key=key,
                fx=None,
            )
        )
        await session.flush()
        return DebitResult(
            spent=spent,
            from_included=0,
            from_purchased=0,
            duplicate=False,
        )
