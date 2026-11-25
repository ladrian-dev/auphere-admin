"""La membresía de un cliente — spec 077, requisitos 6, 7 y 8.

Un cliente con membresía solo envía mientras esté activa (la puerta vive en
``services/membership_gate``). Aquí se configura y se mantiene al día:

* **Por Stripe** (``payer='stripe'``): el operador crea un enlace de pago; el
  estado sale **siempre de la suscripción leída en Stripe**, nunca del tipo de
  aviso (un aviso desordenado, o un fallo seguido de un pago, deja el estado
  que Stripe tiene ahora). Stripe pone ``past_due`` al primer cobro fallido de
  una renovación: ese es el corte que pidió Luis.
* **Del saldo del partner** (``payer='partner_wallet'``): un cargo fijo
  mensual en el libro del partner (``metering/wallet.charge_fixed_fee``). El
  periodo que toca **se guarda antes de cobrar**, y la clave del cargo sale de
  ahí: repetir tras una caída da ``duplicate`` y se trata como pagado.

Todo lo de un cliente se lee y se escribe bajo su contexto (garantía 1). Un
aviso de Stripe solo cambia la membresía cuyo cliente de Stripe es el suyo.
"""

from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
import structlog
from fastapi import HTTPException, status

from nexus_api.billing import tenant_membership as stripe_membership
from nexus_api.billing.pricing import cents_to_credits, credits_to_cents
from nexus_api.billing.provider import BillingUnavailable, field
from nexus_api.config import get_settings
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AuditLog, Partner, Tenant
from nexus_api.db.models.service_membership import (
    DEFAULT_AMOUNT_CENTS,
    PAYER_PARTNER_WALLET,
    PAYER_STRIPE,
    PAYERS,
    STATUS_ACTIVE,
    STATUS_CANCELED,
    STATUS_PAST_DUE,
    STATUS_PENDING,
    ServiceMembership,
)
from nexus_api.metering.wallet import charge_fixed_fee, fixed_fees_for, partner_id_for_tenant
from nexus_api.services.membership_gate import is_active, live_membership

log = structlog.get_logger(__name__)

#: The reason of the fixed charge (R8.7: a later rule brings its own).
FEE_REASON = "membership"
#: A wallet membership is charged this long before its period ends, so a
#: renewal never leaves a gap in sending.
RENEW_AHEAD = timedelta(hours=1)
#: How often the hourly job re-reads a Stripe membership at most.
STRIPE_REREAD_EVERY = timedelta(hours=1)
#: An active Stripe membership is re-read at least this often.
STRIPE_STALE_AFTER = timedelta(hours=24)

#: Stripe's subscription status → ours. Anything not listed is ``pending``.
_STRIPE_STATUS = {
    "active": STATUS_ACTIVE,
    "trialing": STATUS_ACTIVE,
    "past_due": STATUS_PAST_DUE,
    "unpaid": STATUS_PAST_DUE,
    "paused": STATUS_PAST_DUE,
    "canceled": STATUS_CANCELED,
    "incomplete_expired": STATUS_CANCELED,
    "incomplete": STATUS_PENDING,
}
#: A subscription in these states still exists at Stripe and can charge.
_LIVE_STRIPE = {STATUS_ACTIVE, STATUS_PAST_DUE}


def add_one_month(moment: datetime) -> datetime:
    """The same day next month, or its last day (31 Jan → 28/29 Feb)."""
    year, month = (moment.year + 1, 1) if moment.month == 12 else (moment.year, moment.month + 1)
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def map_stripe_status(raw: str | None) -> str:
    return _STRIPE_STATUS.get(str(raw or ""), STATUS_PENDING)


def _conflict(code: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=code)


def _close_link(session_id: str) -> str | None:
    """R7.13 (/cso 2026-11-24): expire an open payment link BEFORE anything
    changes, so a link at an old amount, or one nothing follows any more, is
    never left payable. Returns the subscription the link already paid, if
    it was paid. Any Stripe failure is 503 and the caller saves nothing."""
    try:
        return stripe_membership.expire_checkout_session(session_id)
    except Exception as exc:
        log.warning("membership.link_not_expired", error=str(exc)[:200])
        raise _billing_unavailable() from exc


