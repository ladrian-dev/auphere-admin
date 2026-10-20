"""A partner's card on file and its automatic charges (spec 041).

The partner saves a card on a Stripe-hosted page (Checkout, ``mode=setup``):
no card data ever reaches Auphere. With a card, the partner chooses how it is
charged:

- ``manual`` — buys balance by hand, as before.
- ``auto_recharge`` — when the purchased balance falls below a threshold, a
  fixed amount is charged and credited. Still prepaid: no debt.
- ``postpaid`` — only with a credit line Auphere granted
  (``partner_wallets.credit_limit``). Consumption may take the balance below
  zero, down to the line; on the 1st the debt is charged and the balance
  returns to zero.

**Every automatic charge is a Stripe invoice** charged to the saved card
(``collection_method=charge_automatically``, paid off-session): each charge
has its fiscal document, which is what ``docs/billing.md`` asks of a payment.

**Money goes up in one place.** :func:`settle_paid_invoice` credits the
balance with ``credit_stripe`` and the key ``stripe_invoice:<id>``, whether
it is called right after paying or when ``invoice.paid`` arrives — the same
key twice credits once (spec 033). A charge row is unique on its own key, so
a retried job cannot open a second invoice for the same purpose.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import sqlalchemy as sa
import structlog
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.billing.pricing import CREDITS_PER_CENT, cents_to_credits
from nexus_api.billing.provider import get_client, idempotency_key
from nexus_api.config import get_settings
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Partner, PartnerWallet
from nexus_api.db.models.partner_billing import (
    BILLING_AUTO_RECHARGE,
    BILLING_MANUAL,
    BILLING_MODES,
    BILLING_POSTPAID,
    CHARGE_ACTION_REQUIRED,
    CHARGE_AUTO_RECHARGE,
    CHARGE_FAILED,
    CHARGE_PAID,
    CHARGE_PENDING,
    CHARGE_POSTPAID,
    MAX_FAILED_ATTEMPTS,
    MIN_RECHARGE_CENTS,
    PartnerBilling,
    PartnerCharge,
)
from nexus_api.db.models.partner_wallet import KIND_CREDIT_STRIPE
from nexus_api.repositories.audit import AuditRepository

log = structlog.get_logger(__name__)


class BillingRuleError(ValueError):
    """A request the rules refuse; ``code`` is what the screen explains."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Read a Stripe object or a plain dict alike (tests use dicts)."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


async def billing_row(session: AsyncSession, partner_id: uuid.UUID) -> PartnerBilling:
    """The partner's billing row, created on first use. Needs the partner GUC."""
    row = await session.get(PartnerBilling, partner_id)
    if row is None:
        row = PartnerBilling(partner_id=partner_id, mode=BILLING_MANUAL, failed_attempts=0)
        session.add(row)
        await session.flush()
    return row


# ── card ────────────────────────────────────────────────────────────────────


def _ensure_customer(client: Any, partner: Partner, billing: PartnerBilling) -> str:
    if billing.stripe_customer_id:
        return billing.stripe_customer_id
    customer = client.customers.create(
        cast(
            Any,
            {
                "name": partner.name,
                "email": partner.billing_email or partner.contact_email,
                # Our id travels with the customer so a notice can always be
                # traced back to a partner without trusting Stripe's id.
                "metadata": {"partner_id": str(partner.id)},
            },
        ),
        options={"idempotency_key": idempotency_key("customer", partner.id)},
    )
    billing.stripe_customer_id = str(_get(customer, "id"))
    return billing.stripe_customer_id


async def open_card_setup(session: AsyncSession, partner: Partner) -> str:
    """The Stripe page where the partner saves (or replaces) a card."""
    await apply_partner_to_session(session, partner.id)
    billing = await billing_row(session, partner.id)
    client = get_client()
    customer_id = _ensure_customer(client, partner, billing)
    base = get_settings().console_base_url.rstrip("/")
    checkout = client.checkout.sessions.create(
        cast(
            Any,
            {
                "mode": "setup",
                "currency": "usd",
                "customer": customer_id,
                # No ``payment_method_types``: Stripe refuses it now (staging,
                # 2026-10-20) and takes the methods from the Dashboard. With it
                # gone, ``currency`` is what setup mode requires.
                "client_reference_id": str(partner.id),
                "metadata": {"partner_id": str(partner.id), "kind": "card"},
                "setup_intent_data": {"metadata": {"partner_id": str(partner.id)}},
                "success_url": f"{base}/billing?card=saved",
                "cancel_url": f"{base}/billing",
            },
        ),
        options={
            "idempotency_key": idempotency_key(
                "card", partner.id, datetime.now(UTC).isoformat(timespec="seconds")
            )
        },
    )
    billing.updated_at = datetime.now(UTC)
    return str(_get(checkout, "url"))


