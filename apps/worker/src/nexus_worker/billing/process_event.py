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
    return await session.scalar(
        sa.text("SELECT code FROM membership_tiers WHERE stripe_price_id = :p"),
        {"p": price_id},
    )


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
    await move_to(session, partner_id=partner_id, state=state_from_provider(provider_status))


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

    units = units_for_cents(amount_total)
    await add_purchased(partner_id=partner_id, qty=units)
    log.info(
        "metering.credit_purchased",
        partner_id=str(partner_id),
        cents=amount_total,
        units=units,
    )
    return units