async def _close_open_link(tenant_id: uuid.UUID) -> None:
    """Close the client's open payment link, if it has one. If the link was
    already paid without the notice arriving, that payment is applied and the
    change is refused (409 ``checkout_already_paid``): R7.14."""
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await live_membership(session)
        if (
            row is None
            or row.payer != PAYER_STRIPE
            or not row.checkout_url
            or not row.stripe_checkout_session_id
        ):
            return
        session_id, stored = row.stripe_checkout_session_id, row.stripe_subscription_id
    paid = _close_link(session_id)
    if paid and paid != stored:
        await _apply_paid_link(tenant_id, paid, session_id)
        raise _conflict("checkout_already_paid")


async def _apply_paid_link(tenant_id: uuid.UUID, subscription_id: str, session_id: str) -> None:
    try:
        sub = stripe_membership.retrieve_subscription(subscription_id)
    except Exception as exc:
        raise _billing_unavailable() from exc
    await _apply_subscription(tenant_id, sub, checkout_session_id=session_id)


def _billing_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="billing_unavailable"
    )


@dataclass(frozen=True)
class MembershipView:
    """What the panel shows (``contracts/admin-api.md``, ``MembershipOut``)."""

    tenant_id: uuid.UUID
    payer: str
    amount_cents: int
    pending_amount_cents: int | None
    status: str
    active: bool
    current_period_end: datetime | None
    billing_email: str | None
    checkout_url: str | None
    checkout_expires_at: datetime | None
    last_synced_at: datetime | None
    last_failure: str | None
    partner_id: uuid.UUID | None
    partner_name: str | None
    has_subscription: bool


async def _partner_of(session: Any, tenant_id: uuid.UUID) -> tuple[uuid.UUID | None, str | None]:
    partner_id = await partner_id_for_tenant(session, tenant_id)
    if partner_id is None:
        return None, None
    name = await session.scalar(sa.select(Partner.name).where(Partner.id == partner_id))
    return partner_id, (str(name) if name is not None else None)


def _view(
    row: ServiceMembership, partner_id: uuid.UUID | None, partner_name: str | None
) -> MembershipView:
    now = datetime.now(UTC)
    show_link = (
        row.payer == PAYER_STRIPE
        and row.status != STATUS_ACTIVE
        and row.checkout_url is not None
        and (row.checkout_expires_at is None or row.checkout_expires_at > now)
    )
    return MembershipView(
        tenant_id=row.tenant_id,
        payer=row.payer,
        amount_cents=row.amount_cents,
        pending_amount_cents=row.pending_amount_cents,
        status=row.status,
        active=is_active(row, now=now),
        current_period_end=row.current_period_end,
        billing_email=row.billing_email,
        checkout_url=row.checkout_url if show_link else None,
        checkout_expires_at=row.checkout_expires_at if show_link else None,
        last_synced_at=row.last_synced_at,
        last_failure=row.last_failure,
        partner_id=partner_id,
        partner_name=partner_name,
        has_subscription=row.stripe_subscription_id is not None and row.status in _LIVE_STRIPE,
    )


def _audit(
    session: Any,
    *,
    tenant_id: uuid.UUID,
    actor: str,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            target=f"membership:{tenant_id}",
            before_json=before,
            after_json=after,
        )
    )


def _snapshot(row: ServiceMembership | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "payer": row.payer,
        "amount_cents": row.amount_cents,
        "pending_amount_cents": row.pending_amount_cents,
        "status": row.status,
        "billing_email": row.billing_email,
    }


async def get_view(tenant_id: uuid.UUID) -> MembershipView | None:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await live_membership(session)
        if row is None:
            return None
        partner_id, partner_name = await _partner_of(session, tenant_id)
        return _view(row, partner_id, partner_name)


