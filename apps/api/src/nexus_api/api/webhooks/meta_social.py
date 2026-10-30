"""Instagram (``object=instagram``) and Page (``object=page``) events — spec 049.

Same callback as WhatsApp (``/webhook/meta``), same signature check, same
guarantees; :func:`meta.meta_webhook` hands these two objects here after
verifying ``X-Hub-Signature-256``.

**Who owns an event.** ``entry[].id`` is the professional account or the
Page. The tenant comes from ``resolve_channel_tenant(provider, entry.id)``
(active channels only) and never from anything else in the payload.

**Two environments, one callback.** Meta accepts one URL per object per app
for these objects — there is no per-asset ``override_callback_uri`` like
WhatsApp's. Staging and production share the app, so an environment that
receives a batch with an account it does not own forwards the raw body and
its original signature to the other one (``settings.meta_webhook_peer``),
marked ``X-Auphere-Forwarded`` so it never bounces back. The peer verifies
the signature exactly as if Meta had called it, and ignores what is not its
own either. Forwarding is best-effort and bounded (5 s): Meta's 20 s budget
is for the whole batch.

**Once.** Meta retries for up to 36 h. Redis keeps the event id for 48 h;
the UNIQUE partial index on ``messages.provider_message_id`` is the durable
layer behind it.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import structlog
from nexus_channels.meta_social import SocialEvent, entry_account_ids, iter_events, provider_for
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.config import get_settings
from nexus_api.core.errors import TenantNotFound
from nexus_api.core.logging_context import bind_tenant
from nexus_api.core.metrics import CHANNEL_UNRESOLVED_EVENT, counters
from nexus_api.core.otel import inject_trace_fields
from nexus_api.core.streams import stream_for_tier, xadd_capped
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.core.tenant_resolver import resolve_tenant, resolve_tenant_tier
from nexus_api.db.models import ChannelStatus, Message
from nexus_api.repositories import ChannelRepository

log = structlog.get_logger()

FORWARDED_HEADER = "X-Auphere-Forwarded"
EVENT_DEDUPE_TTL = 48 * 3600  # above Meta's 36 h retry window
FORWARD_TIMEOUT_S = 5.0

_forward_client: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _forward_client
    if _forward_client is None:
        _forward_client = httpx.AsyncClient(timeout=FORWARD_TIMEOUT_S)
    return _forward_client


async def handle_meta_social(
    payload: dict[str, Any],
    *,
    body: bytes,
    signature: str | None,
    forwarded: bool,
    session: AsyncSession,
    redis: Redis,
) -> dict[str, Any]:
    provider = provider_for(payload)
    if provider is None:
        return {"status": "ignored"}

    owners: dict[str, uuid.UUID] = {}
    foreign: list[str] = []
    for account_id in entry_account_ids(payload):
        try:
            owners[account_id] = await resolve_tenant(session, redis, provider, account_id)
        except TenantNotFound:
            foreign.append(account_id)

    forwarded_to_peer = False
    if foreign:
        if forwarded:
            # Neither environment owns it: an account nobody connected, or one
            # disconnected a moment ago. Dropped without touching any data.
            counters.incr(CHANNEL_UNRESOLVED_EVENT)
            log.info("channel.unresolved_event", provider=provider, accounts=len(foreign))
        else:
            forwarded_to_peer = await _forward(body, signature, provider=provider)

    enqueued = 0
    for event in iter_events(payload):
        tenant_id = owners.get(event.account_id)
        if tenant_id is None:
            continue
        if event.inbound is None:
            log.info(
                "webhook.meta_social.event",
                provider=provider,
                tenant_id=str(tenant_id),
                kind=event.kind,
                detail=event.detail,
            )
            continue
        if await _enqueue(event, tenant_id=tenant_id, session=session, redis=redis):
            enqueued += 1

    return {
        "status": "ok" if enqueued else "ignored",
        "enqueued": enqueued,
        "forwarded": forwarded_to_peer,
    }


async def _forward(body: bytes, signature: str | None, *, provider: str) -> bool:
    peer = get_settings().meta_webhook_peer
    if not peer or not signature:
        counters.incr(CHANNEL_UNRESOLVED_EVENT)
        log.info("channel.unresolved_event", provider=provider, reason="no_peer")
        return False
    try:
        resp = await _client().post(
            peer,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": signature,
                FORWARDED_HEADER: "1",
            },
        )
    except httpx.HTTPError as exc:
        log.warning(
            "webhook.meta_social.forward_failed", provider=provider, error=type(exc).__name__
        )
        return False
    log.info("webhook.meta_social.forwarded", provider=provider, status=resp.status_code)
    return resp.status_code < 400


async def _enqueue(
    event: SocialEvent,
    *,
    tenant_id: uuid.UUID,
    session: AsyncSession,
    redis: Redis,
) -> bool:
    inbound = event.inbound
    assert inbound is not None
    if session.in_transaction():
        await session.rollback()
    bind_tenant(tenant_id)

    event_id = inbound.provider_message_id
    dedupe_key = f"nexus:msocial:{event.provider}:{event_id}"
    if await redis.setnx(dedupe_key, "1"):
        await redis.expire(dedupe_key, EVENT_DEDUPE_TTL)
    else:
        log.info("webhook.meta_social.dedupe_redis_hit", tenant_id=str(tenant_id))
        return False
    try:
        return await _enqueue_once(
            event, event_id=event_id, tenant_id=tenant_id, session=session, redis=redis
        )
    except BaseException:
        # The 5xx makes Meta retry; a mark left here would drop that retry for
        # EVENT_DEDUPE_TTL and lose the message (QA 2026-10-30, INC-17).
        await redis.delete(dedupe_key)
        raise


async def _enqueue_once(
    event: SocialEvent,
    *,
    event_id: str,
    tenant_id: uuid.UUID,
    session: AsyncSession,
    redis: Redis,
) -> bool:
    inbound = event.inbound
    assert inbound is not None
    async with tenant_scoped_session(session, tenant_id):
        prior = await session.scalar(
            select(Message.id).where(Message.provider_message_id == event_id)
        )
        channel = await ChannelRepository(session).get_by_provider_identifier(
            event.provider, event.account_id
        )
        channel_id = channel.id if channel is not None else None
        channel_status = channel.status if channel is not None else None
        channel_config = dict(channel.config or {}) if channel is not None else {}

    if prior is not None:
        log.info("webhook.meta_social.dedupe_db_hit", tenant_id=str(tenant_id))
        return False
    # Paused or degraded still enqueues, as on WhatsApp: the worker's turn
    # gate keeps the message for a person («Canal en pausa») instead of the
    # webhook dropping it (QA 2026-10-30, INC-37).
    if channel_id is None or channel_status is ChannelStatus.DISCONNECTED:
        log.warning("webhook.meta_social.channel_not_active", tenant_id=str(tenant_id))
        return False
    if event.kind == "comment" and channel_config.get("comments_enabled") is False:
        log.info("webhook.meta_social.comment_skipped_disabled", tenant_id=str(tenant_id))
        return False

    fields: dict[str, str] = {
        "tenant_id": str(tenant_id),
        "channel_id": str(channel_id),
        "user_id": inbound.sender_identifier,
        "content": _render_content(inbound),
        "provider": event.provider,
        "provider_message_id": event_id,
        "kind": inbound.kind.value,
    }
    if inbound.sender_name:
        fields["customer_name"] = inbound.sender_name
    if inbound.media is not None and inbound.kind.value in {
        "audio",
        "image",
        "document",
        "video",
        "sticker",
    }:
        fields["media_kind"] = inbound.kind.value
        fields["media_provider_id"] = inbound.media.provider_media_id
    if inbound.context_message_id:
        # A comment turn carries ``comment:<id>``: the worker stamps it on the
        # agent's reply, which then leaves as a private reply to that comment.
        fields["context_message_id"] = inbound.context_message_id
    if inbound.reaction is not None:
        fields["reaction_emoji"] = inbound.reaction.emoji
        fields["reaction_target_wamid"] = inbound.reaction.target_message_id

    inject_trace_fields(fields)
    tier = await resolve_tenant_tier(session, redis, tenant_id)
    await xadd_capped(redis, stream_for_tier(tier), fields)
    log.info(
        "webhook.meta_social.enqueued",
        tenant_id=str(tenant_id),
        channel_id=str(channel_id),
        provider=event.provider,
        kind=inbound.kind.value,
        comment=event.kind == "comment",
    )
    return True


def _render_content(inbound: Any) -> str:
    """Same contract as the WhatsApp route's renderer: one ``content``
    string, media as a prefix the multimodal step replaces."""
    if inbound.text is not None and inbound.kind.value == "text":
        return str(inbound.text)
    if inbound.interactive is not None:
        title = inbound.interactive.title or ""
        return f"[interactive:{inbound.interactive.kind}:{inbound.interactive.payload_id}]{title}"
    if inbound.reaction is not None:
        emoji = inbound.reaction.emoji or "(removed)"
        return f"[reaction:{emoji}:on={inbound.reaction.target_message_id}]"
    if inbound.kind.value in {"audio", "image", "document", "video", "sticker"}:
        caption = inbound.media.caption if inbound.media is not None else None
        return f"[media:{inbound.kind.value}]{caption or ''}"
    return inbound.text or f"[unsupported:{inbound.raw_event_type or 'unknown'}]"
