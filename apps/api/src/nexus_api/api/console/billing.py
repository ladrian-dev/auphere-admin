"""``/console/billing`` — read-only billing view (CP-25 backend, before
Stripe). Billing e-mail, contact and the partner's receipts (invoices
addressed to the partner — decision C2: we bill the partner).

``GET /billing/receipts/{invoice_id}/download`` returns the receipt as a
**printable, self-contained HTML document** (``Content-Disposition:
attachment``). There is no PDF renderer in the repo (no weasyprint /
reportlab dependency) and adding a native one for v1 was not worth it:
the browser's "print to PDF" on this document IS the PDF, and the same
``render_receipt_html`` already produces the monthly e-mail, so the two
never disagree. Only receipts of the principal's partner resolve; any
other id is an opaque 404.
"""

from __future__ import annotations

import uuid
from html import escape

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.db.models import Invoice, InvoiceLine, Tenant
from nexus_api.services.partner_receipt import (
    ReceiptLine,
    ReceiptResult,
    _model_from_description,
    due_date_for,
)
from nexus_api.services.partner_receipt_email import receipt_subject, render_receipt_html

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


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown receipt")


@router.get("/receipts/{invoice_id}/download", response_class=HTMLResponse)
async def download_receipt(
    invoice_id: uuid.UUID,
    principal: ConsolePrincipal = Depends(require_console_principal("billing:read")),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    async with session.begin():
        invoice = await session.get(Invoice, invoice_id)
        if invoice is None or invoice.partner_id != principal.partner.id:
            raise _not_found()
        line_rows = (
            (
                await session.execute(
                    sa.select(InvoiceLine)
                    .where(InvoiceLine.invoice_id == invoice.id)
                    .order_by(InvoiceLine.created_at, InvoiceLine.id)
                )
            )
            .scalars()
            .all()
        )
        tenant_ids = {ln.tenant_id for ln in line_rows}
        names: dict[uuid.UUID, tuple[str, str]] = {}
        if tenant_ids:
            for tid, slug, name in (
                await session.execute(
                    sa.select(Tenant.id, Tenant.slug, Tenant.name).where(Tenant.id.in_(tenant_ids))
                )
            ).all():
                names[tid] = (slug, name)

    lines = [
        ReceiptLine(
            tenant_id=ln.tenant_id,
            tenant_slug=names.get(ln.tenant_id, ("?", ""))[0],
            tenant_name=names.get(ln.tenant_id, ("?", ln.description))[1],
            model=_model_from_description(ln.description),
            description=ln.description,
            amount_cents=ln.amount_cents,
        )
        for ln in line_rows
    ]
    result = ReceiptResult(
        invoice_id=invoice.id,
        partner_id=principal.partner.id,
        partner_slug=principal.partner.slug,
        partner_name=principal.partner.name,
        billing_email=principal.partner.billing_email,
        period_year=invoice.period_year,
        period_month=invoice.period_month,
        total_cents=invoice.total_cents,
        currency=invoice.currency,
        status=invoice.status,
        clp_per_usd=None,
        issued_at=invoice.issued_at,
        due_date=due_date_for(invoice.period_year, invoice.period_month),
        lines=lines,
        created=False,
    )
    title = receipt_subject(result)
    body = render_receipt_html(result)
    document = (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        f"<title>{escape(title)}</title>"
        "<style>@media print { body { margin: 0 } }</style>"
        f'</head><body style="margin:24px">{body}</body></html>'
    )
    filename = (
        f"recibo-{principal.partner.slug}-{invoice.period_year}-{invoice.period_month:02d}.html"
    )
    return HTMLResponse(
        content=document,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