async def configure(
    tenant_id: uuid.UUID,
    *,
    payer: str,
    amount_cents: int,
    billing_email: str | None,
    actor: str,
) -> MembershipView:
    """Create or change the client's membership (R6.2-R6.4, R6.6).

    The first time, a wallet membership is charged at once; a Stripe one
    waits for the payment link. With a live Stripe subscription neither the
    amount nor the payer can change: cancel and create a new link.
    """
    if payer not in PAYERS:
        raise HTTPException(status_code=422, detail="invalid_payer")
    if amount_cents <= 0:
        raise HTTPException(status_code=422, detail="invalid_amount")
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        current = await live_membership(session)
        changes_terms = current is not None and (
            payer != current.payer or amount_cents != current.amount_cents
        )
    if changes_terms:
        # R7.13: the open link is for the old terms. Closed first; if Stripe
        # cannot close it, nothing is saved.
        await _close_open_link(tenant_id)
    charge_now = False
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        if await session.get(Tenant, tenant_id) is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")
        partner_id, _name = await _partner_of(session, tenant_id)
        if payer == PAYER_PARTNER_WALLET and partner_id is None:
            raise HTTPException(status_code=422, detail="no_partner")
        row = await live_membership(session)
        before = _snapshot(row)
        if row is None:
            row = ServiceMembership(
                tenant_id=tenant_id,
                payer=payer,
                amount_cents=amount_cents,
                status=STATUS_PENDING,
                billing_email=billing_email,
            )
            session.add(row)
            charge_now = payer == PAYER_PARTNER_WALLET
        else:
            stripe_live = row.stripe_subscription_id is not None and row.status in _LIVE_STRIPE
            if stripe_live and (payer != row.payer or amount_cents != row.amount_cents):
                raise _conflict("subscription_in_progress")
            if payer != row.payer and is_active(row):
                raise _conflict("membership_active")
            if payer != row.payer:
                row.payer = payer
                row.status = STATUS_PENDING
                row.checkout_url = None
                row.checkout_expires_at = None
                row.current_period_start = row.current_period_end = None
                row.next_period_start = None
                row.amount_cents = amount_cents
                row.pending_amount_cents = None
                charge_now = payer == PAYER_PARTNER_WALLET
            elif amount_cents != row.amount_cents:
                if row.payer == PAYER_PARTNER_WALLET and is_active(row):
                    # R6.4: from the next period on.
                    row.pending_amount_cents = amount_cents
                else:
                    row.amount_cents = amount_cents
                    row.pending_amount_cents = None
                    # The link for the old amount was expired above: a new
                    # one has to be created.
                    row.checkout_url = None
                    row.checkout_expires_at = None
            if billing_email is not None:
                row.billing_email = billing_email
        await session.flush()
        _audit(
            session,
            tenant_id=tenant_id,
            actor=actor,
            action="membership.configure",
            before=before,
            after=_snapshot(row),
        )
    if charge_now:
        await charge_wallet_if_due(tenant_id, force=True)
    view = await get_view(tenant_id)
    assert view is not None
    return view


async def archive(tenant_id: uuid.UUID, *, actor: str) -> None:
    """Stop requiring a membership (R6.8): archived, never deleted. Its open
    payment link is expired first (R7.13)."""
    await _close_open_link(tenant_id)
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await live_membership(session)
        if row is None:
            raise HTTPException(status_code=404, detail="no_membership")
        stripe_live = row.stripe_subscription_id is not None and row.status in _LIVE_STRIPE
        if is_active(row) or stripe_live:
            raise _conflict("membership_active")
        row.archived_at = datetime.now(UTC)
        row.archived_by = actor
        row.checkout_url = None
        row.checkout_expires_at = None
        _audit(
            session,
            tenant_id=tenant_id,
            actor=actor,
            action="membership.archive",
            before=_snapshot(row),
            after=None,
        )


