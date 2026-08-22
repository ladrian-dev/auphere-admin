"""``/console/wallet`` — lectura del libro Fase 3.

El partner sale del principal. El cliente nunca envía ``partner_id``.
Un cliente ajeno (``/clients/{ref}/allocation``) es el mismo 404 opaco
que un ref que no existe.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.metering.wallet import read_wallet

from .deps import ClientRef, resolve_mapping, unknown_client
from .schemas_wallet import AllocationOut, WalletOut

router = APIRouter()


def _empty(partner_missing: bool = False) -> WalletOut:
    del partner_missing
    return WalletOut(
        included_remaining=0,
        purchased_remaining=0,
        available=0,
        included_expires_at=None,
        exhausted=True,
    )


@router.get("/wallet", response_model=WalletOut)
async def get_wallet(
    principal: ConsolePrincipal = Depends(require_console_principal("usage:read")),
) -> WalletOut:
    """Saldo del partner que llama. Libro ilegible → 0 (fail-closed)."""
    snap = await read_wallet(principal.partner.id)
    if snap is None:
        return _empty()
    return WalletOut(
        included_remaining=snap.included_remaining,
        purchased_remaining=snap.purchased_remaining,
        available=snap.available,
        included_expires_at=snap.included_expires_at,
        exhausted=snap.empty,
    )


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
    import sqlalchemy as sa

    from nexus_api.core.partner_context import apply_partner_to_session
    from nexus_api.db.models.partner_wallet import PartnerAllocation

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
