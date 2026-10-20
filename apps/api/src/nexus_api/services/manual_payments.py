"""A partner's payment received outside Stripe, and its credit (owner, 2026-10-20).

The partner pays Auphere, not its client. A payment is still recorded against
one client and one month — that is what the partner paid for — but recording
it credits the **partner's** recharged balance with the amount, once, by the
payment's id; voiding it takes the credit back. A client without a partner is
a direct client of Auphere: its payment is recorded and credits nothing.

The payment row and the credit are two transactions (the row lives under the
client's RLS, the credit under the partner's). The credit is keyed by the
payment, so retrying it never credits twice, and ``credited_cents`` says
whether it happened.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.billing.pricing import cents_to_credits, credits_to_cents
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.partner import PartnerTenant
from nexus_api.db.models.partner_wallet import KIND_CREDIT_MANUAL
from nexus_api.db.models.tenant_payment import TenantPayment
from nexus_api.metering.wallet import (
    NotEnoughBalance,
    WalletSnapshot,
    add_purchased,
    reverse_purchased,
)
from nexus_api.repositories import AuditRepository

log = structlog.get_logger(__name__)

__all__ = ["NotEnoughBalance", "credit_payment", "partner_of", "reverse_payment"]


def credit_key(payment_id: uuid.UUID) -> str:
    return f"tenant_payment:{payment_id}"


def reversal_key(payment_id: uuid.UUID) -> str:
    return f"tenant_payment_void:{payment_id}"


async def partner_of(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID | None:
    """The partner that pays for this client, if it has one."""
    found = await session.scalar(
        sa.select(PartnerTenant.partner_id).where(PartnerTenant.tenant_id == tenant_id).limit(1)
    )
    return found if isinstance(found, uuid.UUID) else None


async def credit_payment(*, payment: TenantPayment, partner_id: uuid.UUID, actor: str) -> int:
    """Credit the partner with the payment's amount. Safe to repeat."""

    async def audit(tx: AsyncSession, before: WalletSnapshot, after: WalletSnapshot) -> None:
        await AuditRepository(tx).record(
            actor=actor,
            action="wallet.admin_purchased",
            target=f"partner:{partner_id}",
            before={"purchased_cents": credits_to_cents(before.purchased_remaining)},
            after=_payment_after(payment, after),
            platform=True,
        )

    await add_purchased(
        partner_id,
        cents_to_credits(payment.amount_cents),
        kind=KIND_CREDIT_MANUAL,
        idempotency_key=credit_key(payment.id),
        audit=audit,
    )
    await _set_credited(payment.tenant_id, payment.id, payment.amount_cents)
    log.info(
        "manual_payment.credited",
        partner_id=str(partner_id),
        payment_id=str(payment.id),
        amount_cents=payment.amount_cents,
    )
    return payment.amount_cents


async def reverse_payment(*, payment: TenantPayment, partner_id: uuid.UUID, actor: str) -> None:
    """Take a voided payment's credit back. Raises ``NotEnoughBalance``."""
    amount = int(payment.credited_cents or 0)
    if amount <= 0:
        return

    async def audit(tx: AsyncSession, before: WalletSnapshot, after: WalletSnapshot) -> None:
        await AuditRepository(tx).record(
            actor=actor,
            action="wallet.payment_reversed",
            target=f"partner:{partner_id}",
            before={"purchased_cents": credits_to_cents(before.purchased_remaining)},
            after={**_payment_after(payment, after), "amount_cents": amount},
            platform=True,
        )

    await reverse_purchased(
        partner_id,
        cents_to_credits(amount),
        idempotency_key=reversal_key(payment.id),
        audit=audit,
    )
    log.info("manual_payment.reversed", partner_id=str(partner_id), payment_id=str(payment.id))


def _payment_after(payment: TenantPayment, after: WalletSnapshot) -> dict[str, Any]:
    return {
        "purchased_cents": credits_to_cents(after.purchased_remaining),
        "amount_cents": payment.amount_cents,
        "payment_id": str(payment.id),
        "period": f"{payment.period_year}-{payment.period_month:02d}",
    }


async def _set_credited(tenant_id: uuid.UUID, payment_id: uuid.UUID, cents: int) -> None:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        row = await s.get(TenantPayment, payment_id)
        if row is not None and row.credited_cents is None:
            row.credited_cents = cents
