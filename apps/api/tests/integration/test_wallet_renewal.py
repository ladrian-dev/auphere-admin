"""D3: renovar el included caducado y sembrar la cuota que falte, en ese orden.

El orden no es cosmético. ``set_allocation`` y ``seed_default_allocation``
calculan el cap sobre el disponible del wallet, y ``effective_included``
devuelve 0 en cuanto ``expires_at <= now``. Con el included caducado,
**cualquier asignación sale 0**: sembrar antes de renovar deja filas a 0 que
parecen correctas y clientes igual de mudos.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.db.models import (
    Partner,
    PartnerAllocation,
    PartnerWallet,
    Tenant,
    TenantStatus,
)
from nexus_api.metering.wallet import (
    allocatable_for,
    next_period_end,
    renew_included_if_expired,
    seed_default_allocation,
)

pytestmark = pytest.mark.asyncio

MONTHLY_CAP = 500_000
DEFAULT_CAP = 50_000


async def _partner_with_expired_wallet(db_session) -> uuid.UUID:
    partner_id = uuid.uuid4()
    db_session.add(
        Partner(
            id=partner_id,
            name="Renovación Test",
            slug=f"renov-{partner_id.hex[:6]}",
            companion_monthly_token_cap=MONTHLY_CAP,
        )
    )
    await db_session.flush()
    wallet = await db_session.get(PartnerWallet, partner_id)
    expired = datetime.now(UTC) - timedelta(days=1)
    if wallet is None:
        wallet = PartnerWallet(
            partner_id=partner_id,
            included_remaining=MONTHLY_CAP,
            purchased_remaining=0,
            included_expires_at=expired,
        )
        db_session.add(wallet)
    else:
        wallet.included_remaining = MONTHLY_CAP
        wallet.purchased_remaining = 0
        wallet.included_expires_at = expired
    await db_session.commit()
    return partner_id


async def _tenant(db_session, partner_id: uuid.UUID) -> uuid.UUID:
    """Un cliente real: ``partner_allocations.tenant_id`` tiene FK a ``tenants``."""
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="Cliente Renovación",
            slug=f"renov-cli-{tenant_id.hex[:8]}",
            status=TenantStatus.ACTIVE,
            partner_id=partner_id,
        )
    )
    await db_session.flush()
    return tenant_id


async def test_expired_included_makes_every_allocation_zero(db_session) -> None:
    """La razón por la que el orden importa, escrita como test."""
    partner_id = await _partner_with_expired_wallet(db_session)
    tenant_id = uuid.uuid4()
    assert await allocatable_for(db_session, partner_id, tenant_id) == 0


async def test_renewal_then_seed_gives_the_client_its_quota(db_session) -> None:
    partner_id = await _partner_with_expired_wallet(db_session)
    tenant_id = await _tenant(db_session, partner_id)

    renewed = await renew_included_if_expired(
        db_session, partner_id=partner_id, monthly_cap=MONTHLY_CAP
    )
    assert renewed is True

    cap = await seed_default_allocation(
        db_session, partner_id=partner_id, tenant_id=tenant_id, default_cap=DEFAULT_CAP
    )
    assert cap == DEFAULT_CAP

    wallet = await db_session.get(PartnerWallet, partner_id)
    assert wallet is not None
    assert int(wallet.included_remaining) == MONTHLY_CAP
    assert wallet.included_expires_at == next_period_end()


async def test_seeding_before_renewing_is_the_trap(db_session) -> None:
    """Al revés: la fila se crea a 0 y el cliente sigue mudo."""
    partner_id = await _partner_with_expired_wallet(db_session)
    tenant_id = await _tenant(db_session, partner_id)

    cap = await seed_default_allocation(
        db_session, partner_id=partner_id, tenant_id=tenant_id, default_cap=DEFAULT_CAP
    )
    assert cap == 0

    # Y renovar después NO arregla la fila ya sembrada: es idempotente y no
    # la toca. Por eso el cron renueva primero.
    await renew_included_if_expired(db_session, partner_id=partner_id, monthly_cap=MONTHLY_CAP)
    again = await seed_default_allocation(
        db_session, partner_id=partner_id, tenant_id=tenant_id, default_cap=DEFAULT_CAP
    )
    assert again == 0


async def test_renewal_is_idempotent(db_session) -> None:
    partner_id = await _partner_with_expired_wallet(db_session)
    assert (
        await renew_included_if_expired(db_session, partner_id=partner_id, monthly_cap=MONTHLY_CAP)
        is True
    )
    assert (
        await renew_included_if_expired(db_session, partner_id=partner_id, monthly_cap=MONTHLY_CAP)
        is False
    )


async def test_renewal_fires_on_expiry_not_on_the_first_of_the_month(db_session) -> None:
    """Un scheduler caído el día 1 no puede costar el mes entero."""
    partner_id = await _partner_with_expired_wallet(db_session)
    # Estamos a mitad de mes y el included caducó hace días: renueva igual.
    assert (
        await renew_included_if_expired(db_session, partner_id=partner_id, monthly_cap=MONTHLY_CAP)
        is True
    )
    wallet = await db_session.get(PartnerWallet, partner_id)
    assert wallet is not None
    assert wallet.included_expires_at > datetime.now(UTC)


async def test_seed_does_not_touch_an_existing_allocation(db_session) -> None:
    partner_id = await _partner_with_expired_wallet(db_session)
    await renew_included_if_expired(db_session, partner_id=partner_id, monthly_cap=MONTHLY_CAP)
    tenant_id = await _tenant(db_session, partner_id)
    db_session.add(
        PartnerAllocation(partner_id=partner_id, tenant_id=tenant_id, cap=1234, remaining=7)
    )
    await db_session.flush()

    assert (
        await seed_default_allocation(
            db_session, partner_id=partner_id, tenant_id=tenant_id, default_cap=DEFAULT_CAP
        )
        == 1234
    )
    row = await db_session.scalar(
        sa.select(PartnerAllocation).where(
            PartnerAllocation.partner_id == partner_id,
            PartnerAllocation.tenant_id == tenant_id,
        )
    )
    assert row is not None
    assert int(row.remaining) == 7, "una cuota ya gastada no se repone sola"
