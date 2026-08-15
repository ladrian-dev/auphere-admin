"""``/console/billing`` — read-only billing view (CP-25 backend, before
Stripe). Billing e-mail, contact and the partner's receipts (invoices
addressed to the partner — decision C2: we bill the partner).

Downloading a receipt (PDF) and Stripe live in later packages; this is
the list a partner can check without asking anyone.
"""

from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.db.models import Invoice
from nexus_api.services.partner_receipt import due_date_for

from .schemas import BillingOut, ReceiptSummaryOut

router = APIRouter(prefix="/billing")


@router.get("", response_model=BillingOut)
async def get_billing(
    principal: ConsolePrincipal = Depends(require_console_principal("billing:read")),
    session: AsyncSession = Depends(get_db_session),
) -> BillingOut:
    async with session.begin():
        rows = (
            (
                await session.execute(
                    sa.select(Invoice)
                    .where(Invoice.partner_id == principal.partner.id)
                    .order_by(Invoice.period_year.desc(), Invoice.period_month.desc())
                )
            )
            .scalars()
            .all()
        )
        receipts = [
            ReceiptSummaryOut(
                invoice_id=inv.id,
                period_year=inv.period_year,
                period_month=inv.period_month,
                total_usd=inv.total_cents / 100,
                currency=inv.currency,
                status=inv.status,
                issued_at=inv.issued_at,
                due_date=due_date_for(inv.period_year, inv.period_month),
            )
            for inv in rows
        ]
    return BillingOut(
        billing_email=principal.partner.billing_email,
        contact_email=principal.partner.contact_email,
        receipts=receipts,
    )