async def cancel(tenant_id: uuid.UUID, *, actor: str) -> MembershipView:
    """Stop charging and stop sending now (R6.5). An open payment link is
    expired first; one already paid is applied, then cancelled below too."""
    try:
        await _close_open_link(tenant_id)
    except HTTPException as exc:
        # 409 checkout_already_paid: that subscription is now the stored one,
        # and the cancel below cancels it too. A 503 stops the cancel.
        if exc.status_code != status.HTTP_409_CONFLICT:
            raise
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await live_membership(session)
        if row is None:
            raise HTTPException(status_code=404, detail="no_membership")
        subscription_id = row.stripe_subscription_id
        live = row.payer == PAYER_STRIPE and subscription_id and row.status in _LIVE_STRIPE
    if live:
        try:
            stripe_membership.cancel_subscription(str(subscription_id))
        except BillingUnavailable as exc:
            raise _billing_unavailable() from exc
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await live_membership(session)
        assert row is not None
        before = _snapshot(row)
        row.status = STATUS_CANCELED
        row.next_period_start = None
        row.checkout_url = None
        row.checkout_expires_at = None
        if row.payer == PAYER_PARTNER_WALLET:
            # Stops at once (R6.5), even inside a paid period.
            row.current_period_end = datetime.now(UTC)
        _audit(
            session,
            tenant_id=tenant_id,
            actor=actor,
            action="membership.cancel",
            before=before,
            after=_snapshot(row),
        )
    view = await get_view(tenant_id)
    assert view is not None
    return view


# ── Stripe ───────────────────────────────────────────────────────────────────


async def create_checkout(tenant_id: uuid.UUID, *, actor: str) -> tuple[str, datetime | None]:
    """A new payment link; the previous one, if still open, is expired."""
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await live_membership(session)
        if row is None:
            raise HTTPException(status_code=404, detail="no_membership")
        if row.payer != PAYER_STRIPE:
            raise _conflict("not_stripe")
        if is_active(row):
            raise _conflict("already_active")
        tenant = await session.get(Tenant, tenant_id)
        assert tenant is not None
        name, email = tenant.name, row.billing_email
        customer_id, old_session = row.stripe_customer_id, row.stripe_checkout_session_id
        stored_sub = row.stripe_subscription_id
        amount_cents = row.amount_cents
        live_sub = row.stripe_subscription_id if row.status in _LIVE_STRIPE else None
    if live_sub:
        # A failed renewal is paid on ITS invoice: a new checkout would open a
        # second subscription for the same client (security review, 077).
        try:
            invoice_url = stripe_membership.open_invoice_url(live_sub)
        except BillingUnavailable as exc:
            raise _billing_unavailable() from exc
        if not invoice_url:
            raise _conflict("subscription_in_progress")
        async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
            row = await live_membership(session)
            assert row is not None
            row.checkout_url = invoice_url
            row.checkout_expires_at = None
            _audit(
                session,
                tenant_id=tenant_id,
                actor=actor,
                action="membership.invoice_link",
                before=None,
                after={"subscription": live_sub},
            )
        return invoice_url, None
    base = get_settings().console_base_url.rstrip("/")
    try:
        if customer_id is None:
            customer_id = stripe_membership.ensure_tenant_customer(
                tenant_id=tenant_id, name=name, email=email
            )
        if old_session:
            # R7.14: a link paid without its notice is applied, never
            # followed by a second one (two paid links, two subscriptions).
            paid = _close_link(old_session)
            if paid and paid != stored_sub:
                await _apply_paid_link(tenant_id, paid, old_session)
                raise _conflict("checkout_already_paid")
        opened = stripe_membership.open_tenant_membership_session(
            tenant_id=tenant_id,
            customer_id=customer_id,
            amount_cents=amount_cents,
            product_name=f"Membresía de envío · {name}",
            success_url=f"{base}/pago-recibido",
            cancel_url=f"{base}/pago-recibido?estado=cancelado",
            stamp=datetime.now(UTC).strftime("%Y%m%d%H%M%S%f"),
        )
    except BillingUnavailable as exc:
        raise _billing_unavailable() from exc
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await live_membership(session)
        assert row is not None
        row.stripe_customer_id = customer_id
        row.stripe_checkout_session_id = opened.session_id
        row.checkout_url = opened.url
        row.checkout_expires_at = opened.expires_at
        if row.status not in _LIVE_STRIPE:
            # A new link after a cancel (or a lapsed one): the old subscription
            # is dead, so forget it. The membership waits for this payment,
            # and the refresh and the hourly job resolve it through this link
            # even if the notice of the payment is lost.
            row.status = STATUS_PENDING
            row.stripe_subscription_id = None
        _audit(
            session,
            tenant_id=tenant_id,
            actor=actor,
            action="membership.checkout_link",
            before=None,
            after={"expires_at": opened.expires_at.isoformat() if opened.expires_at else None},
        )
    return opened.url, opened.expires_at