async def apply_card_saved(session: AsyncSession, *, partner_id: uuid.UUID, checkout: Any) -> None:
    """``checkout.session.completed`` with ``mode=setup``: keep the card."""
    client = get_client()
    setup_intent = _get(checkout, "setup_intent")
    if isinstance(setup_intent, str):
        setup_intent = client.setup_intents.retrieve(
            setup_intent, cast(Any, {"expand": ["payment_method"]})
        )
    method = _get(setup_intent, "payment_method")
    if isinstance(method, str):
        method = client.payment_methods.retrieve(method)
    method_id = str(_get(method, "id") or "")
    if not method_id:
        raise BillingRuleError("no_payment_method")
    customer_id = str(_get(checkout, "customer") or "")
    # Checkout picks the methods from the Dashboard now, so what comes back is
    # not always a ``card`` (Link, for one). Staging saved one and showed
    # «terminada en · caduca 00/»: read the details again if they are missing
    # and name the method when it has no card.
    kind = str(_get(method, "type") or "")
    card = _get(method, "card")
    if not card and kind in ("", "card"):
        method = client.payment_methods.retrieve(method_id)
        kind = str(_get(method, "type") or kind)
        card = _get(method, "card")
    card = card or {}
    log.info(
        "billing.card_details",
        partner_id=str(partner_id),
        method_type=kind or None,
        has_last4=bool(_get(card, "last4")),
    )
    await apply_partner_to_session(session, partner_id)
    billing = await billing_row(session, partner_id)
    if customer_id:
        billing.stripe_customer_id = customer_id
    if not billing.stripe_customer_id:
        raise BillingRuleError("no_customer")
    # The saved card pays the invoices: Stripe charges the default method.
    client.customers.update(
        str(billing.stripe_customer_id),
        cast(Any, {"invoice_settings": {"default_payment_method": method_id}}),
    )
    billing.payment_method_id = method_id
    billing.card_brand = str(_get(card, "brand") or "") or (kind if kind != "card" else "") or None
    billing.card_last4 = str(_get(card, "last4") or "") or None
    billing.card_exp_month = _get(card, "exp_month")
    billing.card_exp_year = _get(card, "exp_year")
    billing.card_updated_at = datetime.now(UTC)
    # A new card is a fresh start for automatic charges.
    billing.failed_attempts = 0
    billing.paused_reason = None
    billing.updated_at = datetime.now(UTC)
    await AuditRepository(session).record(
        actor=f"partner:{partner_id}",
        action="billing.card_saved",
        target=f"partner:{partner_id}",
        after={"brand": billing.card_brand, "last4": billing.card_last4},
        platform=True,
    )


async def remove_card(session: AsyncSession, *, partner_id: uuid.UUID, actor: str) -> None:
    await apply_partner_to_session(session, partner_id)
    billing = await billing_row(session, partner_id)
    if billing.payment_method_id:
        try:
            get_client().payment_methods.detach(billing.payment_method_id)
        except Exception as exc:  # pragma: no cover - forgetting it locally still holds
            log.warning("billing.card_detach_failed", partner_id=str(partner_id), error=str(exc))
    before = {"last4": billing.card_last4, "mode": billing.mode}
    billing.payment_method_id = None
    billing.card_brand = billing.card_last4 = None
    billing.card_exp_month = billing.card_exp_year = None
    billing.card_updated_at = datetime.now(UTC)
    # Without a card nothing can be charged automatically.
    billing.mode = BILLING_MANUAL
    billing.updated_at = datetime.now(UTC)
    await AuditRepository(session).record(
        actor=actor,
        action="billing.card_removed",
        target=f"partner:{partner_id}",
        before=before,
        platform=True,
    )


# ── how the card is charged ─────────────────────────────────────────────────


