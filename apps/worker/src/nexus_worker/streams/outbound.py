"""Outbound message dispatcher.

Drains ``messages WHERE status='pending'`` and pushes each one through the
:class:`MetaChannelAdapter`. Drives the WhatsApp side of every smoke test
that asks "agent answers in the customer's WhatsApp".

Tenant isolation:
- Outer loop discovers tenants once per tick via a tenant-agnostic query
  on the ``tenants`` table (RLS-free; it's a global table).
- Per tenant, a fresh session enters ``tenant_scoped_session`` and runs the
  ``SELECT ... FOR UPDATE SKIP LOCKED`` against ``messages``. RLS limits the
  scan to that tenant's rows; SKIP LOCKED lets multiple worker replicas
  share the load without waiting on each other.

Block N additions:

- **Opt-out enforcement**: before every send the dispatcher checks
  ``whatsapp_opt_outs`` for an active entry covering (channel, recipient).
  If matched, the row is parked ``failed`` with ``failure_code='opted_out'``
  and never retried.
- **Meta error-code classification**: 4xx with codes ``131026`` (recipient
  unable), ``131047`` (outside 24h window), ``132xxx`` (template
  paused/disabled), or ``100`` (bad params) are *no-retry* — the dispatcher
  stamps ``failed`` immediately. The burst tracker still fires for 5xx
  storms; for 4xx we want loud single-row failures, not burst alerts.
- **provider_message_id persisted**: once the provider accepts the send, the wamid
  is stamped on ``messages.provider_message_id``. The UNIQUE partial index
  guarantees the inbound status callbacks reference the same row.
- **Media outbound**: pending messages with ``media_kind`` set route through
  the matching adapter method. ``media_s3_key`` resolves via the storage
  adapter to a presigned URL, which is what we pass to Cloud API.
- **Reactions outbound**: rows with ``reaction_emoji`` + ``reaction_target_
  wamid`` skip text rendering and call ``send_reaction``.

Backoff:
- Each row tracks ``attempts``. On a *retryable* failure we increment,
  capture the error in ``last_error``, and re-set status='pending' until
  attempts hits ``MAX_ATTEMPTS``. After that the row is parked in 'failed'
  and the alerter (block H+) bubbles it up.
- A simple exponential pause within the same tick is unnecessary because
  the loop tick itself is the natural backoff unit (default 500ms).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Channel,
    ChannelType,
    Conversation,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
    Tenant,
    TenantStatus,
    WhatsAppOptOut,
)
from nexus_api.services.media_storage import MediaStorageError, get_media_storage
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from nexus_channels.base import SendResult

# Provider → ChannelAdapter. Every adapter exposes the same outbound method
# surface (send_text/template/interactive/image/audio/video/document/reaction)
# with identical keyword signatures, so the dispatcher treats them uniformly
# and only differs in *which* adapter it resolves per ``channels.provider``.
AdapterRegistry = Mapping[str, Any]

log = structlog.get_logger(__name__)

# Tunables — outbound is bursty (think reminder fan-out at the same minute)
# but most ticks see zero pending rows. 500ms tick + 50 rows per tenant per
# tick == 100 msg/s headroom per worker which exceeds the 50 msg/s target.
DEFAULT_TICK_SECONDS = 0.5
DEFAULT_BATCH_SIZE = 50
MAX_ATTEMPTS = 3

# WhatsApp Cloud API error codes that are not worth retrying.
# Source: Meta Cloud API error reference.
#
# The codes carry semantics:
# - 100        : bad request / parameter / template mismatch.
# - 131026     : recipient cannot receive (number blocked, no WhatsApp).
# - 131047     : outside 24h window (free-form sent post-window).
# - 131049     : message generated against a number that exited the system.
# - 131051     : unsupported message type.
# - 132000-132069 : template-related rejects (paused, disabled, bad params).
# - 368        : temporary block on the WABA (no retry, escalate).
_NO_RETRY_CODES: frozenset[str] = frozenset(
    {
        "100",
        "131026",
        "131047",
        "131049",
        "131051",
        "131052",
        "131053",
        "133015",  # number can't be registered
        "368",
    }
)
# Numeric ranges expressed as prefixes; matches anything starting with these.
_NO_RETRY_PREFIXES: tuple[str, ...] = ("132",)  # all 132xxx template rejects


async def run_outbound_dispatcher(
    *,
    adapters: AdapterRegistry,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    """Background task. Returns when ``stop`` is set.

    ``adapters`` maps ``channels.provider`` (``"meta"``) to the
    matching :class:`ChannelAdapter`. Each pending row resolves its adapter
    from the channel's provider, so a single worker serves both transports.
    """
    log.info(
        "outbound.dispatcher.start",
        tick_seconds=tick_seconds,
        batch=batch_size,
        providers=sorted(adapters.keys()),
    )
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            tenant_ids = await _list_active_tenants(sm)
            for tid in tenant_ids:
                if stop.is_set():
                    break
                await _drain_tenant(sm, tid, adapters, batch_size)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("outbound.dispatcher.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("outbound.dispatcher.stopped")


async def _list_active_tenants(sm: sa.orm.sessionmaker) -> list[uuid.UUID]:  # type: ignore[type-arg]
    async with sm() as session:
        rows = await session.execute(
            sa.select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE)
        )
        return [row[0] for row in rows]


async def _drain_tenant(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
    tenant_id: uuid.UUID,
    adapters: AdapterRegistry,
    batch_size: int,
) -> None:
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        result = await session.execute(
            sa.select(Message)
            .where(
                Message.direction == MessageDirection.OUTBOUND,
                Message.status == MessageStatus.PENDING,
            )
            .order_by(Message.created_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        pending = list(result.scalars())
        if not pending:
            return
        log.info(
            "outbound.dispatcher.batch",
            tenant_id=str(tenant_id),
            count=len(pending),
        )
        for msg in pending:
            await _send_one(session, msg, adapters, tenant_id)


async def _send_one(
    session: AsyncSession,
    msg: Message,
    adapters: AdapterRegistry,
    tenant_id: uuid.UUID,
) -> None:
    """Resolve the channel + recipient, send via adapter, update status.

    Routing precedence on the persisted message row:
    1. ``reaction_emoji`` + ``reaction_target_wamid`` → ``send_reaction``.
    2. ``media_kind`` set → ``send_image/audio/document/video`` (resolved
       to a presigned S3 URL).
    3. Otherwise → ``send_text`` (the historical path).
    """
    info = await session.execute(
        sa.select(
            Channel.id,
            Channel.provider_identifier,
            Channel.type,
            Channel.provider,
            Customer.identifier,
            Channel.config,
        )
        .join(Conversation, Conversation.channel_id == Channel.id)
        .join(Customer, Customer.id == Conversation.customer_id)
        .where(Conversation.id == msg.conversation_id)
        .limit(1)
    )
    row = info.first()
    if row is None:
        msg.status = MessageStatus.FAILED
        msg.attempts += 1
        msg.failed_at = datetime.now(UTC)
        msg.failure_code = "no_channel"
        msg.last_error = "channel/customer not found for conversation"
        log.warning(
            "outbound.dispatcher.no_channel_for_conversation",
            tenant_id=str(tenant_id),
            message_id=str(msg.id),
        )
        return
    channel_id, business_phone, channel_type, provider, recipient, channel_config = row
    # Meta Commerce catalog linked to this WABA — used to resolve native
    # product-card messages. Resolved server-side; the LLM never sees it.
    catalog_id = (channel_config or {}).get("catalog_id")
    # Thumbnail retailer_id for the native catalog message (Meta requires a
    # valid catalog item to render the catalog card). Set once in channel
    # config; the LLM never sees it.
    catalog_thumbnail = (channel_config or {}).get("catalog_thumbnail_retailer_id")
    if channel_type != ChannelType.WHATSAPP:
        msg.status = MessageStatus.FAILED
        msg.failed_at = datetime.now(UTC)
        msg.failure_code = "unsupported_channel"
        msg.last_error = f"unsupported channel type: {channel_type}"
        return

    # Resolve the adapter for this channel's provider. A channel whose
    # provider has no registered adapter is parked failed (no retry) instead
    # of silently sending through the wrong transport — a foreign provider's
    # credential has no authority over the tenant's WABA.
    adapter = adapters.get(provider)
    if adapter is None:
        msg.status = MessageStatus.FAILED
        msg.failed_at = datetime.now(UTC)
        msg.failure_code = "unsupported_provider"
        msg.last_error = f"no adapter registered for provider: {provider}"
        log.warning(
            "outbound.dispatcher.unsupported_provider",
            tenant_id=str(tenant_id),
            message_id=str(msg.id),
            provider=provider,
        )
        return

    # Opt-out check (Block N). The recipient's number may have STOP'd us —
    # park the row failed instead of sending. The audit log + operator alert
    # already happened at opt-out registration time.
    opted_out = await session.scalar(
        sa.select(WhatsAppOptOut.id).where(
            WhatsAppOptOut.channel_id == channel_id,
            WhatsAppOptOut.recipient_phone == recipient,
            WhatsAppOptOut.opted_in_at.is_(None),
        )
    )
    if opted_out is not None:
        msg.status = MessageStatus.FAILED
        msg.failed_at = datetime.now(UTC)
        msg.failure_code = "opted_out"
        msg.last_error = "recipient is opted out of WhatsApp messages"
        log.info(
            "outbound.dispatcher.blocked_opt_out",
            tenant_id=str(tenant_id),
            message_id=str(msg.id),
            recipient=recipient,
        )
        return

    try:
        result = await _dispatch_message(
            adapter=adapter,
            msg=msg,
            from_phone=business_phone,
            recipient=recipient,
            tenant_id=tenant_id,
            channel_id=channel_id,
            catalog_id=catalog_id,
            catalog_thumbnail=catalog_thumbnail,
        )
    except MediaStorageError as exc:
        # Media couldn't be resolved to a presigned URL. Park failed.
        msg.attempts += 1
        msg.status = MessageStatus.FAILED
        msg.failed_at = datetime.now(UTC)
        msg.failure_code = "media_unavailable"
        msg.last_error = f"media storage error: {exc}"[:500]
        log.warning(
            "outbound.dispatcher.media_storage_failed",
            tenant_id=str(tenant_id),
            message_id=str(msg.id),
            error=msg.last_error,
        )
        return
    except Exception as exc:
        await _handle_send_exception(
            session=session,
            msg=msg,
            exc=exc,
            tenant_id=tenant_id,
        )
        return

    msg.status = MessageStatus.SENT
    msg.last_error = None
    msg.trace_id = result.provider_message_id
    msg.provider_message_id = result.provider_message_id or msg.provider_message_id
    if msg.cost_usd is None and result.cost_usd_estimate is not None:
        msg.cost_usd = result.cost_usd_estimate
    msg.latency_ms = msg.latency_ms or _ms_since(msg.created_at)
    log.info(
        "outbound.dispatcher.sent",
        tenant_id=str(tenant_id),
        message_id=str(msg.id),
        provider_message_id=result.provider_message_id,
        kind=msg.media_kind or ("reaction" if msg.reaction_emoji else "text"),
    )


async def _dispatch_message(
    *,
    adapter: Any,
    msg: Message,
    from_phone: str,
    recipient: str,
    tenant_id: uuid.UUID,
    channel_id: uuid.UUID,
    catalog_id: str | None = None,
    catalog_thumbnail: str | None = None,
) -> SendResult:
    """Route the pending row to the right adapter call."""
    context = msg.context_message_id

    # -1) HSM template rows (migration 0049, ADR-028) — written by the
    # broadcast fan-out service. ``template_payload`` mirrors the
    # ``interactive_payload`` pattern: the row is self-contained, retry
    # bookkeeping applies unchanged, and template rejects (132xxx) are
    # already in the no-retry list. ``content`` only carries a preview
    # for the operator panel.
    if msg.template_payload:
        tp = msg.template_payload
        return await adapter.send_template(
            from_phone=from_phone,
            recipient=recipient,
            template_name=tp["name"],
            language=tp.get("language", "es"),
            params=tp.get("params", {}),
            tenant_id=tenant_id,
            channel_id=channel_id,
            context_message_id=context,
        )

    # 0) Interactive components take priority over text but coexist
    # with the rest. A row with ``interactive_payload`` set is the
    # output of a ``response.send_interactive`` tool call; the field
    # carries our tool-side shape and we convert to Meta's
    # ``interactive`` block here. The row's ``content`` carries the
    # body (for operator-panel previews) but the Cloud API only sees
    # the structured block.
    if msg.interactive_payload:
        payload = msg.interactive_payload
        # Product cards: the Facebook-for-WooCommerce catalog keys each item by
        # the raw WooCommerce product id (verified against Meta's catalog), so
        # the ids the agent passes ARE the product_retailer_ids — sent as-is.
        interactive_block = _to_meta_interactive(
            payload, catalog_id=catalog_id, catalog_thumbnail=catalog_thumbnail
        )
        # The tool's payload may carry an in-band ``context_message_id``
        # for quoted replies; prefer it over the row-level ``context``
        # (the row's column is populated by media / text paths, not by
        # the interactive tool).
        quote_wamid = payload.get("context_message_id") or context
        return await adapter.send_interactive(
            from_phone=from_phone,
            recipient=recipient,
            interactive=interactive_block,
            tenant_id=tenant_id,
            channel_id=channel_id,
            context_message_id=quote_wamid,
        )

    # 1) Reactions take priority — same row can't carry media + a reaction.
    if msg.reaction_emoji is not None and msg.reaction_target_wamid:
        return await adapter.send_reaction(
            from_phone=from_phone,
            recipient=recipient,
            target_message_id=msg.reaction_target_wamid,
            emoji=msg.reaction_emoji,
            tenant_id=tenant_id,
            channel_id=channel_id,
        )

    # 2) Media outbound.
    if msg.media_kind and msg.media_s3_key:
        storage = get_media_storage()
        link = await storage.presign_get(msg.media_s3_key)
        kind = msg.media_kind
        caption = msg.content if msg.content and not msg.content.startswith("[media:") else None
        if kind == "image":
            return await adapter.send_image(
                from_phone=from_phone,
                recipient=recipient,
                link=link,
                caption=caption,
                tenant_id=tenant_id,
                channel_id=channel_id,
                context_message_id=context,
            )
        if kind == "audio":
            return await adapter.send_audio(
                from_phone=from_phone,
                recipient=recipient,
                link=link,
                tenant_id=tenant_id,
                channel_id=channel_id,
                context_message_id=context,
            )
        if kind == "video":
            return await adapter.send_video(
                from_phone=from_phone,
                recipient=recipient,
                link=link,
                caption=caption,
                tenant_id=tenant_id,
                channel_id=channel_id,
                context_message_id=context,
            )
        if kind == "document":
            return await adapter.send_document(
                from_phone=from_phone,
                recipient=recipient,
                link=link,
                filename=msg.media_filename,
                caption=caption,
                tenant_id=tenant_id,
                channel_id=channel_id,
                context_message_id=context,
            )
        # Sticker / location / contacts: location and contacts live in
        # tool_calls as structured JSON; sticker reuses send_image with
        # the sticker URL once Cloud API exposes a separate endpoint
        # (it doesn't as of 2026). Fall through to text.

    # 3) Plain text. ``send_text`` already accepts ``context_message_id``.
    return await adapter.send_text(
        from_phone=from_phone,
        recipient=recipient,
        text=msg.content,
        tenant_id=tenant_id,
        channel_id=channel_id,
        context_message_id=context,
    )


async def _maybe_flag_meta_reauth(
    *,
    session: AsyncSession,
    exc: Exception,
    tenant_id: uuid.UUID,
) -> None:
    """If ``exc`` is a Meta token-invalidation, flip the tenant's Meta
    credentials to ``needs_reauth``. Best-effort: a failure here must not
    mask the original send failure being classified by the caller."""
    from nexus_channels.whatsapp_meta.credentials import MetaCredentialsRepository
    from nexus_channels.whatsapp_meta.exceptions import TokenInvalidatedError

    if not isinstance(exc, TokenInvalidatedError):
        return
    try:
        await MetaCredentialsRepository(session).mark_reauth_needed()
        log.warning(
            "outbound.dispatcher.meta_reauth_flagged",
            tenant_id=str(tenant_id),
            code=getattr(exc, "code", None),
        )
    except Exception as flag_exc:
        log.error(
            "outbound.dispatcher.meta_reauth_flag_failed",
            tenant_id=str(tenant_id),
            error=str(flag_exc),
        )


async def _handle_send_exception(
    *,
    session: AsyncSession,
    msg: Message,
    exc: Exception,
    tenant_id: uuid.UUID,
) -> None:
    """Classify and persist the failure. Decides retry vs no-retry on
    Meta Cloud API error codes."""
    error_str = f"{type(exc).__name__}: {exc}"[:500]
    msg.attempts += 1
    msg.last_error = error_str
    status_code = int(getattr(exc, "status_code", -1) or 0)
    meta_code = _extract_meta_code(exc)

    # Meta token invalidation (OAuthException 190/463/467). The BISUAT is
    # dead — flag the tenant's credentials ``needs_reauth`` so the operator
    # can re-run Embedded Signup instead of the dispatcher silently failing
    # every send forever. We're already inside the tenant-scoped session, so
    # the repo writes the right row under RLS.
    await _maybe_flag_meta_reauth(session=session, exc=exc, tenant_id=tenant_id)

    no_retry = False
    if meta_code in _NO_RETRY_CODES or any(meta_code.startswith(p) for p in _NO_RETRY_PREFIXES):
        no_retry = True
    elif 400 <= status_code < 500 and status_code not in {408, 429}:
        # 4xx other than timeouts and rate limits is a contract failure;
        # retrying would only burn attempts. 408/429 retry per the
        # historical behaviour (rate-limit backoff handled elsewhere).
        no_retry = True

    # Burst tracker for sustained 5xx storms (transport / upstream outage).
    if status_code == 0 or 500 <= status_code <= 599:
        from nexus_worker.streams.burst_tracker import get_default_tracker

        await get_default_tracker().record_failure_and_maybe_audit(
            tenant_id,
            status_code,
            error_message=msg.last_error or "",
        )

    if no_retry:
        msg.status = MessageStatus.FAILED
        msg.failed_at = datetime.now(UTC)
        msg.failure_code = meta_code or str(status_code)
        log.warning(
            "outbound.dispatcher.permanent_failure_no_retry",
            tenant_id=str(tenant_id),
            message_id=str(msg.id),
            status_code=status_code,
            meta_code=meta_code,
            error=msg.last_error,
        )
        return

    if msg.attempts >= MAX_ATTEMPTS:
        msg.status = MessageStatus.FAILED
        msg.failed_at = datetime.now(UTC)
        msg.failure_code = meta_code or str(status_code) or "exhausted_retries"
        log.warning(
            "outbound.dispatcher.permanent_failure",
            tenant_id=str(tenant_id),
            message_id=str(msg.id),
            attempts=msg.attempts,
            error=msg.last_error,
        )
    else:
        log.info(
            "outbound.dispatcher.retry",
            tenant_id=str(tenant_id),
            message_id=str(msg.id),
            attempts=msg.attempts,
            error=msg.last_error,
        )


def _extract_meta_code(exc: Exception) -> str:
    """Parse the embedded Meta error code from a provider error.

    ``MetaAPIError`` exposes a structured ``.code`` (the Cloud API error
    code) which we use directly; we also parse a JSON ``.body`` defensively
    for transport-level errors that carry the payload verbatim. If neither
    is present, return empty string and the caller falls back to the HTTP
    status code (``_NO_RETRY_CODES``: 131026, 131047, 132xxx, …).
    """
    direct_code = getattr(exc, "code", None)
    if direct_code is not None:
        return str(direct_code)
    body = getattr(exc, "body", None)
    if not body:
        return ""
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return ""
    if not isinstance(data, dict):
        return ""
    err = data.get("error")
    if isinstance(err, dict):
        code = err.get("code")
        if code is not None:
            return str(code)
    # Some transports flatten the shape.
    code = data.get("error_code") or data.get("code")
    if code is not None:
        return str(code)
    return ""


def _ms_since(when: datetime) -> int | None:
    if when is None:
        return None
    delta = datetime.now(UTC) - when.astimezone(UTC) if when.tzinfo else None
    if delta is None:
        return None
    return int(delta.total_seconds() * 1000)


def _to_meta_interactive(
    payload: dict[str, Any],
    *,
    catalog_id: str | None = None,
    catalog_thumbnail: str | None = None,
) -> dict[str, object]:
    """Convert our ``response.send_interactive`` tool payload into a
    Meta Cloud API ``interactive`` block.

    Input shape (validated by ``SendInteractiveInput``):
        {body, header?, footer?, buttons|list|cta_url|products, context_message_id?}

    ``catalog_id`` (the tenant's Meta Commerce catalog, from the channel
    config) is required to serialise ``products`` into native
    ``product`` / ``product_list`` messages; it is injected server-side
    and never comes from the LLM.

    Output shape (Meta WhatsApp Cloud API):
        {type: "button"|"list"|"cta_url",
         body: {text}, header?: {type:"text", text}, footer?: {text},
         action: {...}}

    ``context_message_id`` is NOT included in the returned block — it
    travels alongside as a sibling argument on ``adapter.send_interactive``
    (or equivalently, on the ``context`` field of the outbound row).
    """
    body = str(payload.get("body") or "")
    block: dict[str, object] = {"body": {"text": body}}

    header = payload.get("header")
    if header:
        block["header"] = {"type": "text", "text": str(header)}
    footer = payload.get("footer")
    if footer:
        block["footer"] = {"text": str(footer)}

    if payload.get("buttons"):
        block["type"] = "button"
        block["action"] = {
            "buttons": [
                {
                    "type": "reply",
                    "reply": {"id": str(b["id"]), "title": str(b["title"])},
                }
                for b in payload["buttons"]
            ]
        }
        return block

    if payload.get("list"):
        lst = payload["list"]
        rows = []
        for r in lst["items"]:
            row: dict[str, object] = {
                "id": str(r["id"]),
                "title": str(r["title"]),
            }
            if r.get("description"):
                row["description"] = str(r["description"])
            rows.append(row)
        block["type"] = "list"
        block["action"] = {
            "button": str(lst["button"]),
            "sections": [{"title": "Opciones", "rows": rows}],
        }
        return block

    if payload.get("cta_url"):
        cta = payload["cta_url"]
        block["type"] = "cta_url"
        block["action"] = {
            "name": "cta_url",
            "parameters": {
                "display_text": str(cta["text"]),
                "url": str(cta["url"]),
            },
        }
        return block

    if payload.get("catalog"):
        # Native catalog message: a card with a "View catalog" button that
        # opens the store's full Meta catalog inside WhatsApp. Meta needs a
        # valid catalog item for the thumbnail; the catalog itself is the
        # one linked to the WABA (no catalog_id in this message type).
        block["type"] = "catalog_message"
        block.pop("header", None)  # catalog_message allows only body/footer/action
        action: dict[str, object] = {"name": "catalog_message"}
        if catalog_thumbnail:
            action["parameters"] = {
                "thumbnail_product_retailer_id": str(catalog_thumbnail)
            }
        block["action"] = action
        return block

    if payload.get("products"):
        product_ids = [str(p) for p in payload["products"] if str(p).strip()]
        if not catalog_id:
            raise ValueError(
                "product message requires a catalog_id on the channel "
                "(config.catalog_id) — none set; cannot send catalog cards"
            )
        if not product_ids:
            raise ValueError("products list is empty after cleaning")
        section_title = str(header or "Productos")[:24]
        if len(product_ids) == 1:
            # Single Product Message — Meta allows only body/footer/action
            # (no header). Drop any header the generic prefix added.
            block.pop("header", None)
            block["type"] = "product"
            block["action"] = {
                "catalog_id": str(catalog_id),
                "product_retailer_id": product_ids[0],
            }
        else:
            # Multi-Product Message — Meta requires a text header + sections.
            block["type"] = "product_list"
            block["header"] = {"type": "text", "text": str(header or "Productos")}
            block["action"] = {
                "catalog_id": str(catalog_id),
                "sections": [
                    {
                        "title": section_title,
                        "product_items": [{"product_retailer_id": pid} for pid in product_ids],
                    }
                ],
            }
        return block

    raise ValueError(
        "interactive_payload missing buttons / list / cta_url / products — "
        "tool validation failed earlier; refusing to send a malformed block"
    )