async def _apply_subscription(
    tenant_id: uuid.UUID, sub: Any, *, checkout_session_id: str | None = None
) -> bool:
    """Copy the subscription's state onto the client's membership — **only**
    when the subscription is this client's: its customer is the one we created
    for the client, or it came from the client's current checkout session."""
    sub_id = str(field(sub, "id") or "")
    customer = field(sub, "customer")
    customer_id = str(field(customer, "id") or customer or "")
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await live_membership(session)
        if row is None or row.payer != PAYER_STRIPE:
            return False
        stored = row.stripe_subscription_id
        from_current_link = (
            checkout_session_id is not None
            and row.stripe_checkout_session_id == checkout_session_id
        )
        if stored is not None and stored != sub_id:
            # Once a subscription is ours, a different one only replaces it
            # through the client's CURRENT payment link. A late notice about
            # an older subscription of the same customer changes nothing.
            ours = from_current_link
        else:
            ours = (
                stored == sub_id
                or (row.stripe_customer_id is not None and row.stripe_customer_id == customer_id)
                or from_current_link
            )
        if not ours:
            log.warning(
                "membership.stripe_object_not_ours",
                tenant_id=str(tenant_id),
                subscription=sub_id,
            )
            return False
        start, end = stripe_membership.subscription_period(sub)
        before = row.status
        row.stripe_subscription_id = sub_id or row.stripe_subscription_id
        row.stripe_customer_id = row.stripe_customer_id or customer_id or None
        row.status = map_stripe_status(field(sub, "status"))
        row.current_period_start = start or row.current_period_start
        row.current_period_end = end or row.current_period_end
        row.last_synced_at = datetime.now(UTC)
        row.last_failure = "payment_failed" if row.status == STATUS_PAST_DUE else None
        if row.status == STATUS_ACTIVE:
            row.checkout_url = None
            row.checkout_expires_at = None
        log.info(
            "membership.stripe_state",
            tenant_id=str(tenant_id),
            before=before,
            after=row.status,
        )
        return True


async def refresh_from_stripe(tenant_id: uuid.UUID) -> MembershipView:
    """Re-read Stripe (R7.7): the subscription, or the one behind the stored
    checkout session if no notice told us yet."""
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await live_membership(session)
        if row is None:
            raise HTTPException(status_code=404, detail="no_membership")
        if row.payer != PAYER_STRIPE:
            raise _conflict("not_stripe")
        sub_id, session_id = row.stripe_subscription_id, row.stripe_checkout_session_id
    try:
        if sub_id is None and session_id:
            checkout = stripe_membership.retrieve_checkout_session(session_id)
            found = field(checkout, "subscription")
            sub_id = str(field(found, "id") or found or "") or None
        if sub_id:
            await _apply_subscription(
                tenant_id,
                stripe_membership.retrieve_subscription(sub_id),
                checkout_session_id=session_id,
            )
    except BillingUnavailable as exc:
        raise _billing_unavailable() from exc
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await live_membership(session)
        if row is not None:
            row.last_synced_at = datetime.now(UTC)
    view = await get_view(tenant_id)
    assert view is not None
    return view


#: The notices that can move a client's membership.
MEMBERSHIP_EVENTS = frozenset(
    {
        "checkout.session.completed",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.paid",
        "invoice.payment_failed",
    }
)


