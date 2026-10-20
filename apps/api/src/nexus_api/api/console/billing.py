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
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.billing.catalog import base_paid_pool, consumption_multiple, load_public_tiers
from nexus_api.billing.checkout import (
    BillingUnavailable,
    open_credit_session,
    open_portal,
    open_subscription_session,
    schedule_downgrade,
    upgrade_subscription,
)
from nexus_api.billing.pricing import credits_to_cents
from nexus_api.billing.provider import (
    ProviderRefusal,
    as_refusal,
    idempotency_key,  # noqa: F401 - re-exported for tests
)
from nexus_api.config import get_settings
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.db.models import AuditLog, Invoice, InvoiceLine, Partner, Tenant
from nexus_api.db.models.membership import (
    STATE_CANCELED,
    STATE_CURRENT,
    STATE_PAYMENT_FAILED,
    TIER_FREE,
    MembershipTier,
    PartnerSubscription,
)
from nexus_api.metering.wallet import apply_tier_change
from nexus_api.services.membership_limits import over_cap_by
from nexus_api.services.partner_billing import (
    BillingRuleError,
    BillingView,
    billing_view,
    open_card_setup,
    remove_card,
    set_charging,
)
from nexus_api.services.partner_receipt import (
    ReceiptLine,
    ReceiptResult,
    _model_from_description,
    due_date_for,
)
from nexus_api.services.partner_receipt_email import receipt_subject, render_receipt_html

from .schemas import (
    BillingOut,
    CancelOut,
    CheckoutIn,
    CheckoutOut,
    CreditIn,
    MembershipOut,
    MembershipUsageOut,
    PortalOut,
    ReceiptSummaryOut,
    TierOut,
)

router = APIRouter(prefix="/billing")


def require_memberships() -> None:
    """Spec 034 (R3.1): with memberships off, the plans, the provider portal and
    the cancellation do not exist — a 404, not a disabled button (§V).

    Called first thing in the body, **after** the principal is resolved: an
    anonymous caller or a client user still gets its 401/403 (the isolation
    sweeps check exactly that), and only an authorised partner learns the
    route is not there."""
    from nexus_api.services.membership_limits import memberships_enabled

    if not memberships_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "not_found"})


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
    from nexus_api.services.membership_limits import memberships_enabled

    return BillingOut(
        billing_email=principal.partner.billing_email,
        contact_email=principal.partner.contact_email,
        receipts=receipts,
        memberships_enabled=memberships_enabled(),
    )


class _BillingEmailIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    #: ``None`` clears it: notices go back to the contact e-mail.
    billing_email: EmailStr | None


class BillingEmailOut(BaseModel):
    billing_email: str | None


@router.put("/email", response_model=BillingEmailOut)
async def put_billing_email(
    body: _BillingEmailIn,
    principal: ConsolePrincipal = Depends(require_console_principal("billing:manage")),
    session: AsyncSession = Depends(get_db_session),
) -> BillingEmailOut:
    """The partner sets where billing notices go (owner, 2026-10-20).

    Until now only Auphere could set it from the Admin, and the console said
    «escríbenos». The 3D Secure notice («Confirma el cobro de tu tarjeta») goes
    here: a partner who cannot set it may never confirm a charge.
    """
    new = str(body.billing_email).strip().lower() if body.billing_email else None
    async with session.begin():
        partner = await session.get(Partner, principal.partner.id, with_for_update=True)
        if partner is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_partner")
        before = partner.billing_email
        if before != new:
            partner.billing_email = new
            session.add(
                AuditLog(
                    tenant_id=None,
                    actor=principal.actor,
                    action="console.billing.email_update",
                    target=f"partner:{partner.id}",
                    before_json={"billing_email": before},
                    after_json={"billing_email": new},
                )
            )
    return BillingEmailOut(billing_email=new)


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


log = structlog.get_logger(__name__)


def _provider_error(refusal: ProviderRefusal) -> HTTPException:
    """502 with Stripe's own reason. Without it a refused call was a bare 500
    («No se pudo hablar con el servidor») and nobody could tell why: the
    code and message go to the log and to the screen."""
    log.warning(
        "billing.provider_error",
        provider_code=refusal.code,
        message=refusal.message,
        http_status=refusal.http_status,
        request_id=refusal.request_id,
    )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={
            "code": "billing_provider_error",
            "provider_code": refusal.code,
            "message": refusal.message,
        },
    )