async def set_charging(
    session: AsyncSession,
    *,
    partner_id: uuid.UUID,
    mode: str,
    threshold_cents: int | None,
    amount_cents: int | None,
    actor: str,
) -> PartnerBilling:
    if mode not in BILLING_MODES:
        raise BillingRuleError("unknown_mode")
    await apply_partner_to_session(session, partner_id)
    billing = await billing_row(session, partner_id)
    if mode != BILLING_MANUAL and not billing.has_card:
        raise BillingRuleError("card_required")
    if mode == BILLING_AUTO_RECHARGE:
        if threshold_cents is None or threshold_cents < 0:
            raise BillingRuleError("threshold_required")
        if amount_cents is None or amount_cents < MIN_RECHARGE_CENTS:
            raise BillingRuleError("amount_too_small")
    if mode == BILLING_POSTPAID:
        wallet = await session.get(PartnerWallet, partner_id)
        if wallet is None or int(wallet.credit_limit or 0) <= 0:
            raise BillingRuleError("no_credit_line")
    before = {
        "mode": billing.mode,
        "threshold_cents": billing.recharge_threshold_cents,
        "amount_cents": billing.recharge_amount_cents,
    }
    billing.mode = mode
    billing.recharge_threshold_cents = threshold_cents if mode == BILLING_AUTO_RECHARGE else None
    billing.recharge_amount_cents = amount_cents if mode == BILLING_AUTO_RECHARGE else None
    billing.updated_at = datetime.now(UTC)
    await AuditRepository(session).record(
        actor=actor,
        action="billing.charging_set",
        target=f"partner:{partner_id}",
        before=before,
        after={
            "mode": mode,
            "threshold_cents": billing.recharge_threshold_cents,
            "amount_cents": billing.recharge_amount_cents,
        },
        platform=True,
    )
    return billing


async def set_credit_limit(
    session: AsyncSession, *, partner_id: uuid.UUID, credit_limit_cents: int, actor: str
) -> int:
    """Auphere grants (or withdraws) a postpaid line. Withdrawing it below the
    current debt is refused: the database CHECK would, and a clear code is
    better than an integrity error."""
    if credit_limit_cents < 0:
        raise BillingRuleError("negative_limit")
    await apply_partner_to_session(session, partner_id)
    wallet = await session.get(PartnerWallet, partner_id, with_for_update=True)
    if wallet is None:
        raise BillingRuleError("no_wallet")
    limit = cents_to_credits(credit_limit_cents)
    if int(wallet.purchased_remaining) < -limit:
        raise BillingRuleError("limit_below_debt")
    billing = await billing_row(session, partner_id)
    before = int(billing.granted_credit_limit or wallet.credit_limit or 0)
    billing.granted_credit_limit = limit
    # While a failed postpaid charge keeps the line frozen, the wallet stays at
    # what is owed; the new line applies when the debt is paid.
    if billing.credit_frozen_at is None:
        wallet.credit_limit = limit
    if limit == 0 and billing.mode == BILLING_POSTPAID:
        # No line, no postpaid: back to buying balance by hand.
        billing.mode = BILLING_MANUAL
    await AuditRepository(session).record(
        actor=actor,
        action="billing.credit_limit_set",
        target=f"partner:{partner_id}",
        before={"credit_limit": before},
        after={"credit_limit": limit},
        platform=True,
    )
    return limit


# ── charges ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChargeOutcome:
    charge_id: uuid.UUID | None
    status: str
    detail: str | None = None


async def _open_charge(
    partner_id: uuid.UUID, *, kind: str, amount_cents: int, period: str | None, key: str
) -> uuid.UUID | None:
    """The charge row, or ``None`` if one with this key already exists."""
    try:
        async with get_sessionmaker()() as s, s.begin():
            await apply_partner_to_session(s, partner_id)
            charge = PartnerCharge(
                partner_id=partner_id,
                kind=kind,
                amount_cents=amount_cents,
                period=period,
                status=CHARGE_PENDING,
                idempotency_key=key,
            )
            s.add(charge)
            await s.flush()
            return charge.id
    except IntegrityError:
        return None


#: Stripe codes that mean «the bank wants the cardholder to confirm» — 3D
#: Secure. Not a decline: the partner confirms on Stripe's page.
_ACTION_CODES = frozenset({"authentication_required", "invoice_payment_intent_requires_action"})