async def apply_stripe_event(client: Any, event_type: str, fields: dict[str, str]) -> bool:
    """A Stripe notice about a client's membership (R7.2-R7.6).

    ``True`` when it was ours and applied; ``False`` sends it down the
    partners' path, untouched. The body only says what to look at: the object
    is fetched from Stripe and the state copied from the subscription.
    """
    if event_type not in MEMBERSHIP_EVENTS:
        return False
    checkout_session_id: str | None = None
    if event_type == "checkout.session.completed":
        checkout_session_id = fields.get("checkout_session_id") or fields.get("object_id") or ""
        checkout = client.checkout.sessions.retrieve(checkout_session_id)
        if not stripe_membership.is_ours(checkout):
            return False
        found = field(checkout, "subscription")
        sub_id = str(field(found, "id") or found or "")
    elif event_type.startswith("invoice."):
        invoice = client.invoices.retrieve(fields.get("object_id") or "")
        sub_id = stripe_membership.subscription_of_invoice(invoice) or ""
    else:
        sub_id = fields.get("object_id") or ""
    if not sub_id:
        return False
    sub = client.subscriptions.retrieve(sub_id)
    if not stripe_membership.is_ours(sub):
        return False
    tenant_id = stripe_membership.tenant_of(sub)
    if tenant_id is None:
        return False
    applied = await _apply_subscription(tenant_id, sub, checkout_session_id=checkout_session_id)
    # Ours by its mark even when it did not apply (a stale or foreign one):
    # never hand it to the partners' path, which would read it as an orphan.
    log.info(
        "membership.stripe_event",
        tenant_id=str(tenant_id),
        event_type=event_type,
        applied=applied,
    )
    return True


