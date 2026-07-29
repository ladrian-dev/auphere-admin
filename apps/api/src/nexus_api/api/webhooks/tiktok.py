"""TikTok Business Messaging webhook endpoint.

Speaks TikTok's wire format directly, and mirrors the guarantees the Meta
webhook already establishes:

- **Signature first.** ``TikTok-Signature`` is verified over the raw body
  before anything is parsed. A failure is the only case that returns non-2xx.
- **Fail-closed tenant resolution.** An event we cannot attribute to a tenant
  is acked and dropped, never processed under a guessed scope.
- **Two-layer dedupe.** Redis (short TTL, absorbs the redrive storm) plus the
  UNIQUE partial index on ``messages.provider_message_id`` (durable).
- **Media before enqueue.** Images are downloaded and persisted to S3 before
  the turn is queued, so the multimodal pipeline has a reference when the
  consumer picks it up.
- **200 on anything that is not a signature failure.** TikTok redrives
  aggressively; a 500 on our side turns one bad payload into a retry storm.

The one structural difference from the Meta route is ``conversation_id``.
WhatsApp lets us reply to a phone number, so an outbound send needs nothing
from the inbound event. TikTok has no send-to-user call at all — the only way
to answer is to target the conversation the *user* opened. The parser puts
that id on ``InboundMessage.context_message_id`` and this route forwards it
into the stream, which is how the outbound dispatcher gets it back hours
later. Losing it means the agent can compose a perfect answer with nowhere
to send it.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from nexus_channels.tiktok_bm import (
    TikTokAPIError,
    TikTokChannelAdapter,
    TikTokClient,
    TikTokInvalidSignatureError,
    extract_business_id,
    is_known_event,
    parse_conversation_event,
    parse_inbound,
    verify_tiktok_signature,
)
from nexus_channels.tiktok_bm.credentials import TikTokCredentialsRepository
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.config import get_settings
from nexus_api.core.errors import TenantNotFound
from nexus_api.core.logging_context import bind_tenant
from nexus_api.core.metrics import CHANNEL_UNRESOLVED_EVENT, counters
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.core.tenant_resolver import resolve_tenant
from nexus_api.db.models import Message
from nexus_api.repositories import ChannelRepository
from nexus_api.services.media_storage import MediaStorageError, get_media_storage

router = APIRouter()
log = structlog.get_logger()

PROVIDER = "tiktok"
INBOUND_STREAM = "nexus:inbound"
# Above TikTok's retry budget, same rationale as the Meta route's wamid TTL.
MESSAGE_DEDUPE_TTL = 600


@router.post("/tiktok", status_code=status.HTTP_200_OK)
async def tiktok_webhook(
    request: Request,
    tiktok_signature: str | None = Header(default=None, alias="TikTok-Signature"),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    body = await request.body()
    settings = get_settings()

    # Read the raw bytes before touching request.json() — Starlette would
    # otherwise consume the stream, and a re-serialised body never verifies.
    try:
        verify_tiktok_signature(settings.tiktok_app_secret, body, tiktok_signature)
    except TikTokInvalidSignatureError as exc:
        # Deliberately no body echo: a signature failure is either a rotated
        # secret or an attacker, and neither should get their payload back in
        # our logs.
        log.warning("webhook.tiktok.signature_failed", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature"
        ) from exc

    try:
        payload: dict[str, Any] = json.loads(body)
    except json.JSONDecodeError:
        # Signed but unparseable. Ack so TikTok stops redriving; there is
        # nothing here we could ever process.
        log.warning("webhook.tiktok.invalid_json")
        return {"status": "ignored"}

    if not is_known_event(payload):
        # ``event_name``, not ``event``: structlog reserves ``event`` for the
        # message itself and passing it raises at call time.
        log.info("webhook.tiktok.unknown_event", event_name=payload.get("event"))
        return {"status": "ignored"}

    inbound = parse_inbound(payload)
    if inbound is None:
        return await _handle_non_message_event(payload)

    return await _handle_inbound(payload, inbound=inbound, session=session, redis=redis)


# ── non-message events ─────────────────────────────────────────────────────


async def _handle_non_message_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Read receipts and conversation lifecycle.

    Logged and acked. These carry no state the platform tracks today, but
    recognising them keeps them out of the "unknown event" bucket so a real
    unknown stays visible.
    """
    event = parse_conversation_event(payload)
    if event is not None:
        log.info(
            "webhook.tiktok.conversation_event",
            event_name=event.event,
            business_id=event.business_id,
            conversation_id=event.conversation_id,
        )
    return {"status": "ignored"}