def _open_invoice(
    client: Any,
    *,
    partner_id: uuid.UUID,
    customer_id: str,
    payment_method_id: str,
    charge_id: uuid.UUID,
    kind: str,
    amount_cents: int,
    description: str,
) -> str:
    """Create and finalize one invoice; returns its id. Every step carries an
    idempotency key built on our charge id."""
    meta = {"partner_id": str(partner_id), "kind": kind, "charge_id": str(charge_id)}
    client.invoice_items.create(
        cast(
            Any,
            {
                "customer": customer_id,
                "amount": amount_cents,
                "currency": "usd",
                "description": description,
                "metadata": meta,
            },
        ),
        options={"idempotency_key": idempotency_key("charge_item", partner_id, str(charge_id))},
    )
    invoice = client.invoices.create(
        cast(
            Any,
            {
                "customer": customer_id,
                "collection_method": "charge_automatically",
                "default_payment_method": payment_method_id,
                "pending_invoice_items_behavior": "include",
                "auto_advance": False,
                "metadata": meta,
                "description": description,
            },
        ),
        options={"idempotency_key": idempotency_key("charge_invoice", partner_id, str(charge_id))},
    )
    invoice_id = str(_get(invoice, "id"))
    client.invoices.finalize_invoice(invoice_id)
    return invoice_id


def _code(exc: Exception) -> str:
    return str(getattr(exc, "code", None) or type(exc).__name__)[:64]


async def charge(
    partner_id: uuid.UUID, *, kind: str, amount_cents: int, period: str | None, key: str
) -> ChargeOutcome:
    """Charge the saved card ``amount_cents`` and settle it. Safe to repeat."""
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        billing = await billing_row(s, partner_id)
        if not billing.has_card:
            return ChargeOutcome(None, "skipped", "card_required")
        customer_id = str(billing.stripe_customer_id)
        method_id = str(billing.payment_method_id)
    # Before any row: without Stripe keys this raises ``BillingUnavailable``
    # and nothing is recorded — a closed billing is not a declined card.
    client = get_client()
    charge_id = await _open_charge(
        partner_id, kind=kind, amount_cents=amount_cents, period=period, key=key
    )
    if charge_id is None:
        return ChargeOutcome(None, "duplicate")
    description = (
        f"Consumo de {period}" if kind == CHARGE_POSTPAID else "Recarga automática de saldo"
    )
    try:
        invoice_id = _open_invoice(
            client,
            partner_id=partner_id,
            customer_id=customer_id,
            payment_method_id=method_id,
            charge_id=charge_id,
            kind=kind,
            amount_cents=amount_cents,
            description=description,
        )
    except Exception as exc:
        await _record_failure(partner_id, charge_id, _code(exc), kind=kind)
        return ChargeOutcome(charge_id, CHARGE_FAILED, _code(exc))
    try:
        invoice = client.invoices.pay(invoice_id, cast(Any, {"off_session": True}))
    except Exception as exc:
        code = _code(exc)
        if code in _ACTION_CODES:
            url = _get(client.invoices.retrieve(invoice_id), "hosted_invoice_url")
            await _record_action_required(
                partner_id, charge_id, invoice_id, url, kind=kind, amount_cents=amount_cents
            )
            return ChargeOutcome(charge_id, CHARGE_ACTION_REQUIRED, code)
        await _record_failure(partner_id, charge_id, code, kind=kind, invoice_id=invoice_id)
        return ChargeOutcome(charge_id, CHARGE_FAILED, code)
    if str(_get(invoice, "status")) == "paid":
        await settle_paid_invoice(partner_id, invoice)
        return ChargeOutcome(charge_id, CHARGE_PAID)
    # Open but not paid: Stripe is waiting on the cardholder.
    await _record_action_required(
        partner_id,
        charge_id,
        invoice_id,
        _get(invoice, "hosted_invoice_url"),
        kind=kind,
        amount_cents=amount_cents,
    )
    return ChargeOutcome(charge_id, CHARGE_ACTION_REQUIRED)


