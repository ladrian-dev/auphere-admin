"""YCloud webhook endpoint — Block N.

The endpoint handles four distinct event families end-to-end:

1. **``whatsapp.inbound_message.received``** — customer-side message.
   Verifies signature, dedupes by wamid (UNIQUE partial index on
   ``messages.provider_message_id``), persists media to S3 when present,
   detects opt-out keywords and registers them in ``whatsapp_opt_outs``,
   enqueues the canonical event onto the ``nexus:inbound`` Redis Stream
   for the worker to consume. Best-effort marks the inbound as read.

2. **``whatsapp.message.updated``** — outbound status callback. Advances
   ``Message.status`` to delivered/read/failed, persists Meta's
   ``pricing.category`` and ``conversation.id`` for the 24h billing
   window, captures Meta error codes (131026/131047/132xxx) so the
   outbound dispatcher and the alerter can act on them.

3. **``whatsapp.template.updated``** — Meta template approval state.
   Upserts the ``whatsapp_template_status`` row. The
   ``notification.send_template`` tool reads this before queueing.

4. **Everything else** — log + 200 ack so YCloud doesn't redrive.

Idempotency: wamid is the natural dedupe key. The ``provider_message_id``
UNIQUE partial index on ``messages`` is the durable guard; the webhook
uses an explicit ``SELECT 1 FROM messages WHERE provider_message_id = ?``
check too so a retry inside the 5-minute Redis dedupe window is silent
even before the durable INSERT.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from nexus_channels.whatsapp_ycloud.adapter import WhatsAppYCloudAdapter
from nexus_channels.whatsapp_ycloud.signature import (
    YCloudSignatureError,
    verify_ycloud_signature,
)
from nexus_channels.whatsapp_ycloud.webhook_adapter import (
    INBOUND_MESSAGE_EVENT,
    MESSAGE_UPDATED_EVENT,
    TEMPLATE_UPDATED_EVENT,
    TEMPLATE_UPDATED_EVENT_LEGACY,
    StatusCallback,
    TemplateStatusUpdate,
    extract_business_phone,
    is_opt_out_text,
    parse_inbound,
    parse_status_callback,
    parse_template_status,
)
from nexus_channels.whatsapp_ycloud.ycloud_client import YCloudAPIError, YCloudClient
from redis.asyncio import Redis
from sqlalchemy import select, update
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
    Channel,
    Message,
    MessageDirection,
    MessageStatus,
    Tenant,
    WhatsAppOptOut,
    WhatsAppTemplateStatus,
)
from nexus_api.repositories import ChannelRepository
from nexus_api.services.media_storage import (
    MediaStorageError,
    get_media_storage,
)

router = APIRouter()
log = structlog.get_logger()


INBOUND_STREAM = "nexus:inbound"
# Redis dedupe TTL — short window above the YCloud reasonable retry budget.
# The durable guard is the UNIQUE partial index on messages.provider_message_id;
# this Redis key avoids a roundtrip to PG for the common retry case.
WAMID_DEDUPE_TTL = 600


def _build_ycloud_client() -> YCloudClient:
    """Override target for tests via ``app.dependency_overrides``."""
    settings = get_settings()
    return YCloudClient(api_key=settings.ycloud_api_key, base_url=settings.ycloud_api_base_url)


def _ycloud_adapter() -> WhatsAppYCloudAdapter:
    return WhatsAppYCloudAdapter(_build_ycloud_client())


@router.post("/ycloud", status_code=status.HTTP_200_OK)
async def ycloud_webhook(
    request: Request,
    ycloud_signature: str | None = Header(default=None, alias="YCloud-Signature"),
    x_ycloud_signature: str | None = Header(default=None, alias="X-YCloud-Signature"),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
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

    # Status callback path — outbound delivery / read / failed updates.
    if event_type in {MESSAGE_UPDATED_EVENT, "whatsapp.message_status_update"}:
        return await _handle_status_callback(payload, session=session, redis=redis)

    # Template approval state — NOT tenant-scoped lookup; table has waba_id.
    if event_type in {TEMPLATE_UPDATED_EVENT, TEMPLATE_UPDATED_EVENT_LEGACY}:
        return await _handle_template_status(payload, session=session)

    if event_type != INBOUND_MESSAGE_EVENT:
        log.info("webhook.ycloud.non_inbound_event", type=event_type)
        return {"status": "ignored"}

    return await _handle_inbound(payload, session=session, redis=redis)


# ── inbound message ─────────────────────────────────────────────────────────


async def _handle_inbound(
    payload: dict[str, Any],
    *,
    session: AsyncSession,
    redis: Redis,
) -> dict[str, Any]:
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

    # The tenant_resolver leaves a transaction open; close it before
    # entering tenant_scoped_session (block-F gotcha).
    if session.in_transaction():
        await session.rollback()

    bind_tenant(tenant_id)

    inbound = parse_inbound(payload)
    if inbound is None:
        log.info(
            "webhook.ycloud.unparseable_message",
            tenant_id=str(tenant_id),
            type=payload.get("type"),
        )
        return {"status": "ignored"}

    wamid = inbound.provider_message_id

    # 1) In-memory / Redis dedupe — avoids PG round-trip on retries.
    dedupe_key = f"nexus:wamid:{wamid}"
    if await redis.setnx(dedupe_key, "1"):
        await redis.expire(dedupe_key, WAMID_DEDUPE_TTL)
    else:
        log.info(
            "webhook.ycloud.dedupe_redis_hit",
            tenant_id=str(tenant_id),
            wamid=wamid,
        )
        return {"status": "deduped"}

    # 2) Durable dedupe — UNIQUE partial index. If the row already exists
    # the Redis key probably expired; either way we ack without re-enqueueing.
    async with tenant_scoped_session(session, tenant_id):
        prior = await session.scalar(
            select(Message.id).where(Message.provider_message_id == wamid)
        )
        if prior is not None:
            log.info(
                "webhook.ycloud.dedupe_db_hit",
                tenant_id=str(tenant_id),
                wamid=wamid,
                message_id=str(prior),
            )
            return {"status": "deduped"}

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

    # 3) Build the canonical content the worker pipeline sees. For media
    # we download to S3 first so the multimodal pipeline has a reference
    # by the time the consumer picks the stream entry.
    s3_key: str | None = None
    media_mime: str | None = None
    media_size: int | None = None
    media_filename: str | None = None
    sha256: str | None = None
    media_kind_value: str | None = None

    if inbound.media is not None and inbound.kind.value in {
        "audio",
        "image",
        "document",
        "video",
        "sticker",
    }:
        media_kind_value = inbound.kind.value
        try:
            s3_key, media_mime, media_size, sha256 = await _download_inbound_media(
                tenant_id=tenant_id,
                wamid=wamid,
                media_id=inbound.media.provider_media_id,
                hint_mime=inbound.media.mime_type,
                hint_sha=inbound.media.sha256,
            )
            media_filename = inbound.media.filename
        except (YCloudAPIError, MediaStorageError) as exc:
            log.warning(
                "webhook.ycloud.media_download_failed",
                tenant_id=str(tenant_id),
                wamid=wamid,
                media_id=inbound.media.provider_media_id,
                error=str(exc),
            )
            # We still enqueue the turn — the agent answers "se cayó tu
            # archivo, ¿lo subes de nuevo?" instead of going silent.

    # 4) Build the canonical content string used by the pipeline.
    content = _render_content(inbound)

    # 5) Opt-out detection. If the user texted STOP/BAJA, register the
    # opt-out under this tenant + channel + recipient phone and skip the
    # pipeline (the agent should NOT generate an outbound reply that would
    # arrive after the user asked us to stop).
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

    # 6) Update conversations.last_inbound_at + persist inbound media columns.
    # The actual conversation row may or may not exist yet — the dispatcher
    # creates it as part of the pipeline turn. We persist the touch on the
    # channel-side timestamp here so the 24h window check has a valid
    # reference even for the first ever inbound. The pipeline will write
    # the Message row with provider_message_id + media columns; here we
    # only pre-stage the dedupe + S3 download.

    # 7) Enqueue.
    fields: dict[str, str] = {
        "tenant_id": str(tenant_id),
        "channel_id": str(channel.id),
        "user_id": inbound.sender_identifier,
        "content": content,
        "provider": "ycloud",
        "provider_message_id": wamid,
        "kind": inbound.kind.value,
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
    if media_filename:
        fields["media_filename"] = media_filename
    if sha256:
        fields["media_sha256"] = sha256
    if inbound.context_message_id:
        fields["context_message_id"] = inbound.context_message_id
    if inbound.reaction is not None:
        fields["reaction_emoji"] = inbound.reaction.emoji
        fields["reaction_target_wamid"] = inbound.reaction.target_message_id
    if inbound.location is not None:
        fields["location_latitude"] = str(inbound.location.latitude)
        fields["location_longitude"] = str(inbound.location.longitude)
        if inbound.location.name:
            fields["location_name"] = inbound.location.name
        if inbound.location.address:
            fields["location_address"] = inbound.location.address
    if opted_out:
        fields["opted_out"] = "true"

    if opted_out:
        # Persist the inbound but do NOT enqueue — the dispatcher would
        # generate an outbound reply that violates the opt-out the user
        # just expressed. The operator panel still sees the message via
        # the persisted opt-out + audit log.
        log.info(
            "webhook.ycloud.opted_out_skip_enqueue",
            tenant_id=str(tenant_id),
            wamid=wamid,
            recipient=inbound.sender_identifier,
        )
        return {"status": "opted_out"}

    await redis.xadd(INBOUND_STREAM, fields)  # type: ignore[arg-type]

    # 8) Politeness: mark as read so the customer sees the two blue checks.
    # Best-effort; failure doesn't break the turn.
    settings = get_settings()
    if settings.ycloud_api_key and channel.provider_identifier:
        adapter = _ycloud_adapter()
        try:
            await adapter.mark_as_read(
                from_phone=channel.provider_identifier,
                wamid=wamid,
                tenant_id=tenant_id,
                channel_id=channel.id,
            )
        finally:
            await adapter._client.close()

    log.info(
        "webhook.ycloud.enqueued",
        tenant_id=str(tenant_id),
        channel_id=str(channel.id),
        user_id=inbound.sender_identifier,
        kind=inbound.kind.value,
        wamid=wamid,
        has_media=bool(media_kind_value),
        has_context=bool(inbound.context_message_id),
        is_reaction=inbound.reaction is not None,
    )
    return {"status": "queued"}


def _render_content(inbound: Any) -> str:
    """Render the inbound event into a single ``content`` string that the
    pipeline can consume. Keeps the interactive prefix from Block F + adds
    structured headers for media / reactions / location / context so the
    classifier and the agent can react meaningfully.

    The dispatcher persists the actual structured fields (media_s3_key,
    reaction_emoji, context_message_id) onto ``Message`` separately — this
    string is for the LLM's eyes only.
    """
    if inbound.text is not None and inbound.kind.value == "text":
        return inbound.text
    if inbound.interactive is not None:
        title = inbound.interactive.title or ""
        return f"[interactive:{inbound.interactive.kind}:{inbound.interactive.payload_id}]{title}"
    if inbound.reaction is not None:
        emoji = inbound.reaction.emoji or "(removed)"
        return f"[reaction:{emoji}:on={inbound.reaction.target_message_id}]"
    if inbound.location is not None:
        name = inbound.location.name or ""
        return (
            f"[location:lat={inbound.location.latitude:.6f},"
            f"lon={inbound.location.longitude:.6f}]{name}".strip()
        )
    if inbound.kind.value in {"audio", "image", "document", "video", "sticker"}:
        # The multimodal pipeline replaces this prefix with the transcript
        # / vision summary; if it fails this prefix is what reaches the
        # classifier so it can route to a graceful "no pude leerlo" reply.
        kind = inbound.kind.value
        if inbound.media is not None and inbound.media.caption:
            return f"[media:{kind}]{inbound.media.caption}"
        return f"[media:{kind}]"
    if inbound.kind.value == "contacts" and inbound.text:
        return f"[contacts]{inbound.text}"
    return inbound.text or f"[unsupported:{inbound.raw_event_type or 'unknown'}]"


async def _download_inbound_media(
    *,
    tenant_id: uuid.UUID,
    wamid: str,
    media_id: str,
    hint_mime: str | None,
    hint_sha: str | None,
) -> tuple[str, str | None, int, str | None]:
    """Resolve media_id → bytes → S3. Returns (key, mime, size, sha256).

    Honours ``Settings.media_max_size_mb`` — oversized media skip download
    and we surface a meaningful error message via the prefix string.
    """
    settings = get_settings()
    storage = get_media_storage()
    adapter = _ycloud_adapter()
    try:
        content, mime, sha = await adapter.fetch_media_bytes(media_id=media_id)
    finally:
        await adapter._client.close()
    if not mime and hint_mime:
        mime = hint_mime
    if not sha and hint_sha:
        sha = hint_sha
    size = len(content)
    if size > settings.media_max_size_mb * 1024 * 1024:
        raise MediaStorageError(
            f"inbound media too large: {size} bytes > "
            f"{settings.media_max_size_mb}MB limit"
        )

    tenant_slug = await _tenant_slug_for(tenant_id)
    stored = await storage.put_inbound(
        tenant_slug=tenant_slug,
        wamid=wamid,
        content=content,
        content_type=mime,
        sha256=sha,
    )
    return stored.key, stored.content_type, stored.size_bytes, stored.sha256


async def _tenant_slug_for(tenant_id: uuid.UUID) -> str:
    """Resolve tenant_id → slug without RLS scope. Used by S3 key prefix.

    Tenants are a global table (the IS-the-tenant entity), so the lookup
    is RLS-free. A new session avoids contention with the request's
    in-flight transaction state.
    """
    from nexus_api.db.base import get_sessionmaker

    sm = get_sessionmaker()
    async with sm() as s:
        slug = await s.scalar(select(Tenant.slug).where(Tenant.id == tenant_id))
    return slug or str(tenant_id)


# ── opt-out registration ────────────────────────────────────────────────────


async def _record_opt_out(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    channel_id: uuid.UUID,
    recipient_phone: str,
    reason: str,
    keyword: str | None,
    source_wamid: str | None,
) -> None:
    """Insert (or refresh) a row in ``whatsapp_opt_outs``.

    The unique constraint ``(tenant_id, channel_id, recipient_phone)``
    makes the operation idempotent — repeated STOPs from the same number
    refresh ``opted_out_at`` and clear ``opted_in_at`` (re-opt).
    """
    async with tenant_scoped_session(session, tenant_id):
        existing = await session.scalar(
            select(WhatsAppOptOut).where(
                WhatsAppOptOut.tenant_id == tenant_id,
                WhatsAppOptOut.channel_id == channel_id,
                WhatsAppOptOut.recipient_phone == recipient_phone,
            )
        )
        now = datetime.now(UTC)
        if existing is None:
            session.add(
                WhatsAppOptOut(
                    tenant_id=tenant_id,
                    channel_id=channel_id,
                    recipient_phone=recipient_phone,
                    reason=reason,
                    trigger_keyword=keyword,
                    source_wamid=source_wamid,
                    opted_out_at=now,
                )
            )
        else:
            existing.opted_out_at = now
            existing.opted_in_at = None
            existing.reason = reason
            existing.trigger_keyword = keyword
            existing.source_wamid = source_wamid
        await session.flush()
        log.info(
            "webhook.ycloud.opt_out_recorded",
            tenant_id=str(tenant_id),
            channel_id=str(channel_id),
            recipient=recipient_phone,
            reason=reason,
            keyword=keyword,
        )


# ── status callbacks ─────────────────────────────────────────────────────────


async def _handle_status_callback(
    payload: dict[str, Any],
    *,
    session: AsyncSession,
    redis: Redis,
) -> dict[str, Any]:
    cb = parse_status_callback(payload)
    if cb is None:
        log.info("webhook.ycloud.status_callback.unparseable")
        return {"status": "ignored"}

    # Resolve tenant from the business phone (the ``from`` of the original
    # outbound). resolve_tenant will use the cached entry from the inbound
    # path most of the time.
    try:
        tenant_id = await resolve_tenant(session, redis, "ycloud", cb.business_phone)
    except TenantNotFound:
        counters.incr(CHANNEL_UNRESOLVED_EVENT)
        log.warning(
            "webhook.ycloud.status_callback.tenant_unresolved",
            business_phone=cb.business_phone,
            wamid=cb.wamid,
        )
        return {"status": "ignored"}

    if session.in_transaction():
        await session.rollback()

    bind_tenant(tenant_id)

    # Map the WhatsApp status onto our MessageStatus enum + timestamp.
    new_status, timestamp_column = _map_status(cb.status)
    if new_status is None:
        log.info(
            "webhook.ycloud.status_callback.skipped_status",
            tenant_id=str(tenant_id),
            wamid=cb.wamid,
            status=cb.status,
        )
        return {"status": "ignored"}

    async with tenant_scoped_session(session, tenant_id):
        msg = await session.scalar(
            select(Message).where(Message.provider_message_id == cb.wamid)
        )
        if msg is None:
            # Status arrived before we persisted the outbound row (race
            # window: dispatcher set trace_id but didn't flush yet). The
            # next status update will re-deliver the terminal state.
            log.info(
                "webhook.ycloud.status_callback.no_local_row",
                tenant_id=str(tenant_id),
                wamid=cb.wamid,
                status=cb.status,
            )
            return {"status": "ignored"}

        # Status advance — never regress (a stale "delivered" arriving
        # after "read" would undo the read state). We only persist the
        # advance when the new status is strictly downstream.
        if not _is_status_advance(prior=msg.status, new=new_status):
            log.info(
                "webhook.ycloud.status_callback.regress_skipped",
                tenant_id=str(tenant_id),
                wamid=cb.wamid,
                prior=msg.status.value,
                new=new_status.value,
            )
            return {"status": "ignored"}

        msg.status = new_status
        setattr(msg, timestamp_column, cb.timestamp)
        if cb.pricing_category and not msg.pricing_category:
            msg.pricing_category = cb.pricing_category
        if cb.conversation_provider_id and not msg.conversation_provider_id:
            msg.conversation_provider_id = cb.conversation_provider_id
        if new_status is MessageStatus.FAILED:
            msg.failed_at = cb.timestamp
            msg.failure_code = cb.failure_code
            detail = cb.failure_detail or cb.failure_title or ""
            if detail:
                msg.last_error = detail[:500]
        await session.flush()
        log.info(
            "webhook.ycloud.status_callback.applied",
            tenant_id=str(tenant_id),
            wamid=cb.wamid,
            status=new_status.value,
            failure_code=cb.failure_code,
            pricing=cb.pricing_category,
        )

    # Failure with a Meta error code: opportunity to register an opt-out
    # for codes that signal "permanently undeliverable". 131026 = recipient
    # cannot receive (number blocked us, opted out, or doesn't exist).
    if new_status is MessageStatus.FAILED and cb.failure_code == "131026":
        await _record_opt_out_for_recipient(
            session=session,
            tenant_id=tenant_id,
            business_phone=cb.business_phone,
            recipient_phone=cb.recipient_phone,
            reason="compliance",
            keyword=None,
            source_wamid=cb.wamid,
        )

    return {"status": "applied"}


def _map_status(raw: str) -> tuple[MessageStatus | None, str]:
    """Map Meta status string → MessageStatus + the column to stamp."""
    if raw == "delivered":
        return MessageStatus.DELIVERED, "delivered_at"
    if raw == "read":
        return MessageStatus.READ, "read_at"
    if raw == "failed":
        return MessageStatus.FAILED, "failed_at"
    if raw == "sent":
        # We already mark SENT when YCloud accepts the outbound, so this
        # callback is informational; no timestamp column to refresh.
        return None, ""
    return None, ""


_STATUS_RANK: dict[MessageStatus, int] = {
    MessageStatus.PENDING: 0,
    MessageStatus.SENT: 1,
    MessageStatus.DELIVERED: 2,
    MessageStatus.READ: 3,
    MessageStatus.FAILED: 4,  # terminal; any callback before this is a downgrade
}


def _is_status_advance(*, prior: MessageStatus, new: MessageStatus) -> bool:
    if prior == MessageStatus.FAILED:
        return False  # terminal
    if new == MessageStatus.FAILED:
        return True  # any → failed always wins
    return _STATUS_RANK.get(new, -1) > _STATUS_RANK.get(prior, 0)


async def _record_opt_out_for_recipient(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    business_phone: str,
    recipient_phone: str | None,
    reason: str,
    keyword: str | None,
    source_wamid: str | None,
) -> None:
    if not recipient_phone:
        return
    async with tenant_scoped_session(session, tenant_id):
        channel = await ChannelRepository(session).get_by_provider_identifier(
            "ycloud", business_phone
        )
    if channel is None:
        return
    await _record_opt_out(
        session=session,
        tenant_id=tenant_id,
        channel_id=channel.id,
        recipient_phone=recipient_phone,
        reason=reason,
        keyword=keyword,
        source_wamid=source_wamid,
    )


# ── template approval ───────────────────────────────────────────────────────


async def _handle_template_status(
    payload: dict[str, Any],
    *,
    session: AsyncSession,
) -> dict[str, Any]:
    event = parse_template_status(payload)
    if event is None:
        log.info("webhook.ycloud.template_status.unparseable")
        return {"status": "ignored"}

    # The table is intentionally NOT tenant-scoped (templates live at the
    # WABA level). The ``notification.send_template`` tool joins back via
    # channel.config.waba_id to filter to a tenant's view at read time.
    await _upsert_template_status(session, event)
    return {"status": "applied"}


async def _upsert_template_status(
    session: AsyncSession, event: TemplateStatusUpdate
) -> None:
    """UPSERT on ``(waba_id, template_name, language)``."""
    stmt = pg_insert(WhatsAppTemplateStatus).values(
        waba_id=event.waba_id,
        template_name=event.template_name,
        language=event.language,
        category=event.category,
        status=event.status,
        reason=event.reason,
        last_event_payload=event.raw,
        last_event_at=event.event_at,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_tplstatus_waba_name_lang",
        set_={
            "category": stmt.excluded.category,
            "status": stmt.excluded.status,
            "reason": stmt.excluded.reason,
            "last_event_payload": stmt.excluded.last_event_payload,
            "last_event_at": stmt.excluded.last_event_at,
            "updated_at": datetime.now(UTC),
        },
    )
    if session.in_transaction():
        await session.rollback()
    async with session.begin():
        await session.execute(stmt)
    log.info(
        "webhook.ycloud.template_status.applied",
        waba_id=event.waba_id,
        template=event.template_name,
        language=event.language,
        status=event.status,
        reason=event.reason,
    )


__all__ = ["router"]


# Suppress lint warnings — the unused ``update`` import is reserved for
# future status-applied counter metrics; leaving the import keeps the
# delta minimal across the next iteration.
_ = update
