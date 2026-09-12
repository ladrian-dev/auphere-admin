"""Spec 005 · ``POST /webhook/billing`` — the provider's notices land here.

An external caller that **credits balance**. Not a new class of caller — Meta
and TikTok have been delivering since 2026 — but the consequence is different,
so three things contain it and all three are requirements of the spec:
signature verified before the body is read, idempotency by the notice's id,
and **reconciliation in one direction only**: a confirmed payment adds, and
nothing from outside ever subtracts.

The sequence is ADR-022 §13-§15 and has nothing between its steps. Answer
fast and do the work elsewhere: Stripe waits up to 10 seconds for the response
to ``checkout.session.completed`` before redirecting the customer to the thank
you page, and a thank you page that takes ten seconds reads as a failed
payment.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.billing.events import HANDLED_EVENTS, record_event
from nexus_api.billing.provider import verify_signature
from nexus_api.config import get_settings
from nexus_api.core.streams import xadd_capped

log = structlog.get_logger(__name__)

router = APIRouter()

#: Where the real work is queued. The webhook only records and enqueues.
BILLING_EVENT_STREAM = "nexus:billing:events"


@router.post("/billing", status_code=status.HTTP_200_OK)
async def billing_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    # 1. The body RAW. The signature covers the exact bytes; a framework that
    #    parses and re-serialises invalidates it over a single space, and the
    #    failure then looks like an attack instead of a bug.
    body = await request.body()
    settings = get_settings()

    if not settings.billing_webhook_secret.strip():
        # Fail-closed. Booting without billing is an honest state; accepting
        # unverifiable notices is not.
        log.warning("metering.billing_webhook_closed")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="billing closed")

    # 2. Verify BEFORE interpreting. What does not verify is not read (§III).
    try:
        event = verify_signature(
            payload=body,
            signature=stripe_signature or "",
            secret=settings.billing_webhook_secret,
        )
    except Exception as exc:
        log.warning("metering.billing_signature_failed", reason=type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid signature"
        ) from exc

    # 3. Record before acting. The unique constraint IS the idempotency: a
    #    resend loses the INSERT and credits nothing.
    row = await record_event(session, event)
    if row is None:
        return {"status": "duplicate"}
    await session.commit()

    event_type = str(event.get("type") or "")
    if event_type not in HANDLED_EVENTS:
        log.info("metering.billing_event_ignored", event_type=event_type)
        return {"status": "ignored"}

    # 4. Enqueue and answer. The worker re-fetches the object from the API —
    #    the body says WHAT happened, the provider says what it is worth.
    await xadd_capped(
        redis,
        BILLING_EVENT_STREAM,
        {
            "event_row_id": str(row.id),
            "provider_event_id": row.provider_event_id,
            "event_type": event_type,
            "partner_id": str(row.partner_id or ""),
            "checkout_session_id": row.checkout_session_id or "",
        },
    )
    log.info(
        "metering.billing_event_received",
        event_type=event_type,
        partner_id=str(row.partner_id or ""),
    )
    return {"status": "queued"}