async def _freeze_line(session: AsyncSession, partner_id: uuid.UUID) -> None:
    """A postpaid charge did not go through: no more consumption on credit
    until it does. The line drops to what is already owed; the debit path
    (``spendable_purchased``) then stops at zero by itself."""
    wallet = await session.get(PartnerWallet, partner_id, with_for_update=True)
    billing = await billing_row(session, partner_id)
    if wallet is None or billing.credit_frozen_at is not None:
        return
    if not billing.granted_credit_limit:
        billing.granted_credit_limit = int(wallet.credit_limit or 0)
    wallet.credit_limit = max(0, -int(wallet.purchased_remaining))
    billing.credit_frozen_at = datetime.now(UTC)
    log.warning("billing.credit_line_frozen", partner_id=str(partner_id))


async def _record_action_required(
    partner_id: uuid.UUID,
    charge_id: uuid.UUID,
    invoice_id: str,
    url: Any,
    *,
    kind: str,
    amount_cents: int,
) -> None:
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        row = await s.get(PartnerCharge, charge_id)
        if row is not None and row.status == CHARGE_PENDING:
            row.status = CHARGE_ACTION_REQUIRED
            row.stripe_invoice_id = invoice_id
            row.action_url = str(url) if url else None
        if kind == CHARGE_POSTPAID:
            await _freeze_line(s, partner_id)
        partner = await s.get(Partner, partner_id)
        to = (partner.billing_email or partner.contact_email) if partner else None
    if to and url:
        await _send_action_email(to=to, url=str(url), amount_cents=amount_cents, kind=kind)
    log.info("billing.charge_action_required", partner_id=str(partner_id))


async def _send_action_email(*, to: str, url: str, amount_cents: int, kind: str) -> None:
    from html import escape

    from nexus_api.services.email import send_email

    what = "el consumo del mes" if kind == CHARGE_POSTPAID else "la recarga automática de saldo"
    amount = f"US${amount_cents / 100:,.2f}"
    await send_email(
        to=to,
        subject="Confirma el cobro de tu tarjeta",
        html=(
            f"<p>Tu banco pide confirmar el cobro de <strong>{escape(amount)}</strong> por "
            f"{escape(what)} en Auphere.</p>"
            f'<p><a href="{escape(url)}">Confirmar el pago</a></p>'
            "<p>Hasta que lo confirmes, el cobro queda pendiente.</p>"
        ),
    )


async def _record_failure(
    partner_id: uuid.UUID,
    charge_id: uuid.UUID,
    code: str,
    *,
    kind: str,
    invoice_id: str | None = None,
) -> None:
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        row = await s.get(PartnerCharge, charge_id)
        if kind == CHARGE_POSTPAID:
            await _freeze_line(s, partner_id)
        if row is not None and invoice_id and not row.stripe_invoice_id:
            # A declined invoice still exists in Stripe: the partner can see it.
            row.stripe_invoice_id = invoice_id
        if row is not None and row.status in (CHARGE_PENDING, CHARGE_ACTION_REQUIRED):
            row.status = CHARGE_FAILED
            row.failure_code = code
            row.settled_at = datetime.now(UTC)
        billing = await billing_row(s, partner_id)
        billing.failed_attempts = int(billing.failed_attempts or 0) + 1
        if billing.failed_attempts >= MAX_FAILED_ATTEMPTS:
            billing.paused_reason = code or "card_declined"
        billing.updated_at = datetime.now(UTC)
    log.warning("billing.charge_failed", partner_id=str(partner_id), code=code)


async def settle_paid_invoice(partner_id: uuid.UUID, invoice: Any) -> bool:
    """Credit a paid invoice once. Returns True if this call credited it."""
    from nexus_api.metering.wallet import add_purchased

    meta = _get(invoice, "metadata") or {}
    kind = str(_get(meta, "kind") or "")
    if kind not in (CHARGE_AUTO_RECHARGE, CHARGE_POSTPAID):
        return False
    amount = int(_get(invoice, "amount_paid") or 0)
    if amount <= 0:
        return False
    invoice_id = str(_get(invoice, "id"))
    result = await add_purchased(
        partner_id,
        amount * CREDITS_PER_CENT,
        kind=KIND_CREDIT_STRIPE,
        idempotency_key=f"stripe_invoice:{invoice_id}",
    )
    raw_charge = str(_get(meta, "charge_id") or "")
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        if raw_charge:
            row = await s.get(PartnerCharge, uuid.UUID(raw_charge))
            if row is not None and row.status != CHARGE_PAID:
                row.status = CHARGE_PAID
                row.stripe_invoice_id = invoice_id
                row.failure_code = None
                row.action_url = None
                row.settled_at = datetime.now(UTC)
        billing = await billing_row(s, partner_id)
        billing.failed_attempts = 0
        billing.paused_reason = None
        if kind == CHARGE_POSTPAID and billing.credit_frozen_at is not None:
            # The debt is paid: the line Auphere granted is back.
            wallet = await s.get(PartnerWallet, partner_id, with_for_update=True)
            if wallet is not None:
                wallet.credit_limit = int(billing.granted_credit_limit or 0)
            billing.credit_frozen_at = None
    return not result.duplicate