# ── inbound message ────────────────────────────────────────────────────────


async def _handle_inbound(
    payload: dict[str, Any],
    *,
    inbound: Any,
    session: AsyncSession,
    redis: Redis,
) -> dict[str, Any]:
    business_id = extract_business_id(payload)
    if not business_id:
        log.warning("webhook.tiktok.missing_business_id")
        return {"status": "ignored"}

    try:
        tenant_id = await resolve_tenant(session, redis, PROVIDER, business_id)
    except TenantNotFound:
        # Fail-closed: no tenant, no processing. Ack so TikTok stops
        # redriving an event we will never be able to route.
        counters.incr(CHANNEL_UNRESOLVED_EVENT)
        log.warning("channel.unresolved_event", provider=PROVIDER, identifier=business_id)
        return {"status": "ignored"}

    if session.in_transaction():
        await session.rollback()
    bind_tenant(tenant_id)

    message_id = inbound.provider_message_id
    conversation_id = inbound.context_message_id

    # Layer 1: Redis. Absorbs the redrive storm without a PG roundtrip.
    dedupe_key = f"nexus:tiktok_msg:{message_id}"
    if await redis.setnx(dedupe_key, "1"):
        await redis.expire(dedupe_key, MESSAGE_DEDUPE_TTL)
    else:
        log.info(
            "webhook.tiktok.dedupe_redis_hit",
            tenant_id=str(tenant_id),
            message_id=message_id,
        )
        return {"status": "deduped"}

    # Layer 2: the durable UNIQUE partial index. Survives a Redis flush.
    async with tenant_scoped_session(session, tenant_id):
        prior = await session.scalar(
            select(Message.id).where(Message.provider_message_id == message_id)
        )
        if prior is not None:
            log.info(
                "webhook.tiktok.dedupe_db_hit",
                tenant_id=str(tenant_id),
                message_id=message_id,
            )
            return {"status": "deduped"}

        channel = await ChannelRepository(session).get_by_provider_identifier(PROVIDER, business_id)

    if channel is None:
        # The resolver found a tenant but the row is gone or belongs to a
        # different scope. Refuse rather than enqueue an unroutable turn.
        log.warning(
            "webhook.tiktok.channel_not_found_under_tenant",
            tenant_id=str(tenant_id),
            identifier=business_id,
        )
        return {"status": "ignored"}

    if not conversation_id:
        # Without it the agent could answer and have nowhere to send the
        # reply. Better to surface the gap here than to queue a doomed turn.
        log.warning(
            "webhook.tiktok.missing_conversation_id",
            tenant_id=str(tenant_id),
            message_id=message_id,
        )
        return {"status": "ignored"}

    s3_key: str | None = None
    media_mime: str | None = None
    media_size: int | None = None
    media_kind_value: str | None = None

    if inbound.media is not None and inbound.kind.value in {"image", "video"}:
        media_kind_value = inbound.kind.value
        try:
            s3_key, media_mime, media_size = await _download_inbound_media(
                tenant_id=tenant_id,
                message_id=message_id,
                media_id=inbound.media.provider_media_id,
                hint_mime=inbound.media.mime_type,
            )
        except (TikTokAPIError, MediaStorageError) as exc:
            # Still enqueue: the agent asking the customer to resend is a far
            # better outcome than the turn vanishing.
            log.warning(
                "webhook.tiktok.media_download_failed",
                tenant_id=str(tenant_id),
                message_id=message_id,
                media_id=inbound.media.provider_media_id,
                error=str(exc),
            )

    fields: dict[str, str] = {
        "tenant_id": str(tenant_id),
        "channel_id": str(channel.id),
        "user_id": inbound.sender_identifier,
        "content": _render_content(inbound),
        "provider": PROVIDER,
        "provider_message_id": message_id,
        "kind": inbound.kind.value,
        # The handle every outbound send on this channel needs.
        "context_message_id": conversation_id,
    }
    if inbound.sender_name:
        fields["customer_name"] = inbound.sender_name
    if media_kind_value:
        fields["media_kind"] = media_kind_value
    if s3_key:
        fields["media_s3_key"] = s3_key
    if media_mime:
        fields["media_mime"] = media_mime
    if media_size is not None:
        fields["media_size_bytes"] = str(media_size)

    await redis.xadd(INBOUND_STREAM, fields)  # type: ignore[arg-type]  # redis stub: invariant dict

    log.info(
        "webhook.tiktok.enqueued",
        tenant_id=str(tenant_id),
        channel_id=str(channel.id),
        message_id=message_id,
        kind=inbound.kind.value,
    )
    return {"status": "ok"}


