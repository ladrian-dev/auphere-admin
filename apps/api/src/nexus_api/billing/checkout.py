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
from typing import Any, cast

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
        cast(Any, params),
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
        cast(Any, params),
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
    "schedule_downgrade",
    "upgrade_subscription",
]


def upgrade_subscription(
    *,
    partner_id: uuid.UUID,
    subscription_id: str,
    price_id: str,
    period_tag: str = "",
) -> None:
    """Move a live subscription up a tier, now.

    **The proration is Stripe's job**, not ours: ``create_prorations`` makes it
    compute the unused remainder of the current period and credit it against
    the new price. Working out the days ourselves would be reimplementing —
    worse — something the provider already does, and that has to match what
    the customer later reads on their invoice. Two answers to the same
    question is how a billing dispute starts.

    ``proration_behavior`` and the item swap go together: Stripe needs the
    subscription item's id to know which line is being replaced, so the
    subscription is fetched first.
    """
    client = get_client()
    subscription = client.subscriptions.retrieve(subscription_id)
    items = getattr(subscription, "items", None)
    data = getattr(items, "data", None) or []
    if not data:
        raise BillingUnavailable(f"la suscripción {subscription_id} no tiene líneas")

    client.subscriptions.update(
        subscription_id,
        {
            "items": [{"id": data[0].id, "price": price_id}],
            # Stripe prorrates: the unused part of what they already paid is
            # credited against the new price, on their next invoice.
            "proration_behavior": "create_prorations",
        },
        options={
            "idempotency_key": idempotency_key("sub", partner_id, "upgrade", price_id, period_tag)
        },
    )
    log.info("metering.subscription_upgraded", partner_id=str(partner_id))


def schedule_downgrade(
    *,
    partner_id: uuid.UUID,
    subscription_id: str,
    price_id: str,
    period_tag: str = "",
) -> None:
    """Move a subscription down a tier **at the end of the paid period**.

    A Subscription Schedule with ``proration_behavior='none'``: nothing is
    refunded and nothing is cut mid-week, because the partner paid for this
    week in full. Applying a downgrade immediately would take back something
    already bought — which is the same mistake as reclaiming the pool.

    The schedule is created from the existing subscription so its current
    phase is preserved; the new price becomes the phase that follows.
    """
    client = get_client()
    schedule = client.subscription_schedules.create(
        {"from_subscription": subscription_id},
        options={
            "idempotency_key": idempotency_key("sched", partner_id, "create", subscription_id)
        },
    )
    phases = list(getattr(schedule, "phases", None) or [])
    if not phases:
        raise BillingUnavailable("el calendario de suscripción llegó sin fases")

    current = phases[0]
    client.subscription_schedules.update(
        schedule.id,
        cast(
            Any,
            {
                "phases": [
                    {
                        "items": [
                            {"price": item.price, "quantity": getattr(item, "quantity", 1)}
                            for item in (getattr(current, "items", None) or [])
                        ],
                        "start_date": getattr(current, "start_date", None),
                        "end_date": getattr(current, "end_date", None),
                    },
                    {"items": [{"price": price_id, "quantity": 1}]},
                ],
                # Nothing refunded, nothing cut mid-period.
                "proration_behavior": "none",
            },
        ),
        options={
            "idempotency_key": idempotency_key(
                "sched", partner_id, "downgrade", price_id, period_tag
            )
        },
    )
    log.info("metering.subscription_downgrade_scheduled", partner_id=str(partner_id))