class UnknownCharge(LookupError):
    """The charge is not this partner's, or does not exist."""


async def charge_invoice_url(partner_id: uuid.UUID, charge_id: uuid.UUID) -> str | None:
    """Stripe's page for the invoice of one charge, or ``None`` if there is none.

    The owner asked to see the invoices of the automatic top-ups (2026-10-20).
    Read fresh from Stripe on each click rather than stored: the hosted page
    is what Stripe keeps current (paid, refunded, the PDF). A charge from
    before the invoice id was kept on failures is found by its metadata.
    """
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        row = await s.get(PartnerCharge, charge_id)
        if row is None or row.partner_id != partner_id:
            raise UnknownCharge(str(charge_id))
        invoice_id = row.stripe_invoice_id
    client = get_client()
    invoice: Any = None
    if invoice_id:
        invoice = client.invoices.retrieve(invoice_id)
    else:
        found = client.invoices.search(
            cast(Any, {"query": f"metadata['charge_id']:'{charge_id}'", "limit": 1})
        )
        data = _get(found, "data") or []
        invoice = data[0] if data else None
        if invoice is not None:
            async with get_sessionmaker()() as s, s.begin():
                await apply_partner_to_session(s, partner_id)
                row = await s.get(PartnerCharge, charge_id)
                if row is not None and not row.stripe_invoice_id:
                    row.stripe_invoice_id = str(_get(invoice, "id"))
    if invoice is None:
        return None
    url = _get(invoice, "hosted_invoice_url") or _get(invoice, "invoice_pdf")
    return str(url) if url else None


async def record_invoice_failed(partner_id: uuid.UUID, invoice: Any) -> None:
    """``invoice.payment_failed`` for one of our charges."""
    meta = _get(invoice, "metadata") or {}
    raw_charge = str(_get(meta, "charge_id") or "")
    if not raw_charge:
        return
    error = _get(_get(invoice, "last_finalization_error"), "code") or "payment_failed"
    kind = str(_get(meta, "kind") or "")
    await _record_failure(
        partner_id,
        uuid.UUID(raw_charge),
        str(error),
        kind=kind,
        invoice_id=str(_get(invoice, "id") or "") or None,
    )


# ── what the crons do ───────────────────────────────────────────────────────


async def _partner_ids() -> list[uuid.UUID]:
    async with get_sessionmaker()() as s, s.begin():
        return list((await s.execute(sa.select(Partner.id))).scalars().all())


async def refresh_waiting_charges() -> int:
    """Settle the charges Stripe already paid that we still see waiting.

    A charge waiting on 3D Secure is settled by ``invoice.paid``. If that
    notice is lost — or, as in staging on 2026-10-20, read wrong and skipped —
    the charge would wait forever and block every later top-up. Each pass asks
    Stripe about the waiting ones; a paid invoice settles through the same
    single path (:func:`settle_paid_invoice`), so nothing is credited twice.
    Returns how many it settled.
    """
    client = get_client()
    settled = 0
    for partner_id in await _partner_ids():
        async with get_sessionmaker()() as s, s.begin():
            await apply_partner_to_session(s, partner_id)
            invoice_ids = [
                str(i)
                for i in (
                    await s.execute(
                        sa.select(PartnerCharge.stripe_invoice_id).where(
                            PartnerCharge.partner_id == partner_id,
                            PartnerCharge.status == CHARGE_ACTION_REQUIRED,
                            PartnerCharge.stripe_invoice_id.is_not(None),
                        )
                    )
                )
                .scalars()
                .all()
            ]
        for invoice_id in invoice_ids:
            try:
                invoice = client.invoices.retrieve(invoice_id)
            except Exception as exc:  # one partner's hiccup never stops the pass
                log.warning("billing.refresh_failed", partner_id=str(partner_id), error=str(exc))
                continue
            if str(_get(invoice, "status") or "") == "paid":
                await settle_paid_invoice(partner_id, invoice)
                settled += 1
    return settled


