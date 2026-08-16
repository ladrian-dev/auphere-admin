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
from nexus_api.core.otel_metrics import (
    ensure_outbound_gauges,
    record_meta_send_failure,
    record_outbound_delivery,
    set_outbound_backlog,
)
from nexus_api.core.redis_client import get_redis
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
from nexus_channels.base import ChannelCapabilityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_worker.metering.collector import record_channel_message, record_media_unit

if TYPE_CHECKING:
    from nexus_channels.base import SendResult

# Provider → ChannelAdapter. Every adapter exposes the same outbound method
# surface (send_text/template/interactive/image/audio/video/document/reaction)
# with identical keyword signatures, so the dispatcher treats them uniformly
# and only differs in *which* adapter it resolves per ``channels.provider``.
AdapterRegistry = Mapping[str, Any]

# Channel types the dispatcher knows how to drive. Anything else is parked
# ``failed`` rather than pushed at an adapter that may not implement the
# method — a channel with no transport is a config error, not a send error.
_DISPATCHABLE_CHANNEL_TYPES = frozenset({ChannelType.WHATSAPP, ChannelType.TIKTOK})

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
# TikTok Business Messaging error codes that are not worth retrying.
#
# These matter more than their Meta counterparts because **TikTok returns
# HTTP 200 on failure** — the generic "4xx is a contract error" branch below
# never fires for them, so an unlisted permanent failure would burn all three
# attempts on every send.
#
# - 40001/40100/40101/40102/40105 : authentication. The token is dead;
#   retrying with the same one cannot help. Handled here *and* flagged for
#   re-auth further down.
# - 40002/40003 : bad parameter — usually a conversation_id that expired out
#   of the 48h window, which no amount of retrying reopens.
# - 40016 : the conversation is closed or outside the messaging window.
_TIKTOK_NO_RETRY_CODES: frozenset[str] = frozenset(
    {"40001", "40002", "40003", "40016", "40100", "40101", "40102", "40105"}
)

_NO_RETRY_CODES = _NO_RETRY_CODES | _TIKTOK_NO_RETRY_CODES

# Numeric ranges expressed as prefixes; matches anything starting with these.
_NO_RETRY_PREFIXES: tuple[str, ...] = ("132",)  # all 132xxx template rejects


# WP-12 (D11): the dispatcher is notification-driven. The 0062 trigger emits
# ``pg_notify('nexus_outbound', tenant_id)`` per fresh pending outbound row;
# a safety sweep every 30 s covers notifications lost across reconnects and
# rows re-queued via UPDATE (retries), which the INSERT trigger doesn't see.
NOTIFY_CHANNEL = "nexus_outbound"
SWEEP_SECONDS = 30.0
# Tenants drained concurrently per wake-up. Each tenant's drain is serial
# internally (commit per message, well under Meta's per-WABA rate limits).
MAX_CONCURRENT_TENANT_DRAINS = 8


class OutboundWorkSet:
    """Tenants with (probable) pending work, fed by LISTEN or the sweep."""

    def __init__(self) -> None:
        self._tenants: set[uuid.UUID] = set()
        self._wakeup = asyncio.Event()

    def add(self, tenant_id: uuid.UUID) -> None:
        self._tenants.add(tenant_id)
        self._wakeup.set()

    def add_raw(self, payload: str) -> None:
        with contextlib.suppress(ValueError):
            self.add(uuid.UUID(payload))

    def pop_all(self) -> set[uuid.UUID]:
        drained = self._tenants
        self._tenants = set()
        self._wakeup.clear()
        return drained

    async def wait(self, timeout: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wakeup.wait(), timeout=timeout)


def _asyncpg_dsn() -> str:
    from nexus_api.config import get_settings

    url: str = get_settings().database_url
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _run_listener(work: OutboundWorkSet, stop: asyncio.Event) -> None:
    """Hold a dedicated LISTEN connection; feed the work set. Reconnects
    with backoff — the 30 s sweep covers anything missed while down."""
    import asyncpg

    while not stop.is_set():
        conn = None
        try:
            conn = await asyncpg.connect(_asyncpg_dsn())

            def _on_notify(_conn, _pid, _channel, payload):  # type: ignore[no-untyped-def]
                work.add_raw(payload)

            await conn.add_listener(NOTIFY_CHANNEL, _on_notify)
            log.info("outbound.listener.connected", channel=NOTIFY_CHANNEL)
            while not stop.is_set():
                # The connection delivers notifications via the callback; we
                # just keep it alive and probe it so a dead socket surfaces.
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=15.0)
                if not stop.is_set():
                    await conn.execute("SELECT 1")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("outbound.listener.reconnecting", error=str(exc))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=2.0)
        finally:
            if conn is not None:
                with contextlib.suppress(Exception):
                    await conn.close()
    log.info("outbound.listener.stopped")


