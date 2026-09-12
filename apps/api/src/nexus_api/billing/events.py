"""Spec 005 · receiving a notice from the provider: verify, record, dispatch.

Preserves ADR-022 §13-§15 intact. The sequence, and nothing between the steps:

    1. read the body RAW (bytes, unparsed)
    2. verify the signature          -> 400 if it fails
    3. INSERT by provider_event_id   -> if it clashes, 200 and stop
    4. resolve the partner
    5. enqueue the work
    6. 200

Step 3 is where the idempotency actually lives. It is decided at the door by a
database constraint, not by the background job: two simultaneous deliveries of
the same event — which happen — mean one wins the INSERT and the other answers
200 having credited nothing.

Step 1 matters for a reason that looks like pedantry and is not: the signature
is computed over the exact bytes Stripe sent. A framework that parses and
re-serialises invalidates it over a single space, and the failure then looks
like an attack rather than a bug.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.billing_event import BillingEvent

log = structlog.get_logger(__name__)

#: The events we subscribe to. Everything else is recorded as ``ignored``.
#:
#: ``invoice.created`` is deliberately ABSENT. Verified 2026-09-12: if the
#: endpoint does not answer it properly, Stripe delays finalizing **all**
#: invoices with automatic collection for up to 72 hours — every partner's,
#: not just that one's, and with no symptom other than revenue stopping. We do
#: not need it: money arrives with ``invoice.paid``. An event you are not
#: subscribed to expects no answer.
HANDLED_EVENTS: frozenset[str] = frozenset(
    {
        "invoice.paid",
        "invoice.payment_failed",
        # The quiet one. A invoice that cannot be finalized leaves the
        # subscription ACTIVE — the partner keeps working — and nothing is
        # charged. No symptom at all (research D10).
        "invoice.finalization_failed",
        # Fires a few days before renewal. This is what satisfies R5.6:
        # warn BEFORE the service degrades, not after.
        "invoice.upcoming",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
    }
)

#: Keys stripped before the notice is stored. Stripe does not send card data,
#: so this does not protect us from them: it protects us from ourselves, the
#: day someone stores the whole object "to be able to debug".
_REDACT_KEYS = frozenset(
    {
        "card",
        "payment_method_details",
        "payment_method",
        "last4",
        "exp_month",
        "exp_year",
        "number",
        "cvc",
        "cvv",
        "fingerprint",
        "customer_details",
        "billing_details",
        "receipt_number",
    }
)


def redact_payload(payload: Any) -> Any:
    """Strip anything that looks like a payment instrument, recursively.

    Keeps what is needed to act — ids, amounts, statuses — and drops the rest.
    Deliberately a blocklist applied everywhere rather than an allowlist at
    the top level: the provider adds fields over time, and an allowlist would
    silently discard the new one that matters.
    """
    if isinstance(payload, dict):
        return {
            key: redact_payload(value) for key, value in payload.items() if key not in _REDACT_KEYS
        }
    if isinstance(payload, list):
        return [redact_payload(item) for item in payload]
    return payload


def partner_id_from(event: dict[str, Any]) -> uuid.UUID | None:
    """Our partner id, read from the notice itself.

    Every Checkout Session is opened with ``client_reference_id`` set to our
    ``partner_id``, and every subscription carries the same value in
    ``metadata``. That is what lets this resolve the partner **from the
    notice** instead of looking it up by ``stripe_customer_id`` — which would
    turn the provider's identifier into the way into a partner, exactly what
    research D5.1 avoids. It is also what makes the migration runbook's
    ``UPDATE … SET stripe_customer_id = NULL`` harmless.
    """
    obj = (event.get("data") or {}).get("object") or {}
    for candidate in (
        obj.get("client_reference_id"),
        (obj.get("metadata") or {}).get("partner_id"),
        ((obj.get("subscription_details") or {}).get("metadata") or {}).get("partner_id"),
        ((obj.get("parent") or {}).get("subscription_details") or {})
        .get("metadata", {})
        .get("partner_id"),
    ):
        if not candidate:
            continue
        try:
            return uuid.UUID(str(candidate))
        except ValueError:
            log.warning("metering.billing_event_bad_partner_ref", event_id=event.get("id"))
    return None


def object_id_from(event: dict[str, Any]) -> str | None:
    """The id of the object the notice is about.

    The worker re-fetches that object from the provider's API rather than
    trusting the body, so without this id there is nothing to fetch and the
    rule "the body is data, the object is fetched" cannot be honoured.
    """
    obj = (event.get("data") or {}).get("object") or {}
    value = obj.get("id")
    return str(value) if value else None


def checkout_session_id_from(event: dict[str, Any]) -> str | None:
    """The second idempotency anchor.

    ``checkout.session.completed`` and ``checkout.session.async_payment_succeeded``
    are different events that can both arrive for one purchase, so the unique
    on ``provider_event_id`` does not stop them. What stops them is asking
    whether this session was already fulfilled.
    """
    obj = (event.get("data") or {}).get("object") or {}
    if str(event.get("type", "")).startswith("checkout.session."):
        value = obj.get("id")
        return str(value) if value else None
    return None


async def record_event(session: AsyncSession, event: dict[str, Any]) -> BillingEvent | None:
    """Record the notice BEFORE acting on it. ``None`` means already seen.

    The clash on ``provider_event_id`` is not an error path: it is the normal
    outcome of a provider retry, and answering 200 to it is what stops a
    resend from doubling an income.
    """
    event_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")
    row = BillingEvent(
        id=uuid.uuid4(),
        provider_event_id=event_id,
        event_type=event_type,
        checkout_session_id=checkout_session_id_from(event),
        partner_id=partner_id_from(event),
        status="received" if event_type in HANDLED_EVENTS else "ignored",
        payload=redact_payload(event),
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        log.info("metering.billing_event_duplicate", event_id=event_id, event_type=event_type)
        return None
    return row


async def already_fulfilled(session: AsyncSession, checkout_session_id: str) -> bool:
    """Whether this purchase was already credited, by session and not by event."""
    found = await session.scalar(
        sa.select(sa.func.count())
        .select_from(BillingEvent)
        .where(
            BillingEvent.checkout_session_id == checkout_session_id,
            BillingEvent.status == "processed",
        )
    )
    return bool(found)