async def run_auto_recharges() -> list[ChargeOutcome]:
    """Top up every auto-recharge partner below its threshold."""
    out: list[ChargeOutcome] = []
    for partner_id in await _partner_ids():
        async with get_sessionmaker()() as s, s.begin():
            await apply_partner_to_session(s, partner_id)
            billing = await s.get(PartnerBilling, partner_id)
            wallet = await s.get(PartnerWallet, partner_id)
            if (
                billing is None
                or wallet is None
                or billing.mode != BILLING_AUTO_RECHARGE
                or billing.paused_reason
                or not billing.has_card
                or billing.recharge_amount_cents is None
                or billing.recharge_threshold_cents is None
            ):
                continue
            balance_cents = int(wallet.purchased_remaining) // CREDITS_PER_CENT
            if balance_cents >= billing.recharge_threshold_cents:
                continue
            pending = await s.scalar(
                sa.select(sa.func.count()).where(
                    PartnerCharge.partner_id == partner_id,
                    PartnerCharge.status.in_((CHARGE_PENDING, CHARGE_ACTION_REQUIRED)),
                )
            )
            if pending:
                continue
            amount = int(billing.recharge_amount_cents)
            # How many charges this partner has had: only ever grows, so a new
            # attempt never reuses a key, while two runs at the same moment
            # compute the same one and the unique key lets only one through.
            seq = int(
                await s.scalar(
                    sa.select(sa.func.count()).where(PartnerCharge.partner_id == partner_id)
                )
                or 0
            )
        key = f"autorecharge:{partner_id}:{seq}"
        out.append(
            await charge(
                partner_id, kind=CHARGE_AUTO_RECHARGE, amount_cents=amount, period=None, key=key
            )
        )
    return out


def _previous_month(now: datetime) -> str:
    year, month = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
    return f"{year:04d}-{month:02d}"


