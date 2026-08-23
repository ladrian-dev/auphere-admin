"""Admin C3 — wallet, ledger y recarga purchased del partner del path.

El ``partner_id`` del path es la fuente de verdad. Se fija el GUC
``app.partner_id`` igual que el libro FORCE (``partner_wallets``).
No hay caps de cliente. En prod la recarga no existe (404 opaco).
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.partners import _admin_actor, _get_partner_or_404
from nexus_api.api.console.deps import unknown_client
from nexus_api.api.deps import get_db_session
from nexus_api.config import get_settings
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.partner_wallet import (
    BUCKET_PURCHASED,
    PartnerAllocation,
    UsageLedger,
)
from nexus_api.metering.wallet import add_purchased, read_wallet
from nexus_api.repositories import AuditRepository
from nexus_api.schemas.admin_wallet import AdminLedgerOut, AdminPurchasedIn, AdminWalletOut

router = APIRouter(prefix="/partners", dependencies=[Depends(require_admin_token)])
log = structlog.get_logger(__name__)

_ALLOCATION_SUFFIX = ":allocation"
_ADMIN_PURCHASED_PREFIX = "admin_purchased:"


def _empty() -> AdminWalletOut:
    return AdminWalletOut(
        included_remaining=0,
        purchased_remaining=0,
        available=0,
        reserve=0,
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


async def _wallet_out(partner_id: uuid.UUID) -> AdminWalletOut:
    snap = await read_wallet(partner_id)
    if snap is None:
        return _empty()
    caps = await _sum_caps(partner_id)
    return AdminWalletOut(
        included_remaining=snap.included_remaining,
        purchased_remaining=snap.purchased_remaining,
        available=snap.available,
        reserve=snap.available - caps,
        included_expires_at=snap.included_expires_at,
        exhausted=snap.empty,
    )


def _ledger_reason(idempotency_key: str) -> str:
    if idempotency_key.startswith(_ADMIN_PURCHASED_PREFIX):
        return "admin_purchased"
    return "debit"


async def _record_purchased_ledger(partner_id: uuid.UUID, qty: int) -> None:
    """Asiento del crédito admin. El GUC sale del path (FORCE)."""
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        session.add(
            UsageLedger(
                partner_id=partner_id,
                tenant_id=None,
                qty=qty,
                bucket=BUCKET_PURCHASED,
                idempotency_key=f"{_ADMIN_PURCHASED_PREFIX}{uuid.uuid4()}",
                fx=None,
            )
        )


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
    """Asientos del partner del path. Sin filas de allocation de cliente."""
    async with session.begin():
        await _get_partner_or_404(session, partner_id)
        await apply_partner_to_session(session, partner_id)
        rows = (
            await session.scalars(
                sa.select(UsageLedger)
                .where(
                    UsageLedger.partner_id == partner_id,
                    ~UsageLedger.idempotency_key.like(f"%{_ALLOCATION_SUFFIX}"),
                )
                .order_by(UsageLedger.created_at.desc())
                .limit(limit)
            )
        ).all()
        return [
            AdminLedgerOut(
                id=row.id,
                bucket=row.bucket,
                qty=int(row.qty),
                reason=_ledger_reason(row.idempotency_key),
                created_at=row.created_at,
            )
            for row in rows
        ]


@router.post(
    "/{partner_id}/wallet/purchased",
    response_model=AdminWalletOut,
    responses={
        409: {"description": "qty inválido o el libro no se puede escribir."},
        422: {"description": "qty no es un entero > 0, o el cuerpo trae campos extra."},
    },
)
async def add_partner_purchased(
    partner_id: uuid.UUID,
    body: AdminPurchasedIn,
    session: AsyncSession = Depends(get_db_session),
    actor: str = Depends(require_admin_token),
) -> AdminWalletOut:
    """Suma tokens purchased al partner del path. En prod: 404 opaco, no acredita."""
    async with session.begin():
        await _get_partner_or_404(session, partner_id)
    if get_settings().is_prod:
        raise unknown_client()

    before = await read_wallet(partner_id)
    before_available = before.available if before is not None else 0
    try:
        snap = await add_purchased(partner_id, body.qty)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "invalid_qty"},
        ) from None
    except Exception as exc:
        log.warning(
            "admin.wallet.purchased_unwritable",
            partner_id=str(partner_id),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "wallet_unwritable"},
        ) from None

    await _record_purchased_ledger(partner_id, body.qty)

    async with session.begin():
        await AuditRepository(session).record(
            actor=_admin_actor(actor),
            action="wallet.admin_purchased",
            target=f"partner:{partner_id}",
            before={"available": before_available},
            after={"available": snap.available},
            platform=True,
        )

    caps = await _sum_caps(partner_id)
    return AdminWalletOut(
        included_remaining=snap.included_remaining,
        purchased_remaining=snap.purchased_remaining,
        available=snap.available,
        reserve=snap.available - caps,
        included_expires_at=snap.included_expires_at,
        exhausted=snap.empty,
    )