# ── helpers ────────────────────────────────────────────────────────────────


def _render_content(inbound: Any) -> str:
    """Render the event into the single ``content`` string the pipeline reads.

    Same provider-agnostic contract the Meta route uses, so the worker
    consumer sees uniform entries regardless of transport. The media prefix
    is what reaches the classifier when a download failed, letting it route
    to a graceful "no pude verlo" reply instead of answering nothing.
    """
    if inbound.text is not None and inbound.kind.value == "text":
        return str(inbound.text)
    if inbound.media is not None:
        caption = inbound.media.caption or inbound.text or ""
        return f"[{inbound.kind.value}]{caption}".strip()
    if inbound.text:
        return str(inbound.text)
    return f"[{inbound.kind.value}]"


async def _download_inbound_media(
    *,
    tenant_id: uuid.UUID,
    message_id: str,
    media_id: str,
    hint_mime: str | None,
) -> tuple[str, str | None, int]:
    """Resolve ``image_id`` → bytes → S3. Returns ``(key, mime, size)``.

    Honours ``Settings.media_max_size_mb`` so an oversized object surfaces as
    a handled failure rather than being persisted.
    """
    settings = get_settings()
    storage = get_media_storage()
    adapter = _build_tiktok_adapter()
    try:
        content, mime, _sha = await adapter.fetch_media_bytes(
            media_id=media_id, tenant_id=tenant_id
        )
    finally:
        await adapter._client.close()

    if not mime and hint_mime:
        mime = hint_mime
    size = len(content)
    if size > settings.media_max_size_mb * 1024 * 1024:
        raise MediaStorageError(
            f"inbound media too large: {size} bytes > {settings.media_max_size_mb}MB limit"
        )

    tenant_slug = await _tenant_slug_for(tenant_id)
    stored = await storage.put_inbound(
        tenant_slug=tenant_slug,
        wamid=message_id,
        content=content,
        content_type=mime,
        sha256=None,
    )
    return stored.key, stored.content_type, stored.size_bytes


async def _tenant_slug_for(tenant_id: uuid.UUID) -> str:
    """Reuses the Meta route's resolver — ``tenants`` is a global table and
    the lookup is identical, so duplicating it would only create drift."""
    from nexus_api.api.webhooks.meta import _tenant_slug_for as resolve_slug

    return await resolve_slug(tenant_id)


def _build_tiktok_adapter() -> TikTokChannelAdapter:
    """Construct an adapter bound to a per-tenant credentials lookup.

    Built per call rather than held as a module global so the HTTP client is
    closed deterministically after the media fetch.
    """
    settings = get_settings()
    client = TikTokClient(
        settings.tiktok_app_id,
        settings.tiktok_app_secret,
        base_url=settings.tiktok_api_base_url,
        api_version=settings.tiktok_api_version,
    )

    async def _loader(*, tenant_id: uuid.UUID) -> tuple[str, str]:
        from nexus_api.db.base import get_sessionmaker

        sm = get_sessionmaker()
        async with sm() as cred_session, tenant_scoped_session(cred_session, tenant_id):
            creds = await TikTokCredentialsRepository(cred_session).get_or_raise()
            return creds.business_id, creds.access_token

    return TikTokChannelAdapter(client, credentials_loader=_loader)