async def run_postpaid_settlement(now: datetime | None = None) -> list[ChargeOutcome]:
    """Charge every postpaid partner what it owes.

    On the 1st it charges last month's debt. A charge that did not go through
    froze the line (:func:`_freeze_line`) and is **retried at most once a
    day** — the key carries the day — until it is paid or three declines in a
    row stop it (a new card resumes it). A month already paid, or waiting on
    the partner's 3D Secure confirmation, is not charged again.
    """
    now = now or datetime.now(UTC)
    period = _previous_month(now)
    out: list[ChargeOutcome] = []
    for partner_id in await _partner_ids():
        async with get_sessionmaker()() as s, s.begin():
            await apply_partner_to_session(s, partner_id)
            billing = await s.get(PartnerBilling, partner_id)
            wallet = await s.get(PartnerWallet, partner_id)
            if (
                billing is None
                or wallet is None
                or billing.mode != BILLING_POSTPAID
                or billing.paused_reason
            ):
                continue
            if now.day != 1 and billing.credit_frozen_at is None:
                continue
            owed_credits = -int(wallet.purchased_remaining)
            if owed_credits <= 0:
                continue
            key = f"postpaid:{partner_id}:{period}:{now:%Y%m%d}"
            tried_today = await s.scalar(
                sa.select(sa.func.count()).where(PartnerCharge.idempotency_key == key)
            )
            if tried_today:
                continue
            settled_or_waiting = await s.scalar(
                sa.select(sa.func.count()).where(
                    PartnerCharge.partner_id == partner_id,
                    PartnerCharge.kind == CHARGE_POSTPAID,
                    PartnerCharge.period == period,
                    PartnerCharge.status.in_((CHARGE_PAID, CHARGE_PENDING, CHARGE_ACTION_REQUIRED)),
                )
            )
            if settled_or_waiting:
                continue
        # Rounded UP to the cent: charging less than the debt would leave a
        # sliver that never closes; at most one cent more returns as balance.
        amount = -(-owed_credits // CREDITS_PER_CENT)
        out.append(
            await charge(
                partner_id,
                kind=CHARGE_POSTPAID,
                amount_cents=amount,
                period=period,
                key=key,
            )
        )
    return out


# ── what the screens read ───────────────────────────────────────────────────


class CardView(BaseModel):
    brand: str | None
    last4: str | None
    exp_month: int | None
    exp_year: int | None
    #: When the partner saved (or last replaced) it.
    saved_at: datetime | None = None


class ChargeView(BaseModel):
    id: uuid.UUID
    kind: str
    amount_cents: int
    period: str | None
    status: str
    failure_code: str | None
    #: Stripe's page to confirm a charge the bank wants authenticated.
    action_url: str | None = None
    #: Stripe issued an invoice for it (``charge_invoice_url`` opens it).
    has_invoice: bool = False
    created_at: datetime
    settled_at: datetime | None


class BillingView(BaseModel):
    card: CardView | None
    mode: str
    recharge_threshold_cents: int | None
    recharge_amount_cents: int | None
    #: The postpaid line Auphere granted, in cents; 0 = prepaid only.
    credit_limit_cents: int
    #: A failed postpaid charge froze the line at what is owed.
    credit_frozen: bool = False
    #: What a postpaid partner owes right now, in cents.
    owed_cents: int
    paused_reason: str | None
    failed_attempts: int
    charges: list[ChargeView]


async def billing_view(partner_id: uuid.UUID) -> BillingView:
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        billing = await s.get(PartnerBilling, partner_id)
        wallet = await s.get(PartnerWallet, partner_id)
        charges = (
            (
                await s.execute(
                    sa.select(PartnerCharge)
                    .where(PartnerCharge.partner_id == partner_id)
                    .order_by(PartnerCharge.created_at.desc())
                    .limit(12)
                )
            )
            .scalars()
            .all()
        )
        raw = int(wallet.purchased_remaining) if wallet else 0
        return BillingView(
            card=(
                CardView(
                    brand=billing.card_brand,
                    last4=billing.card_last4,
                    exp_month=billing.card_exp_month,
                    exp_year=billing.card_exp_year,
                    saved_at=billing.card_updated_at,
                )
                if billing is not None and billing.has_card
                else None
            ),
            mode=billing.mode if billing else BILLING_MANUAL,
            recharge_threshold_cents=billing.recharge_threshold_cents if billing else None,
            recharge_amount_cents=billing.recharge_amount_cents if billing else None,
            credit_limit_cents=(
                int(billing.granted_credit_limit or 0)
                if billing is not None and billing.granted_credit_limit
                else (int(wallet.credit_limit or 0) if wallet else 0)
            )
            // CREDITS_PER_CENT,
            credit_frozen=billing is not None and billing.credit_frozen_at is not None,
            # Rounded up: a debt of a fraction of a cent is still owed.
            owed_cents=-(-max(0, -raw) // CREDITS_PER_CENT),
            paused_reason=billing.paused_reason if billing else None,
            failed_attempts=int(billing.failed_attempts or 0) if billing else 0,
            charges=[
                ChargeView(
                    id=c.id,
                    kind=c.kind,
                    amount_cents=c.amount_cents,
                    period=c.period,
                    status=c.status,
                    failure_code=c.failure_code,
                    action_url=c.action_url if c.status == CHARGE_ACTION_REQUIRED else None,
                    # A settled charge may still lack the id (before it was
                    # kept on failures): the link finds it by metadata.
                    has_invoice=bool(c.stripe_invoice_id) or c.status != CHARGE_PENDING,
                    created_at=c.created_at,
                    settled_at=c.settled_at,
                )
                for c in charges
            ],
        )


class BillingSummary(BaseModel):
    """What a list of partners shows about each one's card and charging."""

    mode: str
    card_brand: str | None
    card_last4: str | None
    card_saved_at: datetime | None
    paused_reason: str | None
    #: A failed postpaid charge froze the line (spec 041).
    credit_frozen: bool = False


async def billing_summary(partner_id: uuid.UUID) -> BillingSummary:
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        billing = await s.get(PartnerBilling, partner_id)
        if billing is None:
            return BillingSummary(
                mode=BILLING_MANUAL,
                card_brand=None,
                card_last4=None,
                card_saved_at=None,
                paused_reason=None,
            )
        has = billing.has_card
        return BillingSummary(
            mode=billing.mode,
            card_brand=billing.card_brand if has else None,
            card_last4=billing.card_last4 if has else None,
            card_saved_at=billing.card_updated_at if has else None,
            paused_reason=billing.paused_reason,
            credit_frozen=billing.credit_frozen_at is not None,
        )
