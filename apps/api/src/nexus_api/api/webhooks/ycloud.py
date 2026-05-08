"""YCloud webhook stub.

Block B accepts the webhook, verifies HMAC, resolves the tenant, logs the event,
and returns 200. The actual pipeline (normalize → enqueue → agent runtime) is
block F. This stub establishes the contract so admin/operator integration tests
can drive the endpoint immediately.
"""

from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.config import get_settings
from nexus_api.core.errors import HMACVerificationFailed, TenantNotFound
from nexus_api.core.logging_context import bind_tenant
from nexus_api.core.metrics import CHANNEL_UNRESOLVED_EVENT, counters
from nexus_api.core.security import verify_hmac
from nexus_api.core.tenant_resolver import resolve_tenant

router = APIRouter()
log = structlog.get_logger()

# YCloud sends payloads like:
# { "type": "whatsapp.inbound_message", "phoneNumberId": "1234", "message": {...} }
# We only inspect the identifier; the rest is forwarded to the pipeline in block F.


@router.post("/ycloud", status_code=status.HTTP_200_OK)
async def ycloud_webhook(
    request: Request,
    x_ycloud_signature: str | None = Header(default=None, alias="X-YCloud-Signature"),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> dict[str, str]:
    body = await request.body()

    settings = get_settings()
    try:
        verify_hmac(settings.webhook_hmac_secret, body, x_ycloud_signature or "")
    except HMACVerificationFailed as exc:
        log.warning("webhook.ycloud.hmac_failed", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature"
        ) from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid JSON") from exc

    identifier = payload.get("phoneNumberId") or payload.get("phone_number_id")
    if not identifier:
        log.warning("webhook.ycloud.missing_identifier", keys=list(payload))
        # Fail-closed: ack with 200 so YCloud doesn't retry; we just don't process.
        return {"status": "ignored"}

    try:
        tenant_id = await resolve_tenant(session, redis, "ycloud", identifier)
    except TenantNotFound:
        counters.incr(CHANNEL_UNRESOLVED_EVENT)
        log.warning("channel.unresolved_event", provider="ycloud", identifier=identifier)
        return {"status": "ignored"}

    bind_tenant(tenant_id)
    log.info(
        "webhook.ycloud.accepted",
        identifier=identifier,
        type=payload.get("type"),
    )
    # Block F: enqueue payload to Redis Streams here.
    return {"status": "accepted"}