def _refused(exc: Exception) -> HTTPException:
    """The 502 for a provider refusal; anything else is not ours to name."""
    refusal = as_refusal(exc)
    if refusal is None:
        raise exc
    return _provider_error(refusal)


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
    require_memberships()
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
    require_memberships()
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
    period_tag = datetime.now(UTC).strftime("%G-W%V")

    # Con una suscripción viva **no se abre página de pago**: se modifica la
    # que hay. Mandar a alguien que ya paga a introducir su tarjeta otra vez
    # para subir de plan es pedirle que demuestre algo que ya demostró.
    # La condición va entera en el ``if`` y no en una variable intermedia. No
    # es estilo: con una variable, el comprobador pierde el rastro de que
    # ``subscription`` no es ``None`` dentro del bloque, y lo que se lee como
    # protegido deja de estarlo si alguien mueve una línea.
    subscription_id = subscription.stripe_subscription_id if subscription else None
    if (
        subscription is not None
        and subscription_id
        and subscription.state in {STATE_CURRENT, STATE_PAYMENT_FAILED}
    ):
        try:
            outcome = await apply_tier_change(session, partner_id=partner_id, new_tier=tier.code)
            if outcome == "upgraded":
                # El prorrateo del dinero lo hace el proveedor; el pool lo
                # completa el libro. Cada uno lo que sabe hacer.
                upgrade_subscription(
                    partner_id=partner_id,
                    subscription_id=subscription_id,
                    price_id=tier.stripe_price_id or "",
                    period_tag=period_tag,
                )
            else:
                schedule_downgrade(
                    partner_id=partner_id,
                    subscription_id=subscription_id,
                    price_id=tier.stripe_price_id or "",
                    period_tag=period_tag,
                )
        except BillingUnavailable as exc:
            raise _unavailable() from exc

        session.add(
            AuditLog(
                tenant_id=None,
                actor=principal.actor,
                action="console.billing.tier_changed",
                target=f"partner:{partner_id}",
                before_json={"tier": subscription.tier_code},
                after_json={"tier": tier.code, "outcome": outcome},
            )
        )
        await session.commit()
        return CheckoutOut(
            url=None,
            applied=outcome == "upgraded",
            effective_at=subscription.current_period_end if outcome == "scheduled" else None,
        )

    try:
        url = open_subscription_session(
            partner_id=partner_id,
            price_id=tier.stripe_price_id,
            console_base_url=settings.console_base_url,
            customer_id=subscription.stripe_customer_id if subscription else None,
            period_tag=period_tag,
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
    require_memberships()
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


@router.post("/credit", response_model=CheckoutOut)
async def buy_credit(
    body: CreditIn,
    principal: ConsolePrincipal = Depends(require_console_principal("billing:manage")),
    session: AsyncSession = Depends(get_db_session),
) -> CheckoutOut:
    """Open the page to buy consumption credit.

    **This credits nothing.** It opens the provider's page; the balance goes
    up when the payment is confirmed and the notice arrives. That separation
    is the whole point of removing ``POST /console/wallet/purchased``: there
    is no longer any way for a partner to add balance without paying.
    """
    partner_id = principal.partner.id
    subscription = (
        await session.execute(
            sa.select(PartnerSubscription).where(PartnerSubscription.partner_id == partner_id)
        )
    ).scalar_one_or_none()

    try:
        url = open_credit_session(
            partner_id=partner_id,
            amount_cents=body.amount_cents,
            console_base_url=get_settings().console_base_url,
            customer_id=subscription.stripe_customer_id if subscription else None,
            # The stamp is what makes a second purchase of the same amount a
            # second purchase. Without it the idempotency key repeats and the
            # provider replays the first response: a purchase the partner asked
            # for, paid attention to, and that silently does not happen.
            stamp=datetime.now(UTC).isoformat(timespec="seconds"),
        )
    except BillingUnavailable as exc:
        raise _unavailable() from exc
    except Exception as exc:
        raise _refused(exc) from exc

    session.add(
        AuditLog(
            tenant_id=None,
            actor=principal.actor,
            action="console.billing.credit_opened",
            target=f"partner:{partner_id}",
            before_json=None,
            after_json={"amount_cents": body.amount_cents},
        )
    )
    await session.commit()
    return CheckoutOut(url=url)


@router.delete("/subscription", response_model=CancelOut)
async def cancel_subscription_route(
    principal: ConsolePrincipal = Depends(require_console_principal("billing:manage")),
    session: AsyncSession = Depends(get_db_session),
) -> CancelOut:
    """Cancel the plan. **Nothing is archived** (§IV).

    Not a teammate, not a task, not a pending confirmation, not a
    conversation. The account stays whole and readable; what stops is the
    weekly pool refilling. The purchased credit gets a twelve-month clock and
    the answer says so, because that is what the person is wondering.

    Cancelling twice is not an error. Somebody who clicks again because the
    first click did not look like it worked does not deserve a red screen.
    """
    require_memberships()
    from nexus_api.billing.ladder import cancel_subscription

    partner_id = principal.partner.id
    expires_at = await cancel_subscription(session, partner_id=partner_id)

    row = (
        await session.execute(
            sa.text(
                "SELECT purchased_remaining, purchased_expires_at "
                "FROM partner_wallets WHERE partner_id = :p"
            ),
            {"p": str(partner_id)},
        )
    ).first()

    subscription = (
        await session.execute(
            sa.select(PartnerSubscription).where(PartnerSubscription.partner_id == partner_id)
        )
    ).scalar_one_or_none()

    session.add(
        AuditLog(
            tenant_id=None,
            actor=principal.actor,
            action="console.billing.canceled",
            target=f"partner:{partner_id}",
            before_json=None,
            after_json={"credit_expires_at": expires_at.isoformat() if expires_at else None},
        )
    )
    await session.commit()

    return CancelOut(
        state=subscription.state if subscription else STATE_CANCELED,
        effective_at=subscription.current_period_end if subscription else None,
        purchased_remaining_cents=credits_to_cents(int(row[0])) if row else 0,
        purchased_expires_at=row[1] if row else expires_at,
    )


# ── Spec 041: the card on file and how it is charged ────────────────────────


class _ChargingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str
    recharge_threshold_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    recharge_amount_cents: int | None = Field(default=None, ge=0, le=10_000_000)


def _rule(exc: BillingRuleError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code}
    )