async def run_outbound_dispatcher(
    *,
    adapters: AdapterRegistry,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,  # kept for signature compat (tests)
    batch_size: int = DEFAULT_BATCH_SIZE,
    sweep_seconds: float = SWEEP_SECONDS,
    work: OutboundWorkSet | None = None,
    listen: bool = True,
) -> None:
    """Background task. Returns when ``stop`` is set.

    ``adapters`` maps ``channels.provider`` (``"meta"``) to the matching
    :class:`ChannelAdapter`.

    WP-12: database cost is proportional to TRAFFIC, not to tenant count —
    the dispatcher only opens tenant-scoped transactions for tenants that
    notified work (or on the 30 s safety sweep, which still visits every
    active tenant to catch lost notifications and re-queued retries).
    ``work``/``listen`` are test seams: inject a work set and disable the
    real LISTEN connection.
    """
    log.info(
        "outbound.dispatcher.start",
        sweep_seconds=sweep_seconds,
        batch=batch_size,
        providers=sorted(adapters.keys()),
    )
    ensure_outbound_gauges()
    sm = get_sessionmaker()
    work = work if work is not None else OutboundWorkSet()
    listener_task = (
        asyncio.create_task(_run_listener(work, stop), name="outbound-listener") if listen else None
    )
    drain_limit = asyncio.Semaphore(MAX_CONCURRENT_TENANT_DRAINS)

    async def _drain_limited(tid: uuid.UUID) -> None:
        async with drain_limit:
            await _drain_tenant(sm, tid, adapters, batch_size)

    last_sweep = float("-inf")  # first iteration always sweeps
    try:
        while not stop.is_set():
            try:
                now = asyncio.get_running_loop().time()
                if now - last_sweep >= sweep_seconds:
                    last_sweep = now
                    tenant_ids = await _list_active_tenants(sm)
                    await _warn_on_undrained_tenants(sm, tenant_ids)
                    await _publish_outbound_backlog(sm)
                    for tid in tenant_ids:
                        work.add(tid)
                notified = work.pop_all()
                if notified:
                    await asyncio.gather(
                        *(_drain_limited(tid) for tid in notified),
                        return_exceptions=False,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("outbound.dispatcher.tick_failed", error=str(exc))
            # Wake on the next notification, or in time for the sweep.
            remaining = max(0.1, sweep_seconds - (asyncio.get_running_loop().time() - last_sweep))
            wait_task = asyncio.create_task(work.wait(remaining))
            stop_task = asyncio.create_task(stop.wait())
            _done, pending = await asyncio.wait(
                {wait_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            with contextlib.suppress(Exception):
                await asyncio.gather(*pending, return_exceptions=True)
    finally:
        if listener_task is not None:
            listener_task.cancel()
            with contextlib.suppress(Exception):
                await asyncio.gather(listener_task, return_exceptions=True)
    log.info("outbound.dispatcher.stopped")


async def _list_active_tenants(sm: sa.orm.sessionmaker) -> list[uuid.UUID]:  # type: ignore[type-arg]
    async with sm() as session:
        rows = await session.execute(
            sa.select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE)
        )
        return [row[0] for row in rows]


# One tick is 500ms, so this is roughly every five minutes.
_UNDRAINED_CHECK_EVERY_TICKS = 600


async def _warn_on_undrained_tenants(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
    active: list[uuid.UUID],
) -> None:
    """Warn about pending sends the loop above will never look at.

    The drain is driven by ``tenants.status = 'active'``. A tenant that is
    suspended, or was provisioned without ever being activated, still
    accepts ``POST /v1/messages/template`` — the API answers 202 and the
    row lands ``pending`` — but no tick ever selects it. From the caller's
    side that is indistinguishable from a delivered message, and from the
    dispatcher's side it is perfectly silent: the tenant simply is not in
    the loop.

    This session does not switch to ``nexus_app``, so it reads across
    tenants deliberately — it is a global operational count, and the only
    thing it reports is which tenant ids are stuck and how many rows.
    """
    async with sm() as session:
        rows = await session.execute(
            sa.select(Message.tenant_id, sa.func.count())
            .where(
                Message.direction == MessageDirection.OUTBOUND,
                Message.status == MessageStatus.PENDING,
                Message.tenant_id.not_in(active) if active else sa.true(),
            )
            .group_by(Message.tenant_id)
        )
        stuck = list(rows)
    if not stuck:
        return
    log.warning(
        "outbound.dispatcher.undrained_inactive_tenants",
        tenants={str(tid): count for tid, count in stuck},
        total=sum(count for _tid, count in stuck),
        hint=(
            "these tenants are not status='active', so the dispatcher never "
            "selects their pending rows — the API accepted the sends and "
            "nothing will ever deliver them"
        ),
    )


async def _publish_outbound_backlog(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Publish the outbound backlog gauges that egress autoscales on (WP-24).

    Deliberately GLOBAL (no tenant scoping, same reasoning as
    :func:`_warn_on_undrained_tenants`): what egress needs to know is how
    much work exists in total, and CloudWatch could not carry a per-tenant
    dimension at tenant scale anyway.

    The age is computed by the DATABASE (``now() - min(created_at)``)
    instead of in Python: ``created_at`` is generated server-side, so
    mixing it with the worker's clock would report drift as backlog.

    Cost: the query is a count + min over
    ``ix_messages_outbound_pending`` (0067), a partial index that only
    holds rows that are actually pending — normally a handful, even though
    ``messages`` is partitioned and holds millions. Without that index this
    would seq-scan EVERY partition every 30 s.

    Never raises: a metric must not stop the drain.
    """
    try:
        async with sm() as session:
            row = (
                await session.execute(
                    sa.select(
                        sa.func.count(),
                        sa.func.coalesce(
                            sa.func.extract(
                                "epoch", sa.func.now() - sa.func.min(Message.created_at)
                            ),
                            0,
                        ),
                    ).where(
                        Message.direction == MessageDirection.OUTBOUND,
                        Message.status == MessageStatus.PENDING,
                    )
                )
            ).one()
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("outbound.dispatcher.backlog_gauge_failed", error=str(exc))
        return
    pending, oldest_s = int(row[0]), max(0.0, float(row[1]))
    set_outbound_backlog(pending=pending, oldest_pending_s=oldest_s)
    if pending:
        log.info(
            "outbound.dispatcher.backlog", pending=pending, oldest_pending_s=round(oldest_s, 1)
        )


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
            # A campaign is a burst of template rows. Splitting the count
            # by kind is what tells an operator, at a glance, whether the
            # queue they are staring at is the campaign or ordinary agent
            # traffic that happens to be backed up behind it.
            templates=sum(1 for m in pending if m.template_payload),
            oldest_created_at=(
                pending[0].created_at.isoformat() if pending[0].created_at else None
            ),
            retries=sum(1 for m in pending if m.attempts),
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
    # Emitted before anything can go wrong, and carrying the caller's
    # idempotency key: this is the line that joins an n8n spreadsheet row
    # to a wamid. Without it the API says "queued" and the next event is
    # either a send three seconds later or silence, with no way to tell
    # which row the silence belongs to.
    log.info(
        "outbound.dispatcher.picked_up",
        tenant_id=str(tenant_id),
        message_id=str(msg.id),
        idempotency_key=msg.idempotency_key,
        template=(msg.template_payload or {}).get("name"),
        attempts=msg.attempts,
        queued_ms=_ms_since(msg.created_at),
        has_conversation=row is not None,
    )
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
    if channel_type not in _DISPATCHABLE_CHANNEL_TYPES:
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
    #
    # WhatsApp-only by construction: ``whatsapp_opt_outs`` is keyed by phone
    # number, and the STOP-keyword convention it encodes is a WhatsApp/SMS
    # norm with no TikTok equivalent (a TikTok user opts out by not replying,
    # which the 48h window enforces on its own). Running this query for a
    # TikTok channel would compare an ``open_id`` against a phone column —
    # never matching, but implying a protection that isn't there.
    opted_out = (
        await session.scalar(
            sa.select(WhatsAppOptOut.id).where(
                WhatsAppOptOut.channel_id == channel_id,
                WhatsAppOptOut.recipient_phone == recipient,
                WhatsAppOptOut.opted_in_at.is_(None),
            )
        )
        if channel_type == ChannelType.WHATSAPP
        else None
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
    # WP-05: outbound_delivery_ms — time from row creation to provider accept.
    if msg.latency_ms is not None:
        record_outbound_delivery(provider="meta", duration_ms=float(msg.latency_ms))
    # WP-17: un saliente aceptado por el proveedor es un ``channel.message``
    # facturable. Se emite aquí y no en el callback de estado porque aquí
    # es donde el envío ocurre de verdad; lo que el callback añade después
    # es el PRECIO de Meta, que hoy no se persiste (queda para WP-18/19).
    await record_channel_message(
        tenant_id=tenant_id,
        provider="meta",
        provider_message_id=msg.provider_message_id,
        conversation_id=msg.conversation_id,
    )
    # CP-23 (0083): an outbound attachment accepted by the provider is one
    # ``media.<kind>`` unit on top of the channel message.
    if msg.media_kind:
        await record_media_unit(
            tenant_id=tenant_id,
            kind=msg.media_kind,
            provider="meta",
            provider_message_id=msg.provider_message_id,
            conversation_id=msg.conversation_id,
        )
    log.info(
        "outbound.dispatcher.sent",
        tenant_id=str(tenant_id),
        message_id=str(msg.id),
        provider_message_id=result.provider_message_id,
        kind=(
            "template"
            if msg.template_payload
            else msg.media_kind or ("reaction" if msg.reaction_emoji else "text")
        ),
        template=(msg.template_payload or {}).get("name"),
        idempotency_key=msg.idempotency_key,
        attempts=msg.attempts,
        latency_ms=msg.latency_ms,
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
        # Variable *names* only, never their values: a reminder's body
        # carries the customer's name. The names are what actually breaks
        # (a {{nombre}}/name mismatch renders an empty placeholder or is
        # rejected outright), and they are safe to keep.
        body_params = (tp.get("params") or {}).get("body")
        log.info(
            "outbound.dispatcher.template_send",
            tenant_id=str(tenant_id),
            message_id=str(msg.id),
            template=tp.get("name"),
            language=tp.get("language", "es"),
            body_var_names=sorted(body_params) if isinstance(body_params, dict) else None,
            body_var_count=(len(body_params) if isinstance(body_params, (dict, list)) else 0),
            positional=isinstance(body_params, list),
            from_phone=from_phone,
        )
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


async def _maybe_flag_reauth(
    *,
    session: AsyncSession,
    exc: Exception,
    tenant_id: uuid.UUID,
) -> None:
    """If ``exc`` is a token-invalidation, flip that provider's credentials
    to ``needs_reauth``.

    Both providers land here because both can lose auth, but for different
    reasons: Meta's BISUAT is long-lived and dies when the business revokes
    it, whereas TikTok's token dies on a schedule and this path fires when
    even the refresh cron can no longer save it.

    Best-effort: a failure here must not mask the original send failure the
    caller is classifying.
    """
    from nexus_channels.tiktok_bm.exceptions import TikTokTokenInvalidatedError
    from nexus_channels.whatsapp_meta.exceptions import TokenInvalidatedError

    if isinstance(exc, TokenInvalidatedError):
        from nexus_channels.whatsapp_meta.credentials import MetaCredentialsRepository

        provider, repo = "meta", MetaCredentialsRepository(session)
    elif isinstance(exc, TikTokTokenInvalidatedError):
        from nexus_channels.tiktok_bm.credentials import TikTokCredentialsRepository

        provider, repo = "tiktok", TikTokCredentialsRepository(session)
    else:
        return

    try:
        await repo.mark_reauth_needed()
        log.warning(
            "outbound.dispatcher.reauth_flagged",
            tenant_id=str(tenant_id),
            provider=provider,
            code=getattr(exc, "code", None),
        )
    except Exception as flag_exc:
        log.error(
            "outbound.dispatcher.reauth_flag_failed",
            tenant_id=str(tenant_id),
            provider=provider,
            error=str(flag_exc),
        )


async def _count_failure_for_watcher(code: str) -> None:
    """WP-06: windowed per-code failure counter consumed by the platform
    watcher (alert when the same Meta error code repeats in a burst)."""
    import contextlib as _contextlib
    import time as _time

    with _contextlib.suppress(Exception):
        redis = get_redis()
        window = int(_time.time()) // 600
        key = f"nexus:alert:metafail:{code}:{window}"
        await redis.incr(key)
        await redis.expire(key, 1_200)


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

    # Token invalidation (Meta OAuthException 190/463/467, TikTok 401xx). The
    # credential is dead — flag ``needs_reauth`` so the operator can re-run
    # onboarding instead of the dispatcher silently failing every send
    # forever. We're already inside the tenant-scoped session, so the repo
    # writes the right row under RLS.
    await _maybe_flag_reauth(session=session, exc=exc, tenant_id=tenant_id)

    # A capability error is the channel saying "this can never work here" —
    # a TikTok template send, or a reply with no conversation to reply into.
    # Retrying is pure waste and it hides a real config problem behind three
    # identical failures.
    if isinstance(exc, ChannelCapabilityError):
        msg.status = MessageStatus.FAILED
        msg.failed_at = datetime.now(UTC)
        msg.failure_code = "unsupported_capability"
        log.warning(
            "outbound.dispatcher.unsupported_capability",
            tenant_id=str(tenant_id),
            message_id=str(msg.id),
            error=msg.last_error,
        )
        return

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
        record_meta_send_failure(code=msg.failure_code)
        await _count_failure_for_watcher(msg.failure_code)
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
        record_meta_send_failure(code=msg.failure_code)
        await _count_failure_for_watcher(msg.failure_code)
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
            action["parameters"] = {"thumbnail_product_retailer_id": str(catalog_thumbnail)}
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