async def charges(tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    """The membership's charges (R7.10, R8.8), newest first."""
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await live_membership(session)
        if row is None:
            raise HTTPException(status_code=404, detail="no_membership")
        payer, sub_id = row.payer, row.stripe_subscription_id
        partner_id = await partner_id_for_tenant(session, tenant_id)
    if payer == PAYER_STRIPE:
        if not sub_id:
            return []
        try:
            invoices = stripe_membership.list_subscription_invoices(sub_id)
        except BillingUnavailable as exc:
            raise _billing_unavailable() from exc
        return [stripe_membership.invoice_row(i) for i in invoices]
    if partner_id is None:
        return []
    out: list[dict[str, Any]] = []
    for start, qty in await fixed_fees_for(partner_id, reason=FEE_REASON, tenant_id=tenant_id):
        out.append(
            {
                "period_start": start,
                "period_end": add_one_month(start),
                "amount_cents": credits_to_cents(qty, nearest=True),
                "status": "paid",
                "url": None,
            }
        )
    return out


# ── Del saldo del partner ────────────────────────────────────────────────────


async def charge_wallet_if_due(
    tenant_id: uuid.UUID, *, now: datetime | None = None, force: bool = False
) -> bool:
    """Charge the next period to the partner's balance when it is due (R8).

    Due = not active, or within ``RENEW_AHEAD`` of the end. ``force`` is the
    operator's «Cobrar ahora». Three short transactions, in this order: store
    the period to charge, charge it, record the outcome. A crash between the
    last two leaves the period stored, so the retry's key is the same and the
    book answers ``duplicate`` — treated as paid (R8.4). The first read locks
    the row: two runs at once (the cron and «Cobrar ahora», a double click)
    both see the period the first one stored, so they share the key.
    """
    now = now or datetime.now(UTC)
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await live_membership(session, lock=True)
        if row is None or row.payer != PAYER_PARTNER_WALLET or row.status == STATUS_CANCELED:
            return False
        end = row.current_period_end
        due = force or row.status != STATUS_ACTIVE or end is None or end - RENEW_AHEAD <= now
        if not due:
            return False
        if row.status == STATUS_ACTIVE and end is not None and end > now and force:
            # Already paid for this period: nothing to charge.
            return False
        if row.next_period_start is None:
            # On time keeps the anchor; a lapsed one starts again now.
            on_time = end is not None and end > now - RENEW_AHEAD
            row.next_period_start = end if on_time and end is not None else now
        period_start = row.next_period_start
        amount_cents = row.pending_amount_cents or row.amount_cents
        partner_id = await partner_id_for_tenant(session, tenant_id)
    if partner_id is None:
        outcome = "no_partner"
    else:
        result = await charge_fixed_fee(
            partner_id=partner_id,
            tenant_id=tenant_id,
            qty=cents_to_credits(amount_cents),
            reason=FEE_REASON,
            period_start=period_start,
        )
        outcome = result.outcome
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await live_membership(session)
        if row is None:
            return False
        if outcome in ("charged", "duplicate"):
            row.status = STATUS_ACTIVE
            row.current_period_start = period_start
            row.current_period_end = add_one_month(period_start)
            row.amount_cents = amount_cents
            row.pending_amount_cents = None
            row.last_failure = None
        else:
            # Nothing was charged: forget the period so the next try starts
            # from when the balance is there, not from today's date. A renewal
            # tried ahead of time keeps sending until the paid period ends.
            still_paid = row.current_period_end is not None and row.current_period_end > now
            row.status = (
                STATUS_ACTIVE if still_paid and row.status == STATUS_ACTIVE else (STATUS_PAST_DUE)
            )
            row.last_failure = "insufficient_balance" if outcome != "no_partner" else "no_partner"
        row.next_period_start = None
        log.info(
            "membership.wallet_charge",
            tenant_id=str(tenant_id),
            outcome=outcome,
            status=row.status,
        )
        return outcome in ("charged", "duplicate")


async def charge_now(tenant_id: uuid.UUID, *, actor: str) -> MembershipView:
    """The operator's «Cobrar ahora» for a membership paid from the balance."""
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        row = await live_membership(session, lock=True)
        if row is None:
            raise HTTPException(status_code=404, detail="no_membership")
        if row.payer != PAYER_PARTNER_WALLET:
            raise _conflict("not_wallet")
        if row.status == STATUS_CANCELED:
            # Reactivating: inside the paid period it is free, after it a
            # new period starts now (plan §E).
            row.status = STATUS_PAST_DUE
        _audit(
            session,
            tenant_id=tenant_id,
            actor=actor,
            action="membership.charge_now",
            before=_snapshot(row),
            after=None,
        )
        paid_until = row.current_period_end
    if paid_until is not None and paid_until > datetime.now(UTC):
        async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
            row = await live_membership(session)
            assert row is not None
            row.status = STATUS_ACTIVE
    else:
        await charge_wallet_if_due(tenant_id, force=True)
    view = await get_view(tenant_id)
    assert view is not None
    return view


# ── The hourly / five-minute job ─────────────────────────────────────────────


def _stripe_needs_reread(row: ServiceMembership, now: datetime) -> bool:
    last = row.last_synced_at
    if last is not None and now - last < STRIPE_REREAD_EVERY:
        return False
    if row.status == STATUS_PENDING:
        return row.stripe_checkout_session_id is not None
    if row.status == STATUS_PAST_DUE:
        return True
    if row.status == STATUS_ACTIVE:
        expired = row.current_period_end is not None and row.current_period_end <= now
        stale = last is None or now - last >= STRIPE_STALE_AFTER
        return expired or stale
    return False


async def tick(now: datetime | None = None) -> dict[str, int]:
    """One pass over the active clients: charge the wallet memberships that
    are due and re-read the Stripe ones that need it (R7.8, R8.3)."""
    from nexus_api.db.models import TenantStatus

    now = now or datetime.now(UTC)
    async with get_sessionmaker()() as session, session.begin():
        tenant_ids = list(
            (
                await session.scalars(
                    sa.select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE)
                )
            ).all()
        )
    counts = {"charged": 0, "reread": 0}
    billing_on = get_settings().billing_enabled
    for tenant_id in tenant_ids:
        try:
            async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
                row = await live_membership(session)
                payer = row.payer if row is not None else None
                reread = (
                    row is not None and payer == PAYER_STRIPE and _stripe_needs_reread(row, now)
                )
            if payer == PAYER_PARTNER_WALLET:
                if await charge_wallet_if_due(tenant_id, now=now):
                    counts["charged"] += 1
            elif reread and billing_on:
                await refresh_from_stripe(tenant_id)
                counts["reread"] += 1
        except Exception as exc:  # one client never stops the others
            log.warning("membership.tick_failed", tenant_id=str(tenant_id), error=str(exc)[:300])
    return counts


__all__ = [
    "DEFAULT_AMOUNT_CENTS",
    "FEE_REASON",
    "MEMBERSHIP_EVENTS",
    "MembershipView",
    "add_one_month",
    "apply_stripe_event",
    "archive",
    "cancel",
    "charge_now",
    "charge_wallet_if_due",
    "charges",
    "configure",
    "create_checkout",
    "get_view",
    "map_stripe_status",
    "refresh_from_stripe",
    "tick",
]
