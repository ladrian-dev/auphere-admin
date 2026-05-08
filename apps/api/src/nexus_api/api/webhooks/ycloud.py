"""YCloud webhook.

Block B accepted the request and stopped at logging. Block C now extracts the
payload, resolves the channel row, and enqueues an inbound event to the
``nexus:inbound`` Redis Stream consumed by ``apps/worker``. The actual
*outbound* WhatsApp send still belongs to block F.
"""

from __future__ import annotations

import json
from typing import Any

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
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.core.tenant_resolver import resolve_tenant
from nexus_api.repositories import ChannelRepository

router = APIRouter()
log = structlog.get_logger()


# Stream name kept in this module so the worker is the source of truth for the
# producer side too (publish helper imports the same constant).
INBOUND_STREAM = "nexus:inbound"


def _extract_message(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """Pull (from, text) from a YCloud-shaped payload.

    YCloud's whatsapp.inbound_message envelope is roughly::

        {"type": "whatsapp.inbound_message",
         "phoneNumberId": "...",
         "message": {"from": "+56...", "text": {"body": "..."}}}

    We're tolerant — if the body is missing we just say so and let the worker
    side stay clean. Block F can swap this for the official YCloud schema once
    the templates are decided.
    """
    msg = payload.get("message") or {}
    from_ = msg.get("from") or payload.get("from")
    text = None
    if isinstance(msg.get("text"), dict):
        text = msg["text"].get("body")
    elif isinstance(msg.get("text"), str):
        text = msg["text"]
    elif isinstance(payload.get("text"), str):
        text = payload["text"]
    return from_, text


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
        return {"status": "ignored"}

    try:
        tenant_id = await resolve_tenant(session, redis, "ycloud", identifier)
    except TenantNotFound:
        counters.incr(CHANNEL_UNRESOLVED_EVENT)
        log.warning("channel.unresolved_event", provider="ycloud", identifier=identifier)
        return {"status": "ignored"}

    bind_tenant(tenant_id)

    user_id, content = _extract_message(payload)
    if not user_id or not content:
        log.info(
            "webhook.ycloud.non_message_event",
            type=payload.get("type"),
            has_user=bool(user_id),
            has_content=bool(content),
        )
        return {"status": "accepted"}

    # Resolve the channel row inside a tenant-scoped transaction so RLS
    # constrains the lookup to the resolved tenant.
    async with tenant_scoped_session(session, tenant_id):
        channel = await ChannelRepository(session).get_by_provider_identifier("ycloud", identifier)

    if channel is None:
        log.warning(
            "webhook.ycloud.channel_not_found_under_tenant",
            tenant_id=str(tenant_id),
            identifier=identifier,
        )
        return {"status": "ignored"}

    fields: dict[str, str] = {
        "tenant_id": str(tenant_id),
        "channel_id": str(channel.id),
        "user_id": user_id,
        "content": content,
        "provider": "ycloud",
    }
    await redis.xadd(INBOUND_STREAM, fields)  # type: ignore[arg-type]
    log.info(
        "webhook.ycloud.enqueued",
        tenant_id=str(tenant_id),
        channel_id=str(channel.id),
        user_id=user_id,
    )
    return {"status": "queued"}
