"""Admin — the money of the path partner (spec 033).

Everything a person reads or writes here is US$ cents, converted with the one
conversion in ``billing/pricing.py``. The ``partner_id`` of the path is the
source of truth and fixes ``app.partner_id`` like the FORCE-RLS book.

A top-up is one transaction — balance, ledger entry and audit naming the
operator — and is idempotent by the key the panel's form generated.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.operator import operator_actor, require_operator
from nexus_api.api.admin.partners import _get_partner_or_404
from nexus_api.api.deps import get_db_session
from nexus_api.billing.pricing import cents_to_credits, credits_to_cents
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import OperatorAccount
from nexus_api.db.models.partner_wallet import (
    KIND_ALLOCATION_LEGACY,
    KIND_CREDIT_ADMIN,
    PartnerAllocation,
    UsageLedger,
)
from nexus_api.db.models.tenant import Tenant
from nexus_api.metering.wallet import (
    WalletSnapshot,
    add_purchased,
    read_wallet,
    reconcile_purchased,
)
from nexus_api.repositories import AuditRepository
from nexus_api.schemas.admin_wallet import (
    AdminLedgerOut,
    AdminPurchasedIn,
    AdminReconcileOut,
    AdminWalletOut,
)

router = APIRouter(prefix="/partners", dependencies=[Depends(require_admin_token)])
log = structlog.get_logger(__name__)

_ADMIN_PURCHASED_PREFIX = "admin_purchased:"


def _empty() -> AdminWalletOut:
    return AdminWalletOut(
        included_cents=0,
        purchased_cents=0,
        available_cents=0,
        assigned_cents=0,
        included_expires_at=None,
        exhausted=True,
    )


async def _sum_caps(partner_id: uuid.UUID) -> int:
    """Suma de caps del partner bajo RLS. Ilegible → 0 (fail-closed)."""
    try:
        sm = get_sessionmaker()
        async with sm() as session, session.begin():
            await apply_partner_to_session(session, partner_id)
            total = await session.scalar(
                sa.select(sa.func.coalesce(sa.func.sum(PartnerAllocation.cap), 0)).where(
                    PartnerAllocation.partner_id == partner_id,
                )
            )
        return int(total or 0)
    except Exception as exc:
        log.warning("admin.wallet.caps_unreadable", partner_id=str(partner_id), error=str(exc))
        return 0


def _out(snap: WalletSnapshot, caps: int, *, duplicate: bool = False) -> AdminWalletOut:
    # Balances round DOWN (never show money that is not there): the same
    # rule and the same function as the console (``credits_to_cents``).
    return AdminWalletOut(
        included_cents=credits_to_cents(snap.included_remaining),
        purchased_cents=credits_to_cents(snap.purchased_remaining),
        available_cents=credits_to_cents(snap.available),
        assigned_cents=credits_to_cents(caps),
        included_expires_at=snap.included_expires_at,
        exhausted=snap.purchased_remaining <= 0,
        duplicate=duplicate,
    )


async def _wallet_out(partner_id: uuid.UUID) -> AdminWalletOut:
    snap = await read_wallet(partner_id)
    if snap is None:
        return _empty()
    return _out(snap, await _sum_caps(partner_id))


@router.get("/{partner_id}/wallet", response_model=AdminWalletOut)
async def get_partner_wallet(
    partner_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> AdminWalletOut:
    """Saldo C3 del partner del path. Partner ausente → 404."""
    async with session.begin():
        await _get_partner_or_404(session, partner_id)
        await apply_partner_to_session(session, partner_id)
    return await _wallet_out(partner_id)


@router.get("/{partner_id}/wallet/ledger", response_model=list[AdminLedgerOut])
async def get_partner_wallet_ledger(
    partner_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AdminLedgerOut]:
    """The partner's entries, newest first, each with what it is (``kind``).
    The legacy cap-only entries of the double cap debit are not money and
    are left out."""
    async with session.begin():
        await _get_partner_or_404(session, partner_id)
        await apply_partner_to_session(session, partner_id)
        rows = (
            await session.execute(
                sa.select(UsageLedger, Tenant.name)
                .outerjoin(Tenant, Tenant.id == UsageLedger.tenant_id)
                .where(
                    UsageLedger.partner_id == partner_id,
                    UsageLedger.kind != KIND_ALLOCATION_LEGACY,
                )
                .order_by(UsageLedger.created_at.desc())
                .limit(limit)
            )
        ).all()
        return [
            AdminLedgerOut(
                id=row.id,
                kind=row.kind,
                bucket=row.bucket,
                # One entry is read on its own: nearest cent, like spend.
                amount_cents=credits_to_cents(int(row.qty), nearest=True),
                tenant_id=row.tenant_id,
                client_name=name,
                created_at=row.created_at,
            )
            for row, name in rows
        ]


@router.get("/{partner_id}/wallet/reconcile", response_model=AdminReconcileOut)
async def get_partner_wallet_reconcile(
    partner_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> AdminReconcileOut:
    """R2.4: does the stored recharged balance match the book?"""
    async with session.begin():
        await _get_partner_or_404(session, partner_id)
    try:
        rec = await reconcile_purchased(partner_id)
    except Exception as exc:
        log.warning("admin.wallet.reconcile_unreadable", partner_id=str(partner_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "ledger_unreadable"},
        ) from None
    if rec is None:
        return AdminReconcileOut(
            balanced=True,
            stored_cents=0,
            expected_cents=0,
            difference_credits=0,
            credits_cents=0,
            debits_cents=0,
            expiries_cents=0,
        )
    return AdminReconcileOut(
        balanced=rec.balanced,
        stored_cents=credits_to_cents(rec.stored),
        expected_cents=credits_to_cents(max(0, rec.expected)),
        difference_credits=rec.difference,
        credits_cents=credits_to_cents(rec.credits),
        debits_cents=credits_to_cents(rec.debits, nearest=True),
        expiries_cents=credits_to_cents(rec.expiries, nearest=True),
    )


@router.post(
    "/{partner_id}/wallet/purchased",
    response_model=AdminWalletOut,
    responses={
        400: {"description": "Falta X-Operator-Id o no es un operador."},
        409: {"description": "El libro no se puede escribir."},
        422: {"description": "Importe fuera de 1 a 1 000 000 centavos, sin clave, o campos extra."},
    },
)
async def add_partner_purchased(
    partner_id: uuid.UUID,
    body: AdminPurchasedIn,
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
) -> AdminWalletOut:
    """Recarga del saldo del partner del path, en centavos (spec 033, R3).

    Una transacción: saldo, asiento ``credit_admin`` y auditoría con el
    operador. La clave viene del formulario que la envió: la misma clave dos
    veces abona una vez y responde ``duplicate=True`` con el saldo tal cual.
    """
    async with session.begin():
        await _get_partner_or_404(session, partner_id)

    qty = cents_to_credits(body.amount_cents)
    actor = operator_actor(operator)

    async def audit(tx: AsyncSession, before: WalletSnapshot, after: WalletSnapshot) -> None:
        await AuditRepository(tx).record(
            actor=actor,
            action="wallet.admin_purchased",
            target=f"partner:{partner_id}",
            before={"purchased_cents": credits_to_cents(before.purchased_remaining)},
            after={
                "purchased_cents": credits_to_cents(after.purchased_remaining),
                "amount_cents": body.amount_cents,
                "idempotency_key": str(body.idempotency_key),
            },
            platform=True,
        )

    try:
        result = await add_purchased(
            partner_id,
            qty,
            kind=KIND_CREDIT_ADMIN,
            idempotency_key=f"{_ADMIN_PURCHASED_PREFIX}{partner_id}:{body.idempotency_key}",
            audit=audit,
        )
    except Exception as exc:
        log.warning("admin.wallet.purchased_unwritable", partner_id=str(partner_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "wallet_unwritable"},
        ) from None
    return _out(result.snapshot, await _sum_caps(partner_id), duplicate=result.duplicate)
