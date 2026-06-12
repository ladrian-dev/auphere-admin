"""Meta WhatsApp Cloud API webhook endpoint.

Speaks Meta's wire format directly. The route handles:

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
    MetaAPIError,
    MetaChannelAdapter,
    MetaClient,
    MetaSignatureError,
    extract_business_phone,
    extract_phone_number_id,
    is_opt_out_text,
    parse_app_state_sync,
    parse_history_sync,
    parse_inbound,
    parse_message_echo,
    parse_status_callback,
    parse_template_status,
    verify_meta_signature,
)
from nexus_channels.whatsapp_meta.credentials import MetaCredentialsRepository
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
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Message,
    MessageStatus,
    Tenant,
    WhatsAppOptOut,
    WhatsAppTemplateStatus,
)
from nexus_api.repositories import ChannelRepository
from nexus_api.repositories.auphere_channels import (
    ResolvedAuphereChannel,
)
from nexus_api.repositories.auphere_channels import (
    resolve_channel_for_inbound as resolve_owner_channel_for_inbound,
)
from nexus_api.services.media_storage import MediaStorageError, get_media_storage
from nexus_api.services.owner_channel_flow import handle_owner_inbound

router = APIRouter()
log = structlog.get_logger()


INBOUND_STREAM = "nexus:inbound"
WAMID_DEDUPE_TTL = 600  # above Meta's retry budget

# Coexistence-only buffer streams. The webhook ack must return 200 within
# Meta's retry budget, so persistence (which may involve thousands of
# history rows per WABA) lives in a consumer that runs out-of-band.
#
# Until the worker package (block D in CLAUDE.md) materialises, these
# streams act as a durable buffer: events accumulate in Redis with a
# bounded MAXLEN so we never run away on memory, and the consumer reads
# them later. Each xadd payload includes the full parsed dataclass fields
# plus the resolved ``tenant_id`` so the consumer can write under the
# right RLS context without re-parsing the envelope.
COEXISTENCE_ECHO_STREAM = "nexus:meta:echoes"
COEXISTENCE_STATE_SYNC_STREAM = "nexus:meta:state_sync"
COEXISTENCE_HISTORY_STREAM = "nexus:meta:history"
# 10k events ≈ 24h of moderate Coexistence traffic. Cap is approximate
# (Redis trims on insert when over by 50+) — fine for a buffer.
COEXISTENCE_STREAM_MAXLEN = 10_000


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

    # Owner backchannel detection — events whose ``phone_number_id`` belongs
    # to a registered Auphere owner-channel number are NOT tenant traffic.
    # Route inbound text to the owner flow; drop everything else (status
    # callbacks on the backchannel carry no state we track).
    phone_number_id = extract_phone_number_id(payload)
    if phone_number_id:
        owner_channel = await resolve_owner_channel_for_inbound(
            session, provider_phone_id=phone_number_id
        )
        if owner_channel is not None:
            return await _handle_owner_channel_event(
                payload, channel=owner_channel, session=session, redis=redis
            )

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
            elif field == "smb_message_echoes":
                await _handle_message_echo(payload, session=session, redis=redis)
                handled = True
            elif field == "smb_app_state_sync":
                await _handle_app_state_sync(payload, session=session, redis=redis)
                handled = True
            elif field == "history":
                await _handle_history_sync(payload, session=session, redis=redis)
                handled = True
            else:
                log.info("webhook.meta.unhandled_field", field=field)

    return {"status": "ok" if handled else "ignored"}


# ── owner backchannel ──────────────────────────────────────────────────────


async def _handle_owner_channel_event(
    payload: dict[str, Any],
    *,
    channel: ResolvedAuphereChannel,
    session: AsyncSession,
    redis: Redis,
) -> dict[str, Any]:
    """Route a webhook event addressed to an Auphere owner-channel number.

    Only inbound messages drive the backchannel; statuses/template events
    on the backchannel are acked and dropped. The HMAC signature was
    already verified at the route layer (app secret), so no per-channel
    secret dance is needed.
    """
    inbound = parse_inbound(payload)
    if inbound is None:
        log.info(
            "webhook.meta.owner_channel_non_inbound",
            channel=channel.display_name,
        )
        return {"status": "owner_channel:ignored"}
    result = await handle_owner_inbound(
        session,
        redis,
        channel=channel,
        sender_phone=inbound.sender_identifier,
        text=inbound.text,
    )
    return {"status": f"owner_channel:{result.get('status', 'ok')}", **{
        k: v for k, v in result.items() if k != "status"
    }}


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

    # Media download — resolve the Cloud API media id to bytes and persist
    # to S3 BEFORE enqueue so the multimodal pipeline has a reference by the
    # time the consumer picks up the stream entry. On failure we still
    # enqueue the turn (the agent asks the user to resend) instead of going
    # silent.
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
        except (MetaAPIError, MediaStorageError) as exc:
            log.warning(
                "webhook.meta.media_download_failed",
                tenant_id=str(tenant_id),
                wamid=wamid,
                media_id=inbound.media.provider_media_id,
                error=str(exc),
            )

    content = _render_content(inbound)

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
        # Persist the opt-out but do NOT enqueue — the dispatcher would
        # otherwise generate an outbound reply that violates the opt-out the
        # user just expressed. The operator panel still sees the message via
        # the persisted opt-out + audit log.
        log.info(
            "webhook.meta.opted_out_skip_enqueue",
            tenant_id=str(tenant_id),
            wamid=wamid,
            recipient=inbound.sender_identifier,
        )
        return {"status": "opted_out"}

    await redis.xadd(INBOUND_STREAM, fields)

    # Politeness: mark as read so the customer sees the two blue checks.
    # Best-effort — failure never blocks the turn.
    await _mark_read_best_effort(
        tenant_id=tenant_id,
        channel_id=channel.id,
        from_phone=channel.provider_identifier,
        wamid=wamid,
    )

    log.info(
        "webhook.meta.inbound_enqueued",
        tenant_id=str(tenant_id),
        channel_id=str(channel.id),
        wamid=wamid,
        kind=inbound.kind.value,
        has_media=bool(media_kind_value),
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


# ── Coexistence-only events ────────────────────────────────────────────────
#
# Each handler:
#  1. Parses the envelope into a dataclass (cheap).
#  2. Resolves the tenant from ``display_phone_number`` so the consumer
#     can write under RLS without re-resolving from raw payload.
#  3. xadd's a flat field dict to the appropriate buffer stream with a
#     bounded MAXLEN. Persistence (history may carry tens of thousands of
#     rows over several hours per WABA) is the consumer's job — block D.
#  4. Returns 200 fast so Meta doesn't retry.
#
# If the tenant cannot be resolved, the event is dropped with a counter
# bump (same policy as :func:`_handle_inbound`). Coexistence onboarding
# guarantees the channel row exists before any of these fire, so an
# unresolved tenant means the WABA belongs to a different installation
# of the app — not our traffic.


async def _resolve_tenant_for_event(
    payload: dict[str, Any],
    *,
    session: AsyncSession,
    redis: Redis,
) -> tuple[uuid.UUID | None, str | None]:
    """Shared resolver for all three Coexistence handlers."""
    business_phone = extract_business_phone(payload)
    if not business_phone:
        return None, None
    try:
        tenant_id = await resolve_tenant(session, redis, "meta", business_phone)
    except TenantNotFound:
        counters.incr(CHANNEL_UNRESOLVED_EVENT)
        log.warning(
            "channel.unresolved_event",
            provider="meta",
            identifier=business_phone,
        )
        return None, business_phone
    if session.in_transaction():
        await session.rollback()
    bind_tenant(tenant_id)
    return tenant_id, business_phone


async def _handle_message_echo(
    payload: dict[str, Any],
    *,
    session: AsyncSession,
    redis: Redis,
) -> dict[str, Any]:
    echo = parse_message_echo(payload)
    if echo is None:
        return {"status": "ignored"}
    tenant_id, _ = await _resolve_tenant_for_event(payload, session=session, redis=redis)
    if tenant_id is None:
        return {"status": "ignored"}
    fields: dict[str, str] = {
        "tenant_id": str(tenant_id),
        "waba_id": echo.waba_id,
        "phone_number_id": echo.phone_number_id,
        "provider_message_id": echo.provider_message_id,
        "sender_identifier": echo.sender_identifier,
        "recipient_identifier": echo.recipient_identifier,
        "received_at": echo.received_at.isoformat(),
    }
    if echo.text is not None:
        fields["text"] = echo.text
    await redis.xadd(
        COEXISTENCE_ECHO_STREAM,
        fields,
        maxlen=COEXISTENCE_STREAM_MAXLEN,
        approximate=True,
    )
    log.info(
        "webhook.meta.smb_message_echo.enqueued",
        tenant_id=str(tenant_id),
        wamid=echo.provider_message_id,
    )
    return {"status": "enqueued"}


async def _handle_app_state_sync(
    payload: dict[str, Any],
    *,
    session: AsyncSession,
    redis: Redis,
) -> dict[str, Any]:
    sync = parse_app_state_sync(payload)
    if sync is None:
        return {"status": "ignored"}
    tenant_id, _ = await _resolve_tenant_for_event(payload, session=session, redis=redis)
    if tenant_id is None:
        return {"status": "ignored"}
    # State sync carries an in-payload contacts list whose size is bounded
    # by Meta's batch ceiling; the consumer needs the raw value to do the
    # actual contact upsert. Stash the JSON-encoded payload alongside the
    # parsed summary so the consumer can do both passes (summary now,
    # detailed persistence later) without re-fetching.
    raw_value = _extract_change_value(payload, field="smb_app_state_sync")
    fields: dict[str, str] = {
        "tenant_id": str(tenant_id),
        "waba_id": sync.waba_id,
        "phone_number_id": sync.phone_number_id,
        "contact_count": str(sync.contact_count),
        "has_more": "1" if sync.has_more else "0",
        "raw_value": json.dumps(raw_value, separators=(",", ":")) if raw_value else "",
    }
    await redis.xadd(
        COEXISTENCE_STATE_SYNC_STREAM,
        fields,
        maxlen=COEXISTENCE_STREAM_MAXLEN,
        approximate=True,
    )
    log.info(
        "webhook.meta.smb_app_state_sync.enqueued",
        tenant_id=str(tenant_id),
        contact_count=sync.contact_count,
        has_more=sync.has_more,
    )
    return {"status": "enqueued"}


async def _handle_history_sync(
    payload: dict[str, Any],
    *,
    session: AsyncSession,
    redis: Redis,
) -> dict[str, Any]:
    hist = parse_history_sync(payload)
    if hist is None:
        return {"status": "ignored"}
    tenant_id, _ = await _resolve_tenant_for_event(payload, session=session, redis=redis)
    if tenant_id is None:
        return {"status": "ignored"}
    raw_value = _extract_change_value(payload, field="history")
    fields: dict[str, str] = {
        "tenant_id": str(tenant_id),
        "waba_id": hist.waba_id,
        "phone_number_id": hist.phone_number_id,
        "message_count": str(hist.message_count),
        "raw_value": json.dumps(raw_value, separators=(",", ":")) if raw_value else "",
    }
    if hist.error_code is not None:
        fields["error_code"] = str(hist.error_code)
    await redis.xadd(
        COEXISTENCE_HISTORY_STREAM,
        fields,
        maxlen=COEXISTENCE_STREAM_MAXLEN,
        approximate=True,
    )
    log.info(
        "webhook.meta.history_sync.enqueued",
        tenant_id=str(tenant_id),
        message_count=hist.message_count,
        error_code=hist.error_code,
    )
    return {"status": "enqueued"}


def _extract_change_value(
    payload: dict[str, Any], *, field: str
) -> dict[str, Any] | None:
    """Pull ``changes[].value`` for the first change matching ``field``.

    Coexistence handlers stream the raw value alongside the parsed
    summary so the future consumer can persist contacts / history rows
    without re-walking the envelope.
    """
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes") or []:
            if isinstance(change, dict) and change.get("field") == field:
                value = change.get("value")
                if isinstance(value, dict):
                    return value
    return None


# ── inbound content + media helpers ──────────────────────────────────────────


def _build_meta_adapter() -> MetaChannelAdapter:
    """Construct a Meta adapter for webhook-side reads (media fetch,
    mark-as-read). The credentials loader opens its own tenant-scoped
    session so RLS is the only authority on which BISUAT it reads.
    """
    settings = get_settings()
    client = MetaClient(
        app_secret=settings.meta_app_secret,
        require_appsecret_proof=settings.meta_require_appsecret_proof,
    )

    async def _loader(*, tenant_id: uuid.UUID) -> tuple[str, str]:
        sm = get_sessionmaker()
        async with sm() as cred_session, tenant_scoped_session(cred_session, tenant_id):
            creds = await MetaCredentialsRepository(cred_session).get_or_raise()
            return (creds.phone_number_id, creds.bisuat)

    return MetaChannelAdapter(client, credentials_loader=_loader)


def _render_content(inbound: InboundMessage) -> str:
    """Render the inbound event into a single ``content`` string the pipeline
    consumes. Provider-agnostic contract so the
    worker consumer sees uniform stream entries regardless of transport.

    The multimodal pipeline overwrites the media prefix with the transcript /
    vision summary; if download failed this prefix is what reaches the
    classifier so it can route to a graceful "no pude leerlo" reply.
    """
    if inbound.text is not None and inbound.kind.value == "text":
        return str(inbound.text)
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

    Honours ``Settings.media_max_size_mb`` — oversized media raise so the
    caller surfaces a meaningful prefix instead of persisting a bomb.
    """
    settings = get_settings()
    storage = get_media_storage()
    adapter = _build_meta_adapter()
    try:
        content, mime, sha = await adapter.fetch_media_bytes(
            media_id=media_id, tenant_id=tenant_id
        )
    finally:
        await adapter._client.close()
    if not mime and hint_mime:
        mime = hint_mime
    if not sha and hint_sha:
        sha = hint_sha
    size = len(content)
    if size > settings.media_max_size_mb * 1024 * 1024:
        raise MediaStorageError(
            f"inbound media too large: {size} bytes > {settings.media_max_size_mb}MB limit"
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
    """Resolve tenant_id → slug without RLS scope (tenants is a global
    table). Used to build the S3 key prefix."""
    sm = get_sessionmaker()
    async with sm() as s:
        slug = await s.scalar(select(Tenant.slug).where(Tenant.id == tenant_id))
    return slug or str(tenant_id)


async def _mark_read_best_effort(
    *,
    tenant_id: uuid.UUID,
    channel_id: uuid.UUID,
    from_phone: str,
    wamid: str,
) -> None:
    """Send the read receipt. Never raises — the inbound turn already
    enqueued, so a failed read receipt is cosmetic."""
    adapter = _build_meta_adapter()
    try:
        await adapter.mark_as_read(
            from_phone=from_phone,
            wamid=wamid,
            tenant_id=tenant_id,
            channel_id=channel_id,
        )
    except Exception as exc:
        log.info(
            "webhook.meta.mark_as_read_failed",
            tenant_id=str(tenant_id),
            wamid=wamid,
            error=str(exc),
        )
    finally:
        await adapter._client.close()


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
