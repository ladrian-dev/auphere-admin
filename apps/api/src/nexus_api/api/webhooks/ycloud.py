"""YCloud webhook endpoint.

Block B accepted the request and stopped at logging. Block C added Redis
Stream enqueue. Block F now:

1. Validates the real YCloud signature scheme (``YCloud-Signature: t=...,s=...``)
   over ``{ts}.{raw_body}`` — :func:`verify_ycloud_signature`.
2. Parses the real YCloud envelope
   (``whatsapp.inbound_message.received`` + ``whatsappInboundMessage``) via
   :mod:`nexus_channels.whatsapp_ycloud.webhook_adapter`.
3. Resolves the tenant from the *receiver* phone (E.164) — that is, the
   business number stored as ``channels.provider_identifier``.
4. Enqueues an inbound event onto the ``nexus:inbound`` Redis Stream that
   the worker consumer drains.

The *outbound* side is the responsibility of the worker
:mod:`nexus_worker.streams.outbound` dispatcher — this endpoint never sends.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from nexus_channels.whatsapp_ycloud.signature import (
    YCloudSignatureError,
    verify_ycloud_signature,
)
from nexus_channels.whatsapp_ycloud.webhook_adapter import (
    INBOUND_MESSAGE_EVENT,
    extract_business_phone,
    parse_inbound,
)
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.config import get_settings
from nexus_api.core.errors import TenantNotFound
from nexus_api.core.logging_context import bind_tenant
from nexus_api.core.metrics import CHANNEL_UNRESOLVED_EVENT, counters
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.core.tenant_resolver import resolve_tenant
from nexus_api.repositories import ChannelRepository

router = APIRouter()
log = structlog.get_logger()


INBOUND_STREAM = "nexus:inbound"


@router.post("/ycloud", status_code=status.HTTP_200_OK)
async def ycloud_webhook(
    request: Request,
    ycloud_signature: str | None = Header(default=None, alias="YCloud-Signature"),
    x_ycloud_signature: str | None = Header(default=None, alias="X-YCloud-Signature"),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> dict[str, str]:
    body = await request.body()
    settings = get_settings()

    sig_header = ycloud_signature or x_ycloud_signature
    try:
        verify_ycloud_signature(
            settings.ycloud_webhook_secret,
            body,
            sig_header or "",
            tolerance_seconds=settings.ycloud_signature_tolerance_seconds,
        )
    except YCloudSignatureError as exc:
        log.warning("webhook.ycloud.signature_failed", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature"
        ) from exc

    try:
        payload: dict[str, Any] = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid JSON") from exc

    event_type = payload.get("type")
    if event_type != INBOUND_MESSAGE_EVENT:
        # Status callbacks (delivered / read / failed), template approvals,
        # account events. Block H/I will route some of these to dedicated
        # handlers; for now we ack and move on.
        log.info("webhook.ycloud.non_inbound_event", type=event_type)
        return {"status": "ignored"}

    business_phone = extract_business_phone(payload)
    if not business_phone:
        log.warning("webhook.ycloud.missing_business_phone", keys=list(payload))
        return {"status": "ignored"}

    try:
        tenant_id = await resolve_tenant(session, redis, "ycloud", business_phone)
    except TenantNotFound:
        counters.incr(CHANNEL_UNRESOLVED_EVENT)
        log.warning(
            "channel.unresolved_event",
            provider="ycloud",
            identifier=business_phone,
        )
        return {"status": "ignored"}

    # ``resolve_tenant`` autobegins a transaction the moment it issues the
    # ``SELECT resolve_channel_tenant(...)`` lookup. We close it before
    # entering ``tenant_scoped_session`` so the latter can call
    # ``session.begin()`` without tripping ``InvalidRequestError`` (the
    # block-B / -C webhook never reached this branch end-to-end so the
    # latent issue stayed dormant until block F wired the full flow).
    if session.in_transaction():
        await session.rollback()

    bind_tenant(tenant_id)

    inbound = parse_inbound(payload)
    if inbound is None:
        log.info(
            "webhook.ycloud.unparseable_message",
            tenant_id=str(tenant_id),
            type=event_type,
        )
        return {"status": "ignored"}

    # Phase 1 the worker pipeline only handles text + interactive replies.
    # Everything else acks + logs so we don't lose the event from the
    # provider's perspective; Phase 2 wires a "I can't handle this yet"
    # response.
    if inbound.text is None and inbound.interactive is None:
        log.info(
            "webhook.ycloud.unsupported_kind",
            tenant_id=str(tenant_id),
            kind=inbound.kind,
            raw_event_type=inbound.raw_event_type,
        )
        return {"status": "accepted_no_dispatch"}

    async with tenant_scoped_session(session, tenant_id):
        channel = await ChannelRepository(session).get_by_provider_identifier(
            "ycloud", business_phone
        )
    if channel is None:
        log.warning(
            "webhook.ycloud.channel_not_found_under_tenant",
            tenant_id=str(tenant_id),
            identifier=business_phone,
        )
        return {"status": "ignored"}

    content: str
    if inbound.kind.value == "text" and inbound.text is not None:
        content = inbound.text
    elif inbound.interactive is not None:
        # Encode the interactive reply as a structured prefix the pipeline
        # can recognise. The agent sees "[interactive:button:btn_yes]Sí"
        # which is enough for the classifier to route through.
        title = inbound.interactive.title or ""
        content = (
            f"[interactive:{inbound.interactive.kind}:{inbound.interactive.payload_id}]{title}"
        )
    else:
        # parse_inbound already filtered these out above; defensive guard.
        return {"status": "ignored"}

    fields: dict[str, str] = {
        "tenant_id": str(tenant_id),
        "channel_id": str(channel.id),
        "user_id": inbound.sender_identifier,
        "content": content,
        "provider": "ycloud",
        "provider_message_id": inbound.provider_message_id,
    }
    if inbound.sender_name:
        fields["customer_name"] = inbound.sender_name
    await redis.xadd(INBOUND_STREAM, fields)  # type: ignore[arg-type]
    log.info(
        "webhook.ycloud.enqueued",
        tenant_id=str(tenant_id),
        channel_id=str(channel.id),
        user_id=inbound.sender_identifier,
        kind=inbound.kind.value,
    )
    return {"status": "queued"}
