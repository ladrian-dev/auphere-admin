"""``/console/wallet`` — lectura del libro Fase 3.

El partner sale del principal. El cliente nunca envía ``partner_id``.
Un cliente ajeno (``/clients/{ref}/allocation``) es el mismo 404 opaco
que un ref que no existe. La lista nunca incluye filas de otro partner.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.config import get_settings
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import PartnerTenant
from nexus_api.db.models.partner_wallet import PartnerAllocation
from nexus_api.metering.wallet import OverAllocation, add_purchased, read_wallet, set_allocation

from .deps import ClientRef, resolve_mapping, unknown_client
from .schemas_wallet import AllocationIn, AllocationOut, PurchasedIn, WalletOut

router = APIRouter()
log = structlog.get_logger(__name__)


def _empty() -> WalletOut:
    return WalletOut(
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
        log.warning("wallet.caps_unreadable", partner_id=str(partner_id), error=str(exc))
        return 0


async def _list_allocations(partner_id: uuid.UUID) -> list[AllocationOut]:
    """Asignaciones del partner. ``client_ref``; nunca ``tenant_id``."""
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        rows = (
            await session.execute(
                sa.select(
                    PartnerTenant.external_client_ref,
                    PartnerAllocation.cap,
                    PartnerAllocation.remaining,
                )
                .join(
                    PartnerTenant,
                    sa.and_(
                        PartnerTenant.partner_id == PartnerAllocation.partner_id,
                        PartnerTenant.tenant_id == PartnerAllocation.tenant_id,
                    ),
                )
                .where(PartnerAllocation.partner_id == partner_id)
                .order_by(PartnerTenant.external_client_ref)
            )
        ).all()
    return [
        AllocationOut(client_ref=ref, cap=int(cap), remaining=int(remaining))
        for ref, cap, remaining in rows
    ]


@router.get("/wallet", response_model=WalletOut)
async def get_wallet(
    principal: ConsolePrincipal = Depends(require_console_principal("usage:read")),
) -> WalletOut:
    """Saldo del partner que llama. Libro ilegible → 0 (fail-closed).

    ``reserve`` = ``available`` - suma de caps.
    """
    snap = await read_wallet(principal.partner.id)
    if snap is None:
        return _empty()
    caps = await _sum_caps(principal.partner.id)
    return WalletOut(
        included_remaining=snap.included_remaining,
        purchased_remaining=snap.purchased_remaining,
        available=snap.available,
        reserve=snap.available - caps,
        included_expires_at=snap.included_expires_at,
        exhausted=snap.empty,
    )


@router.get("/wallet/allocations", response_model=list[AllocationOut])
async def list_wallet_allocations(
    principal: ConsolePrincipal = Depends(require_console_principal("usage:read")),
) -> list[AllocationOut]:
    """Asignaciones del partner que llama. Libro o lista ilegible → []."""
    try:
        if await read_wallet(principal.partner.id) is None:
            return []
        return await _list_allocations(principal.partner.id)
    except Exception as exc:
        log.warning(
            "wallet.allocations_unreadable",
            partner_id=str(principal.partner.id),
            error=str(exc),
        )
        return []


@router.get(
    "/clients/{ref}/allocation",
    response_model=AllocationOut,
    responses={404: {"description": "Unknown client reference."}},
)
async def get_client_allocation(
    ref: str = ClientRef,
    principal: ConsolePrincipal = Depends(require_console_principal("usage:read")),
    session: AsyncSession = Depends(get_db_session),
) -> AllocationOut:
    """Asignación de un cliente propio. El de otro partner es 404 opaco."""
    mapping = await resolve_mapping(session, principal, ref)
    async with session.begin():
        await apply_partner_to_session(session, principal.partner.id)
        row = await session.scalar(
            sa.select(PartnerAllocation).where(
                PartnerAllocation.partner_id == principal.partner.id,
                PartnerAllocation.tenant_id == mapping.tenant_id,
            )
        )
    if row is None:
        raise unknown_client()
    return AllocationOut(client_ref=ref, cap=row.cap, remaining=row.remaining)


@router.put(
    "/clients/{ref}/allocation",
    response_model=AllocationOut,
    responses={
        404: {"description": "Unknown client reference."},
        409: {"description": "Sum of caps would exceed wallet available."},
    },
)
async def put_client_allocation(
    body: AllocationIn,
    ref: str = ClientRef,
    principal: ConsolePrincipal = Depends(require_console_principal("usage:write")),
    session: AsyncSession = Depends(get_db_session),
) -> AllocationOut:
    """Fija el cap de un cliente propio. El de otro partner es 404 opaco.

    Mover cuota es dos PUT (bajar uno, subir el otro). No hay endpoint de move.
    """
    mapping = await resolve_mapping(session, principal, ref)
    try:
        row = await set_allocation(principal.partner.id, mapping.tenant_id, body.cap)
    except OverAllocation:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "over_allocated"},
        ) from None
    return AllocationOut(client_ref=ref, cap=int(row.cap), remaining=int(row.remaining))


@router.post(
    "/wallet/purchased",
    response_model=WalletOut,
    responses={
        409: {"description": "qty inválido o el libro no se puede escribir."},
        422: {"description": "qty no es un entero > 0, o el cuerpo trae campos extra."},
    },
)
async def add_purchased_tokens(
    body: PurchasedIn,
    principal: ConsolePrincipal = Depends(require_console_principal("usage:write")),
) -> WalletOut:
    """Suma tokens al cubo purchased del partner que llama.

    El partner sale del principal. El cuerpo solo admite ``qty`` (entero > 0).
    No hay Stripe. Fail-closed: si el libro no se escribe, 409.
    En prod el endpoint no existe (404 opaco): nadie se recarga solo.
    """
    if get_settings().is_prod:
        raise unknown_client()
    try:
        snap = await add_purchased(principal.partner.id, body.qty)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "invalid_qty"},
        ) from None
    except Exception as exc:
        log.warning(
            "wallet.purchased_unwritable",
            partner_id=str(principal.partner.id),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "wallet_unwritable"},
        ) from None
    caps = await _sum_caps(principal.partner.id)
    return WalletOut(
        included_remaining=snap.included_remaining,
        purchased_remaining=snap.purchased_remaining,
        available=snap.available,
        reserve=snap.available - caps,
        included_expires_at=snap.included_expires_at,
        exhausted=snap.empty,
    )