@router.get("/card", response_model=BillingView)
async def get_card(
    principal: ConsolePrincipal = Depends(require_console_principal("billing:read")),
) -> BillingView:
    return await billing_view(principal.partner.id)


@router.post("/card", response_model=CheckoutOut)
async def start_card(
    principal: ConsolePrincipal = Depends(require_console_principal("billing:manage")),
    session: AsyncSession = Depends(get_db_session),
) -> CheckoutOut:
    """Open Stripe's page to save (or replace) the card. No card data comes here."""
    try:
        async with session.begin():
            url = await open_card_setup(session, principal.partner)
    except BillingUnavailable as exc:
        raise _unavailable() from exc
    except Exception as exc:
        raise _refused(exc) from exc
    return CheckoutOut(url=url)


@router.delete("/card", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(
    principal: ConsolePrincipal = Depends(require_console_principal("billing:manage")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    try:
        async with session.begin():
            await remove_card(session, partner_id=principal.partner.id, actor=principal.actor)
    except BillingUnavailable as exc:
        raise _unavailable() from exc
    except Exception as exc:
        raise _refused(exc) from exc


@router.put("/charging", response_model=BillingView)
async def put_charging(
    body: _ChargingIn,
    principal: ConsolePrincipal = Depends(require_console_principal("billing:manage")),
    session: AsyncSession = Depends(get_db_session),
) -> BillingView:
    """Manual, automatic recharge, or postpaid (only with Auphere's credit line)."""
    try:
        async with session.begin():
            await set_charging(
                session,
                partner_id=principal.partner.id,
                mode=body.mode,
                threshold_cents=body.recharge_threshold_cents,
                amount_cents=body.recharge_amount_cents,
                actor=principal.actor,
            )
    except BillingRuleError as exc:
        raise _rule(exc) from exc
    return await billing_view(principal.partner.id)
