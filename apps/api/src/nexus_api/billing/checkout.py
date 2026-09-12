"""Spec 005 · opening the provider's hosted payment page.

Hosted and not embedded: that is what keeps card data entirely outside our
infrastructure (R2.2). We never see a number, never store one, never log one.

Every session carries our ``partner_id`` in ``client_reference_id`` — verified
2026-09-12, max length 200, a UUID is 36 — so the webhook resolves the partner
**from the notice** rather than by looking up ``stripe_customer_id``. That is
what keeps the provider's identifier a replaceable reference and makes the
account migration a column update instead of a reconstruction (research D5.1).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import structlog

from nexus_api.billing.provider import BillingUnavailable, get_client, idempotency_key

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CheckoutTarget:
    """Where the customer comes back to.

    ``success_url`` carries ``{CHECKOUT_SESSION_ID}`` because the thank-you
    page needs to know which purchase it is confirming — Stripe substitutes it.
    """

    success_url: str
    cancel_url: str


def _urls(base: str) -> CheckoutTarget:
    root = base.rstrip("/")
    return CheckoutTarget(
        success_url=f"{root}/billing/gracias?session={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{root}/billing",
    )


def open_subscription_session(
    *,
    partner_id: uuid.UUID,
    price_id: str,
    console_base_url: str,
    customer_id: str | None = None,
    period_tag: str = "",
) -> str:
    """Open a subscription Checkout Session and return its URL."""
    client = get_client()
    target = _urls(console_base_url)
    params: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": target.success_url,
        "cancel_url": target.cancel_url,
        # Ours, so the notice carries it back.
        "client_reference_id": str(partner_id),
        # And on the subscription too: renewal notices are not born from a
        # Checkout Session and would otherwise arrive with no way home.
        "subscription_data": {"metadata": {"partner_id": str(partner_id)}},
    }
    if customer_id:
        params["customer"] = customer_id

    session = client.checkout.sessions.create(
        params,
        options={
            "idempotency_key": idempotency_key("sub", partner_id, "checkout", price_id, period_tag)
        },
    )
    log.info("metering.billing_checkout_opened", partner_id=str(partner_id), mode="subscription")
    return str(session.url)


def open_credit_session(
    *,
    partner_id: uuid.UUID,
    amount_cents: int,
    console_base_url: str,
    customer_id: str | None = None,
    stamp: str = "",
) -> str:
    """Open a one-time Checkout Session to buy credit."""
    client = get_client()
    target = _urls(console_base_url)
    params: dict[str, Any] = {
        "mode": "payment",
        "line_items": [
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": amount_cents,
                    "product_data": {"name": "Crédito de consumo Nexus"},
                },
                "quantity": 1,
            }
        ],
        "success_url": target.success_url,
        "cancel_url": target.cancel_url,
        "client_reference_id": str(partner_id),
        "metadata": {"partner_id": str(partner_id), "kind": "credit"},
    }
    if customer_id:
        params["customer"] = customer_id

    session = client.checkout.sessions.create(
        params,
        # The stamp matters: without it, a partner who buys 50 USD twice in a
        # row would reuse the first key and Stripe would replay the stored
        # response — a second purchase that silently does not happen.
        options={
            "idempotency_key": idempotency_key("credit", partner_id, str(amount_cents), stamp)
        },
    )
    log.info("metering.billing_checkout_opened", partner_id=str(partner_id), mode="credit")
    return str(session.url)


def open_portal(*, customer_id: str, console_base_url: str) -> str:
    """The provider's Customer Portal: card, invoices, cancellation.

    Delegated rather than built. The provider's invoices are the fiscal
    document (decided 2026-09-12), and building our own card screen would
    mean touching card data — the one thing the hosted page exists to avoid.
    """
    client = get_client()
    session = client.billing_portal.sessions.create(
        {"customer": customer_id, "return_url": f"{console_base_url.rstrip('/')}/billing"}
    )
    return str(session.url)


__all__ = [
    "BillingUnavailable",
    "open_credit_session",
    "open_portal",
    "open_subscription_session",
]
