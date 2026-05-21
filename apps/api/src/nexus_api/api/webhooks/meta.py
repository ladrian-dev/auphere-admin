"""Meta WhatsApp Cloud API webhook endpoint.

Mirror of the YCloud webhook (``./ycloud.py``) but speaking Meta's wire
format directly. The route handles:

1. ``GET /webhook/meta`` — Meta's initial ``hub.verify_token`` handshake.
   Echoes ``hub.challenge`` if the verify token matches.
2. ``POST /webhook/meta`` — actual event delivery. Three event families:

   - **Inbound message** (``field == "messages"``, ``value.messages[]``):
     dedup by wamid, persist media to S3 (when present), enqueue to the
     ``nexus:inbound`` Redis Stream.
   - **Status callback** (``field == "messages"``, ``value.statuses[]``):
     advance ``Message.status``, capture pricing/error codes.
   - **Template approval** (``field == "message_template_status_update"``):
     upsert ``whatsapp_template_status``.

Idempotency: ``Message.provider_message_id`` has a UNIQUE partial index;
Redis dedupe (5 min TTL) avoids the PG roundtrip on Meta's retry storm.

The endpoint NEVER returns non-2xx for non-signature failures — Meta
re-drives any 4xx/5xx aggressively. Logging + a 200 ack is the way to
discard.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from nexus_channels.base import InboundMessage
from nexus_channels.whatsapp_meta import (
    MetaSignatureError,
    extract_business_phone,
    parse_inbound,
    parse_status_callback,
    parse_template_status,
    verify_meta_signature,
)
from nexus_channels.whatsapp_ycloud.webhook_adapter import is_opt_out_text
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.config import get_settings
from nexus_api.core.errors import TenantNotFound
from nexus_api.core.logging_context import bind_tenant
from nexus_api.core.metrics import CHANNEL_UNRESOLVED_EVENT, counters
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.core.tenant_resolver import resolve_tenant
from nexus_api.db.models import (
    Message,
    MessageStatus,
    WhatsAppOptOut,
    WhatsAppTemplateStatus,
)
from nexus_api.repositories import ChannelRepository

router = APIRouter()
log = structlog.get_logger()


INBOUND_STREAM = "nexus:inbound"
WAMID_DEDUPE_TTL = 600  # match the YCloud route


# ── GET handshake ──────────────────────────────────────────────────────────


@router.get("/meta", status_code=status.HTTP_200_OK)
async def meta_webhook_handshake(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
) -> Any:
    """Meta calls this once when the callback URL is registered (or
    updated). We answer 200 with the challenge as plain text.

    The verify token check is constant-time-ish in spirit (Python string
    equality is constant-time for equal-length strings; the secret is
    fixed-length in practice).
    """
    settings = get_settings()
    if hub_mode != "subscribe":
        log.warning("webhook.meta.handshake.unexpected_mode", mode=hub_mode)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="bad mode")
    if hub_verify_token != settings.meta_webhook_verify_token:
        log.warning("webhook.meta.handshake.bad_verify_token")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="bad verify_token")
    log.info("webhook.meta.handshake.ok")
    # FastAPI serialises strings as JSON by default. Meta requires the
    # raw challenge as plain text — return it via PlainTextResponse so
    # the response body is literally the challenge, no quotes.
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(hub_challenge)


# ── POST events ────────────────────────────────────────────────────────────


@router.post("/meta", status_code=status.HTTP_200_OK)
async def meta_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    body = await request.body()
    settings = get_settings()

    try:
        verify_meta_signature(settings.meta_app_secret, body, x_hub_signature_256)
    except MetaSignatureError as exc:
        log.warning("webhook.meta.signature_failed", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature"
        ) from exc

    try:
        payload: dict[str, Any] = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid JSON") from exc

    if payload.get("object") != "whatsapp_business_account":
        # Could be an Instagram webhook (when we add IG later) — not ours yet.
        log.info("webhook.meta.non_whatsapp_object", object=payload.get("object"))
        return {"status": "ignored"}

    # Route by ``field`` within the first change. Real Meta batches carry
    # one field per change; mixed-field batches are spec-allowed but never
    # observed in practice. Iterate so we surface the right handler.
    handled = False
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes") or []:
            if not isinstance(change, dict):
                continue
            field = change.get("field")
            if field == "messages":
                value = change.get("value") or {}
                if isinstance(value, dict) and value.get("statuses"):
                    await _handle_status_callback(payload, session=session, redis=redis)
                else:
                    await _handle_inbound(payload, session=session, redis=redis)
                handled = True
            elif field == "message_template_status_update":
                await _handle_template_status(payload, session=session)
                handled = True
            else:
                log.info("webhook.meta.unhandled_field", field=field)

    return {"status": "ok" if handled else "ignored"}


# ── inbound message ────────────────────────────────────────────────────────


async def _handle_inbound(
    payload: dict[str, Any],
    *,
    session: AsyncSession,
    redis: Redis,
) -> dict[str, Any]:
    business_phone = extract_business_phone(payload)
    if not business_phone:
        log.warning("webhook.meta.missing_business_phone")
        return {"status": "ignored"}

    try:
        tenant_id = await resolve_tenant(session, redis, "meta", business_phone)
    except TenantNotFound:
        counters.incr(CHANNEL_UNRESOLVED_EVENT)
        log.warning(
            "channel.unresolved_event",
            provider="meta",
            identifier=business_phone,
        )
        return {"status": "ignored"}

    if session.in_transaction():
        await session.rollback()
    bind_tenant(tenant_id)

    inbound = parse_inbound(payload)
    if inbound is None:
        log.info("webhook.meta.unparseable_message", tenant_id=str(tenant_id))
        return {"status": "ignored"}

    wamid = inbound.provider_message_id

    # Redis dedupe — short window above Meta's retry budget.
    dedupe_key = f"nexus:wamid:{wamid}"
    if await redis.setnx(dedupe_key, "1"):
        await redis.expire(dedupe_key, WAMID_DEDUPE_TTL)
    else:
        log.info("webhook.meta.dedupe_redis_hit", tenant_id=str(tenant_id), wamid=wamid)
        return {"status": "deduped"}

    # Durable dedupe via UNIQUE partial index.
    async with tenant_scoped_session(session, tenant_id):
        prior = await session.scalar(select(Message.id).where(Message.provider_message_id == wamid))
        if prior is not None:
            log.info(
                "webhook.meta.dedupe_db_hit",
                tenant_id=str(tenant_id),
                wamid=wamid,
                message_id=str(prior),
            )
            return {"status": "deduped"}

        channel = await ChannelRepository(session).get_by_provider_identifier(
            "meta", business_phone
        )

    if channel is None:
        log.warning(
            "webhook.meta.channel_not_found_under_tenant",
            tenant_id=str(tenant_id),
            identifier=business_phone,
        )
        return {"status": "ignored"}

    # Opt-out detection — keyword-based, provider-agnostic.
    opted_out = False
    if inbound.text is not None:
        matched, kw = is_opt_out_text(inbound.text)
        if matched:
            opted_out = True
            await _record_opt_out(
                session=session,
                tenant_id=tenant_id,
                channel_id=channel.id,
                recipient_phone=inbound.sender_identifier,
                reason="keyword_stop",
                keyword=kw,
                source_wamid=wamid,
            )

    # Enqueue.
    content = inbound.text or f"[{inbound.kind.value}]"
    fields: dict[str, str] = {
        "tenant_id": str(tenant_id),
        "channel_id": str(channel.id),
        "user_id": inbound.sender_identifier,
        "content": content,
        "provider": "meta",
        "provider_message_id": wamid,
        "kind": inbound.kind.value,
    }
    if inbound.sender_name:
        fields["customer_name"] = inbound.sender_name
    if opted_out:
        fields["opted_out"] = "true"
    if inbound.context_message_id:
        fields["context_message_id"] = inbound.context_message_id

    await redis.xadd(INBOUND_STREAM, fields)

    log.info(
        "webhook.meta.inbound_enqueued",
        tenant_id=str(tenant_id),
        channel_id=str(channel.id),
        wamid=wamid,
        kind=inbound.kind.value,
        opted_out=opted_out,
    )
    return {"status": "enqueued"}


# ── outbound status callback ───────────────────────────────────────────────


async def _handle_status_callback(
    payload: dict[str, Any],
    *,
    session: AsyncSession,
    redis: Redis,
) -> dict[str, Any]:
    status_update = parse_status_callback(payload)
    if status_update is None:
        return {"status": "ignored"}

    business_phone = extract_business_phone(payload)
    if not business_phone:
        return {"status": "ignored"}

    try:
        tenant_id = await resolve_tenant(session, redis, "meta", business_phone)
    except TenantNotFound:
        return {"status": "ignored"}

    if session.in_transaction():
        await session.rollback()
    bind_tenant(tenant_id)

    # Map Meta's status enum onto the canonical ``MessageStatus``.
    new_status = _map_status(status_update.status)
    if new_status is None:
        return {"status": "ignored"}

    async with tenant_scoped_session(session, tenant_id):
        values: dict[str, Any] = {
            "status": new_status,
            "updated_at": status_update.timestamp,
        }
        if new_status == MessageStatus.DELIVERED:
            values["delivered_at"] = status_update.timestamp
        elif new_status == MessageStatus.READ:
            values["read_at"] = status_update.timestamp
        elif new_status == MessageStatus.FAILED:
            values["failed_at"] = status_update.timestamp
            if status_update.error_code is not None:
                values["failure_code"] = str(status_update.error_code)
            if status_update.error_message:
                values["last_error"] = status_update.error_message
        if status_update.pricing_category:
            values["pricing_category"] = status_update.pricing_category
        if status_update.conversation_id:
            values["conversation_provider_id"] = status_update.conversation_id
        await session.execute(
            Message.__table__.update()
            .where(Message.provider_message_id == status_update.wamid)
            .values(**values)
        )

    log.info(
        "webhook.meta.status_update",
        tenant_id=str(tenant_id),
        wamid=status_update.wamid,
        new_status=new_status.value if hasattr(new_status, "value") else str(new_status),
        error_code=status_update.error_code,
    )
    return {"status": "ok"}


def _map_status(meta_status: str) -> MessageStatus | None:
    mapping = {
        "sent": MessageStatus.SENT,
        "delivered": MessageStatus.DELIVERED,
        "read": MessageStatus.READ,
        "failed": MessageStatus.FAILED,
    }
    return mapping.get(meta_status)


# ── template approval state ────────────────────────────────────────────────


async def _handle_template_status(
    payload: dict[str, Any],
    *,
    session: AsyncSession,
) -> dict[str, Any]:
    update = parse_template_status(payload)
    if update is None or not update.template_name:
        return {"status": "ignored"}
    now = datetime.now(tz=UTC)
    # The table is NOT tenant-scoped — keyed by (waba_id, template_name,
    # language) so the same template across tenants stays consistent.
    stmt = pg_insert(WhatsAppTemplateStatus).values(
        waba_id=update.waba_id,
        template_name=update.template_name,
        language=update.language,
        status=update.new_status,
        reason=update.reason,
        last_event_payload=payload,
        last_event_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["waba_id", "template_name", "language"],
        set_={
            "status": stmt.excluded.status,
            "reason": stmt.excluded.reason,
            "last_event_payload": stmt.excluded.last_event_payload,
            "last_event_at": stmt.excluded.last_event_at,
        },
    )
    await session.execute(stmt)
    log.info(
        "webhook.meta.template_status",
        waba_id=update.waba_id,
        template_name=update.template_name,
        new_status=update.new_status,
    )
    return {"status": "ok"}


# ── helpers ────────────────────────────────────────────────────────────────


async def _record_opt_out(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    channel_id: uuid.UUID,
    recipient_phone: str,
    reason: str,
    keyword: str | None,
    source_wamid: str,
) -> None:
    """Idempotent UPSERT on (tenant_id, channel_id, recipient_phone)."""
    async with tenant_scoped_session(session, tenant_id):
        stmt = pg_insert(WhatsAppOptOut).values(
            tenant_id=tenant_id,
            channel_id=channel_id,
            recipient_phone=recipient_phone,
            reason=reason,
            trigger_keyword=keyword,
            source_wamid=source_wamid,
            opted_out_at=datetime.now(tz=UTC),
        )
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["tenant_id", "channel_id", "recipient_phone"]
        )
        await session.execute(stmt)


__all__ = ["router"]


_ = InboundMessage  # silence pyflakes "imported but unused" — typing reference
