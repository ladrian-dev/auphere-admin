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
from datetime import UTC, datetime
from html import escape

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.billing.catalog import base_paid_pool, consumption_multiple, load_public_tiers
from nexus_api.billing.checkout import (
    BillingUnavailable,
    open_portal,
    open_subscription_session,
)
from nexus_api.billing.provider import idempotency_key  # noqa: F401 - re-exported for tests
from nexus_api.config import get_settings
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.db.models import AuditLog, Invoice, InvoiceLine, Tenant
from nexus_api.db.models.membership import (
    STATE_CANCELED,
    TIER_FREE,
    MembershipTier,
    PartnerSubscription,
)
from nexus_api.services.membership_limits import over_cap_by
from nexus_api.services.partner_receipt import (
    ReceiptLine,
    ReceiptResult,
    _model_from_description,
    due_date_for,
)
from nexus_api.services.partner_receipt_email import receipt_subject, render_receipt_html

from .schemas import (
    BillingOut,
    CheckoutIn,
    CheckoutOut,
    MembershipOut,
    MembershipUsageOut,
    PortalOut,
    ReceiptSummaryOut,
    TierOut,
)

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


# ── Spec 005 · membresía y cobro ─────────────────────────────────────────────


def _tier_out(tier: MembershipTier, base_pool: int) -> TierOut:
    return TierOut(
        code=tier.code,
        display_name=tier.display_name,
        monthly_price_cents=tier.monthly_price_cents,
        max_teammates=tier.max_teammates,
        max_members=tier.max_members,
        consumption_multiple=consumption_multiple(
            pool=tier.weekly_pool_tokens, base_pool=base_pool
        ),
    )


def _unavailable() -> HTTPException:
    """503 and not 500. "Try again in a moment" is true and actionable;
    "something went wrong" is neither (principle V)."""
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": "billing_unavailable"},
    )


@router.get("/membership", response_model=MembershipOut)
async def get_membership(
    principal: ConsolePrincipal = Depends(require_console_principal("billing:read")),
    session: AsyncSession = Depends(get_db_session),
) -> MembershipOut:
    """Everything the plans screen needs, in one call."""
    partner_id = principal.partner.id

    subscription = (
        await session.execute(
            sa.select(PartnerSubscription).where(PartnerSubscription.partner_id == partner_id)
        )
    ).scalar_one_or_none()

    # A partner with no row is Free, and so is a cancelled one. Absence is a
    # valid state and is designed as one (principle V).
    code = TIER_FREE
    if subscription is not None and subscription.state != STATE_CANCELED:
        code = subscription.tier_code

    tiers = await load_public_tiers(session)
    base_pool = await base_paid_pool(session)
    by_code = {t.code: t for t in tiers}
    current = by_code.get(code) or by_code[TIER_FREE]

    teammates = int(
        await session.scalar(
            sa.text(
                "SELECT count(*) FROM teammates WHERE partner_id = :p AND status <> 'archived'"
            ),
            {"p": str(partner_id)},
        )
        or 0
    )
    members = int(
        await session.scalar(
            sa.text(
                "SELECT count(*) FROM partner_memberships "
                "WHERE partner_id = :p AND status = 'active'"
            ),
            {"p": str(partner_id)},
        )
        or 0
    )
    purchased_expires_at = await session.scalar(
        sa.text("SELECT purchased_expires_at FROM partner_wallets WHERE partner_id = :p"),
        {"p": str(partner_id)},
    )

    return MembershipOut(
        tier=_tier_out(current, base_pool),
        state=subscription.state if subscription else "current",
        state_changed_at=subscription.state_changed_at if subscription else None,
        current_period_end=subscription.current_period_end if subscription else None,
        pending_tier=subscription.pending_tier_code if subscription else None,
        usage=MembershipUsageOut(teammates=teammates, members=members),
        purchased_expires_at=purchased_expires_at,
        catalog=[_tier_out(t, base_pool) for t in tiers],
    )


@router.post("/checkout", response_model=CheckoutOut)
async def start_checkout(
    body: CheckoutIn,
    principal: ConsolePrincipal = Depends(require_console_principal("billing:manage")),
    session: AsyncSession = Depends(get_db_session),
) -> CheckoutOut:
    """Contract a tier. A person does this, and the audit names them (§IV)."""
    partner_id = principal.partner.id
    tier = (
        await session.execute(
            sa.select(MembershipTier).where(
                MembershipTier.code == body.tier_code,
                MembershipTier.is_public.is_(True),
            )
        )
    ).scalar_one_or_none()
    if tier is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "unknown_tier"},
        )
    if tier.code == TIER_FREE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "use_cancel_to_downgrade_to_free"},
        )

    # Refuse a move that does not fit BEFORE it happens. Never archive
    # anything to make room (§IV): tell the partner what to free up.
    over = await over_cap_by(session, partner_id, tier.code)
    if over:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "tier_below_usage", "over": over, "tier": tier.code},
        )

    if not tier.stripe_price_id:
        # The catalogue has not been created upstream yet. Honest state:
        # "cannot charge right now", not a stack trace.
        raise _unavailable()

    subscription = (
        await session.execute(
            sa.select(PartnerSubscription).where(PartnerSubscription.partner_id == partner_id)
        )
    ).scalar_one_or_none()

    settings = get_settings()
    try:
        url = open_subscription_session(
            partner_id=partner_id,
            price_id=tier.stripe_price_id,
            console_base_url=settings.console_base_url,
            customer_id=subscription.stripe_customer_id if subscription else None,
            period_tag=datetime.now(UTC).strftime("%G-W%V"),
        )
    except BillingUnavailable as exc:
        raise _unavailable() from exc

    # §IV: the audit names the PERSON who decided, not the process. The
    # provider's notice later CONFIRMS this; it does not decide it.
    session.add(
        AuditLog(
            tenant_id=None,
            actor=principal.actor,
            action="console.billing.checkout_opened",
            target=f"partner:{partner_id}",
            before_json=None,
            after_json={"tier": tier.code},
        )
    )
    await session.commit()
    return CheckoutOut(url=url)


@router.get("/portal", response_model=PortalOut)
async def open_billing_portal(
    principal: ConsolePrincipal = Depends(require_console_principal("billing:manage")),
    session: AsyncSession = Depends(get_db_session),
) -> PortalOut:
    """The provider's own portal: card, invoices, cancellation.

    Delegated on purpose. The provider's invoices are the fiscal document,
    and building our own card screen would mean touching card data.
    """
    subscription = (
        await session.execute(
            sa.select(PartnerSubscription).where(
                PartnerSubscription.partner_id == principal.partner.id
            )
        )
    ).scalar_one_or_none()
    if subscription is None or not subscription.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "no_subscription_yet"},
        )
    try:
        url = open_portal(
            customer_id=subscription.stripe_customer_id,
            console_base_url=get_settings().console_base_url,
        )
    except BillingUnavailable as exc:
        raise _unavailable() from exc
    return PortalOut(url=url)
