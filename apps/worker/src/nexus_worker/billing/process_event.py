"""Spec 005 · apply a provider notice to our own book.

This runs **outside** the webhook, and that is not an optimisation: Stripe
waits up to 10 seconds for the response to ``checkout.session.completed``
before redirecting the customer to the thank-you page, and a thank-you page
that takes ten seconds reads as a failed payment.

Two rules govern everything here.

**The body is data; the object is fetched.** The notice says *what happened*;
the amount and the status are read from the provider's API using the object's
id. Stripe asks for this because the body can be stale, and principle III asks
for it because what arrives from outside is data and never an instruction.
They agree. An amount that came in the body credits nothing.

**Reconciliation runs one way.** Nothing here subtracts balance. A confirmed
payment adds; a refund is an operator's decision with a trail (ADR-037 D3). A
structural test refuses an import of ``debit_wallet`` into the billing
package, because getting this wrong means money a partner paid disappearing —
and they find out when their agent goes quiet.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
import structlog

log = structlog.get_logger(__name__)

BILLING_EVENT_STREAM = "nexus:billing:events"
GROUP = "billing-workers"
DLQ_STREAM = "nexus:billing:events:dlq"


class Skip(Exception):
    """Nothing to do for this notice. Not an error — acknowledge and move on."""


async def _tier_for_price(session: Any, price_id: str | None) -> str | None:
    if not price_id:
        return None
    code: str | None = await session.scalar(
        sa.text("SELECT code FROM membership_tiers WHERE stripe_price_id = :p"),
        {"p": price_id},
    )
    return code


async def apply_invoice_paid(session: Any, *, partner_id: uuid.UUID, invoice: Any) -> None:
    """Money arrived. Grant the tier and size the pool in the same act.

    Verified 2026-09-12: access is provisioned on ``invoice.paid`` **when the
    subscription status is ``active``**. Granting on the notice alone would
    hand the tier to a subscription that is still incomplete.
    """
    from nexus_api.billing.ladder import grant_tier

    lines = getattr(invoice, "lines", None)
    price_id = None
    if lines is not None and getattr(lines, "data", None):
        pricing = getattr(lines.data[0], "pricing", None) or getattr(lines.data[0], "price", None)
        price_id = getattr(pricing, "price_details", None) or pricing
        price_id = getattr(price_id, "price", None) or getattr(pricing, "id", None)

    tier_code = await _tier_for_price(session, price_id if isinstance(price_id, str) else None)
    if tier_code is None:
        raise Skip(f"la factura no apunta a ningún nivel conocido (price={price_id!r})")

    await grant_tier(
        session,
        partner_id=partner_id,
        tier_code=tier_code,
        period_end=None,
        subscription_id=str(getattr(invoice, "subscription", "") or "") or None,
        customer_id=str(getattr(invoice, "customer", "") or "") or None,
    )


async def apply_subscription_state(session: Any, *, partner_id: uuid.UUID, sub: Any) -> None:
    """Reflect the provider's status through our exhaustive mapping."""
    from nexus_api.billing.ladder import move_to, state_from_provider

    provider_status = str(getattr(sub, "status", "") or "")
    # ``notify=True``: el partner se entera del escalón por nosotros, no porque
    # algo deje de funcionar (R5.6). El aviso se deduplica por escalón, así que
    # los reintentos de Stripe no se convierten en cinco notificaciones.
    await move_to(
        session,
        partner_id=partner_id,
        state=state_from_provider(provider_status),
        notify=True,
    )


async def apply_credit_purchase(session: Any, *, partner_id: uuid.UUID, checkout: Any) -> int:
    """Credit a one-off purchase — the only place balance goes up from outside.

    Two gates before crediting, both from Stripe's own fulfilment guidance
    (verified 2026-09-12):

    * ``payment_status`` must not be ``unpaid``. A completed session with a
      pending payment is not a purchase.
    * fulfilment must be idempotent, because ``checkout.session.completed``
      and ``checkout.session.async_payment_succeeded`` can both arrive for
      the same session. Our unique on the event id does not catch that — they
      are different events — so the second anchor is the session id.
    """
    from nexus_api.billing.events import already_fulfilled
    from nexus_api.metering.wallet import add_purchased

    payment_status = str(getattr(checkout, "payment_status", "") or "")
    if payment_status == "unpaid":
        raise Skip("la sesión está completada pero el pago sigue pendiente")

    session_id = str(getattr(checkout, "id", "") or "")
    if session_id and await already_fulfilled(session, session_id):
        raise Skip(f"la compra {session_id} ya se acreditó")

    amount_total = int(getattr(checkout, "amount_total", 0) or 0)
    if amount_total <= 0:
        raise Skip("importe no positivo")

    # Cents to quota units, at the sold rate. Kept as a single named step so
    # the conversion is greppable when the rate changes.
    from nexus_api.billing.pricing import units_for_cents

    units: int = units_for_cents(amount_total)
    await add_purchased(partner_id=partner_id, qty=units)
    log.info(
        "metering.credit_purchased",
        partner_id=str(partner_id),
        cents=amount_total,
        units=units,
    )
    return units


# ── The consumer ─────────────────────────────────────────────────────────────


async def ensure_group(redis: Any) -> None:
    from redis.exceptions import ResponseError

    try:
        await redis.xgroup_create(BILLING_EVENT_STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def _decode(raw: dict[Any, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in raw.items():
        ks = key.decode() if isinstance(key, bytes) else str(key)
        vs = value.decode() if isinstance(value, bytes) else str(value)
        out[ks] = vs
    return out


async def handle_entry(session: Any, client: Any, fields: dict[str, str]) -> str:
    """Apply one notice. Returns the status to record on the event row.

    The object is **fetched from the provider**, never read out of the body:
    the body says what happened, the provider says what it is worth. That is
    Stripe's own guidance (the body can be stale) and principle III at the
    same time — what arrives from outside is data.
    """
    from nexus_api.billing.ladder import flag_finalization_failure

    event_type = fields.get("event_type", "")
    raw_partner = fields.get("partner_id") or ""
    partner_id = uuid.UUID(raw_partner) if raw_partner else None

    if event_type == "invoice.finalization_failed":
        # Degrades nobody. An invoice that will not finalize is coverage
        # without revenue and gives no other symptom (research D10).
        await flag_finalization_failure(
            session, partner_id=partner_id, reason=fields.get("provider_event_id", "")
        )
        return "processed"

    if partner_id is None:
        # An orphan notice is kept, not dropped: losing the trail of a notice
        # about money is worse than having a row nobody can act on.
        log.warning("metering.billing_event_orphan", event_type=event_type)
        return "failed"

    if event_type == "invoice.paid":
        invoice = client.invoices.retrieve(fields.get("object_id") or "")
        await apply_invoice_paid(session, partner_id=partner_id, invoice=invoice)
        return "processed"

    if event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
        sub = client.subscriptions.retrieve(fields.get("object_id") or "")
        await apply_subscription_state(session, partner_id=partner_id, sub=sub)
        return "processed"

    if event_type in {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
    }:
        checkout = client.checkout.sessions.retrieve(fields.get("checkout_session_id") or "")
        await apply_credit_purchase(session, partner_id=partner_id, checkout=checkout)
        return "processed"

    if event_type in {"invoice.payment_failed", "invoice.upcoming"}:
        from nexus_api.billing.ladder import move_to
        from nexus_api.db.models.membership import STATE_PAYMENT_FAILED

        if event_type == "invoice.payment_failed":
            await move_to(session, partner_id=partner_id, state=STATE_PAYMENT_FAILED, notify=True)
        return "processed"

    return "ignored"
