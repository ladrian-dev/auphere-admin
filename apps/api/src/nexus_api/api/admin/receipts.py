"""Admin panel for monthly partner receipts (recibos) — operator only.

Read: list a partner's receipts and drill into one (lines + totals).
Write: (re)generate a period's receipt (idempotent) and re-send its email.

Generation runs through :mod:`nexus_api.services.partner_receipt`, which uses
its own session-maker (it opens tenant-scoped sessions to read commission
sales), so these handlers call the service with ``get_sessionmaker()`` rather
than the request-scoped session.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Invoice, InvoiceLine, Partner
from nexus_api.schemas.receipt import (
    ReceiptGenerateIn,
    ReceiptLineOut,
    ReceiptOut,
    ReceiptSendOut,
    ReceiptSummaryOut,
)
from nexus_api.services.email import send_email
from nexus_api.services.partner_receipt import (
    PartnerNotFound,
    ReceiptResult,
    due_date_for,
    generate_partner_receipt,
)
from nexus_api.services.partner_receipt_email import receipt_subject, render_receipt_html

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/partners", dependencies=[Depends(require_admin_token)])


async def _partner_or_404(session: AsyncSession, partner_id: uuid.UUID) -> Partner:
    partner = (
        await session.execute(sa.select(Partner).where(Partner.id == partner_id))
    ).scalar_one_or_none()
    if partner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"partner {partner_id} not found")
    return partner


def _result_to_out(r: ReceiptResult) -> ReceiptOut:
    return ReceiptOut(
        invoice_id=r.invoice_id,
        partner_id=r.partner_id,
        partner_slug=r.partner_slug,
        partner_name=r.partner_name,
        billing_email=r.billing_email,
        period_year=r.period_year,
        period_month=r.period_month,
        total_usd=r.total_cents / 100,
        currency=r.currency,
        status=r.status,
        clp_per_usd=float(r.clp_per_usd) if r.clp_per_usd is not None else None,
        issued_at=r.issued_at,
        due_date=r.due_date,
        created=r.created,
        lines=[
            ReceiptLineOut(
                tenant_id=ln.tenant_id,
                tenant_slug=ln.tenant_slug,
                tenant_name=ln.tenant_name,
                model=ln.model,
                description=ln.description,
                amount_usd=ln.amount_cents / 100,
                commission_clp=float(ln.commission_clp) if ln.commission_clp is not None else None,
            )
            for ln in r.lines
        ],
    )


@router.get("/{partner_id}/receipts", response_model=list[ReceiptSummaryOut])
async def list_receipts(
    partner_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> list[ReceiptSummaryOut]:
    await _partner_or_404(session, partner_id)
    rows = (
        (
            await session.execute(
                sa.select(Invoice)
                .where(Invoice.partner_id == partner_id)
                .order_by(Invoice.period_year.desc(), Invoice.period_month.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
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


@router.get("/{partner_id}/receipts/{invoice_id}", response_model=ReceiptOut)
async def get_receipt(
    partner_id: uuid.UUID,
    invoice_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> ReceiptOut:
    partner = await _partner_or_404(session, partner_id)
    inv = (
        await session.execute(
            sa.select(Invoice).where(Invoice.id == invoice_id, Invoice.partner_id == partner_id)
        )
    ).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"receipt {invoice_id} not found")
    lines = (
        (await session.execute(sa.select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id)))
        .scalars()
        .all()
    )
    return ReceiptOut(
        invoice_id=inv.id,
        partner_id=partner.id,
        partner_slug=partner.slug,
        partner_name=partner.name,
        billing_email=partner.billing_email,
        period_year=inv.period_year,
        period_month=inv.period_month,
        total_usd=inv.total_cents / 100,
        currency=inv.currency,
        status=inv.status,
        issued_at=inv.issued_at,
        due_date=due_date_for(inv.period_year, inv.period_month),
        created=False,
        lines=[
            ReceiptLineOut(
                tenant_id=ln.tenant_id,
                tenant_slug="",
                tenant_name="",
                model="",
                description=ln.description,
                amount_usd=ln.amount_cents / 100,
            )
            for ln in lines
        ],
    )


@router.post("/{partner_id}/receipts", response_model=ReceiptOut)
async def generate_receipt(
    partner_id: uuid.UUID,
    body: ReceiptGenerateIn,
    session: AsyncSession = Depends(get_db_session),
) -> ReceiptOut:
    partner = await _partner_or_404(session, partner_id)
    try:
        receipt = await generate_partner_receipt(
            get_sessionmaker(),
            partner_slug=partner.slug,
            period_year=body.period_year,
            period_month=body.period_month,
        )
    except PartnerNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    if body.send_email and receipt.billing_email:
        await _mail(receipt)
    return _result_to_out(receipt)


@router.post("/{partner_id}/receipts/{invoice_id}/send", response_model=ReceiptSendOut)
async def send_receipt(
    partner_id: uuid.UUID,
    invoice_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> ReceiptSendOut:
    partner = await _partner_or_404(session, partner_id)
    inv = (
        await session.execute(
            sa.select(Invoice).where(Invoice.id == invoice_id, Invoice.partner_id == partner_id)
        )
    ).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"receipt {invoice_id} not found")
    if not partner.billing_email:
        raise HTTPException(status.HTTP_409_CONFLICT, "partner has no billing_email")
    # Rebuild the full receipt (idempotent) so the email has line detail.
    receipt = await generate_partner_receipt(
        get_sessionmaker(),
        partner_slug=partner.slug,
        period_year=inv.period_year,
        period_month=inv.period_month,
    )
    emailed = await _mail(receipt)
    return ReceiptSendOut(invoice_id=inv.id, emailed=emailed, to=partner.billing_email)


async def _mail(receipt: ReceiptResult) -> bool:
    if not receipt.billing_email:
        return False
    return await send_email(
        to=receipt.billing_email,
        subject=receipt_subject(receipt),
        html=render_receipt_html(receipt),
    )
