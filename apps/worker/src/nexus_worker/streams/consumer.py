"""Redis Stream consumer — reads ``nexus:inbound`` and dispatches to the pipeline.

A consumer group lets multiple worker replicas share the work without dropping
messages (each entry is delivered exactly once across the group). The group is
created idempotently on first read.

Failures (WP-04): on exception during dispatch we LOG and DO NOT ack, so the
entry stays pending and gets redelivered — by this replica on restart, or by
another replica via the stream claimer (``claimer.py``, ``XAUTOCLAIM``).
After ``MAX_DELIVERY_ATTEMPTS`` failed deliveries the entry is moved to
``nexus:inbound:dlq`` and acked, so a poison message can't block its slot
forever while staying invisible.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from nexus_api.core.otel_metrics import record_turn, record_turn_error
from nexus_api.core.streams import xadd_capped
from opentelemetry import trace as otel_trace
from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError

from nexus_worker.observability.otel import TRACE_FIELDS, extract_trace_context, get_tracer
from nexus_worker.runtime.dispatcher import InboundEvent, process_inbound

log = structlog.get_logger(__name__)

# Inline retry for transient DB-connection errors. The managed Postgres / proxy
# drops connections (idle cutoff, restarts, network blips), surfacing as
# "the connection is closed" / "SSL error: unexpected eof while reading". Before
# this, such a failure left the entry pending forever — there is no reclaim
# loop wired yet, so a "pending" message is effectively lost and the customer
# never got a reply (barbersupply outage 2026-08-14). Retrying in-place with a
# fresh session lets the turn succeed once the connection recovers.
_MAX_DISPATCH_ATTEMPTS = 4
_DISPATCH_RETRY_BASE_DELAY = 0.5  # seconds; doubles each attempt (0.5, 1, 2)

# Substrings that identify a dropped/broken DB connection across asyncpg +
# SQLAlchemy wrapping. Matched case-insensitively against ``str(exc)``.
_TRANSIENT_DB_ERROR_SUBSTRINGS = (
    "connection is closed",
    "connection was closed",
    "server closed the connection",
    "terminating connection",
    "connection reset",
    "unexpected eof",
    "consuming input failed",
    "ssl error",
    "cannot perform operation: another operation is in progress",
)


def _is_transient_db_error(exc: BaseException) -> bool:
    """True when ``exc`` is a dropped/broken DB connection worth retrying.

    Uses SQLAlchemy's ``connection_invalidated`` flag (set when the driver
    connection died) and the driver exception types, with a message-substring
    fallback for cases the flag doesn't cover (raw asyncpg surfaced through
    other layers)."""
    if isinstance(exc, DBAPIError) and getattr(exc, "connection_invalidated", False):
        return True
    if isinstance(exc, (InterfaceError, OperationalError)):
        return True
    message = str(exc).lower()
    return any(sub in message for sub in _TRANSIENT_DB_ERROR_SUBSTRINGS)

# WP-04: after this many failed deliveries an entry is moved to the DLQ
# instead of retrying forever (V6 — poison messages used to sit in the PEL
# silently until someone noticed the conversation had died).
MAX_DELIVERY_ATTEMPTS = 5
DLQ_STREAM = "nexus:inbound:dlq"


async def _ensure_group(redis: Redis, stream: str, group: str) -> None:
    try:
        await redis.xgroup_create(stream, group, id="$", mkstream=True)
    except ResponseError as exc:
        # BUSYGROUP — already exists, nothing to do.
        if "BUSYGROUP" not in str(exc):
            raise


def _decode_fields(raw: dict[bytes | str, bytes | str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in raw.items():
        ks = k.decode() if isinstance(k, bytes) else k
        vs = v.decode() if isinstance(v, bytes) else v
        out[ks] = vs
    return out


def _to_event(fields: dict[str, str]) -> InboundEvent:
    # WP-01: ``traceparent``/``tracestate`` ride the entry for context
    # propagation; they are not part of the business payload.
    fields = {k: v for k, v in fields.items() if k not in TRACE_FIELDS}

    def _opt_int(name: str) -> int | None:
        value = fields.get(name)
        return int(value) if value is not None and value != "" else None

    def _opt_float(name: str) -> float | None:
        value = fields.get(name)
        return float(value) if value is not None and value != "" else None

    return InboundEvent(
        tenant_id=uuid.UUID(fields["tenant_id"]),
        channel_id=uuid.UUID(fields["channel_id"]),
        user_id=fields["user_id"],
        content=fields["content"],
        customer_name=fields.get("customer_name"),
        provider=fields.get("provider", "meta"),
        kind=fields.get("kind", "text"),
        provider_message_id=fields.get("provider_message_id"),
        media_kind=fields.get("media_kind"),
        media_provider_id=fields.get("media_provider_id"),
        media_s3_key=fields.get("media_s3_key"),
        media_mime=fields.get("media_mime"),
        media_size_bytes=_opt_int("media_size_bytes"),
        media_filename=fields.get("media_filename"),
        media_sha256=fields.get("media_sha256"),
        reaction_emoji=fields.get("reaction_emoji"),
        reaction_target_wamid=fields.get("reaction_target_wamid"),
        context_message_id=fields.get("context_message_id"),
        location_latitude=_opt_float("location_latitude"),
        location_longitude=_opt_float("location_longitude"),
        location_name=fields.get("location_name"),
        location_address=fields.get("location_address"),
    )


# WP-09: read batch size. Bigger batches amortise the XREADGROUP round-trip
# once the slots consume concurrently.
READ_BATCH = 64

# Per-slot queue bound: when a hot conversation fills its slot queue the
# reader blocks on put() — natural backpressure that keeps unacked entries
# in Redis (crash-safe) instead of piling them up in process memory.
SLOT_QUEUE_MAXSIZE = 8

_SLOT_SENTINEL: Any = object()


def slot_for(fields: dict[str, str], n_slots: int) -> int:
    """Partition key: crc32 of the canonical thread_id. Two customers of the
    same tenant land in different slots (progress in parallel); two messages
    of the same conversation always land in the same slot (strict order)."""
    from zlib import crc32

    from nexus_worker.runtime.thread_id import make_thread_id

    try:
        thread_id = make_thread_id(fields["tenant_id"], fields["channel_id"], fields["user_id"])
    except (KeyError, ValueError):
        # Malformed entries go to slot 0 where handle_entry acks them away.
        return 0
    return crc32(thread_id.encode()) % n_slots


async def run_inbound_consumer(
    redis: Redis,
    pipeline: Any,
    *,
    stream: str | None = None,
    streams: list[str] | tuple[str, ...] | None = None,
    group: str,
    consumer_name: str,
    block_ms: int = 5_000,
    stop: asyncio.Event | None = None,
    on_processed: Callable[[InboundEvent], Awaitable[None]] | None = None,
    slots: int | None = None,
    max_inflight: int | None = None,
) -> None:
    """WP-09: concurrent consumer partitioned by ``thread_id``.

    One reader task feeds ``slots`` FIFO queues; one worker per slot
    processes strictly in order. A global semaphore caps simultaneous turns
    per replica so concurrency can't exhaust the DB pool or provider quotas.
    Closes V1 — the previous strictly-serial loop capped the whole platform
    at ~10-14 turns/min.

    WP-10: reads a LIST of streams in one XREADGROUP (tier streams + the
    legacy one during the transition release). ``stream=`` remains accepted
    as the single-stream spelling.
    """
    if slots is None or max_inflight is None:
        from nexus_worker.config import get_worker_settings

        ws = get_worker_settings()
        slots = slots or ws.runner_slots
        max_inflight = max_inflight or ws.runner_max_inflight

    stream_list: tuple[str, ...] = tuple(streams or ())
    if stream is not None:
        stream_list = (stream, *stream_list)
    if not stream_list:
        raise ValueError("run_inbound_consumer needs at least one stream")

    for stream_name in stream_list:
        await _ensure_group(redis, stream_name, group)
    log.info(
        "consumer.start",
        streams=list(stream_list),
        group=group,
        consumer=consumer_name,
        slots=slots,
        max_inflight=max_inflight,
    )

    queues: list[asyncio.Queue[Any]] = [
        asyncio.Queue(maxsize=SLOT_QUEUE_MAXSIZE) for _ in range(slots)
    ]
    inflight = asyncio.Semaphore(max_inflight)

    async def _slot_worker(queue: asyncio.Queue[Any]) -> None:
        while True:
            item = await queue.get()
            if item is _SLOT_SENTINEL:
                return
            source_stream, entry_id, raw_fields = item
            try:
                async with inflight:
                    await handle_entry(
                        redis,
                        pipeline=pipeline,
                        stream=source_stream,
                        group=group,
                        entry_id=entry_id,
                        raw_fields=raw_fields,
                        on_processed=on_processed,
                    )
            except Exception as exc:  # handle_entry never raises; belt+braces
                log.error("consumer.slot_worker_failed", error=str(exc))

    workers = [
        asyncio.create_task(_slot_worker(queue), name=f"slot-{i}") for i, queue in enumerate(queues)
    ]

    read_spec = {s: ">" for s in stream_list}
    try:
        while stop is None or not stop.is_set():
            try:
                response = await redis.xreadgroup(
                    groupname=group,
                    consumername=consumer_name,
                    streams=read_spec,  # type: ignore[arg-type]
                    count=READ_BATCH,
                    block=block_ms,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("consumer.xreadgroup_failed", error=str(exc))
                await asyncio.sleep(1.0)
                continue

            if not response:
                # Yield explicitly: with a client whose blocking read
                # completes synchronously (fakeredis) this loop would
                # otherwise starve every other task on the loop.
                await asyncio.sleep(0.01)
                continue

            for stream_name, entries in response:
                source = stream_name.decode() if isinstance(stream_name, bytes) else stream_name
                for entry_id, raw_fields in entries:
                    decoded = _decode_fields(raw_fields)
                    await queues[slot_for(decoded, slots)].put((source, entry_id, raw_fields))
    finally:
        # Graceful drain: workers finish whatever is queued, then exit on
        # the sentinel. Anything not yet processed stays unacked in the PEL
        # and is redelivered (or reclaimed) — never lost.
        for queue in queues:
            await queue.put(_SLOT_SENTINEL)
        await asyncio.gather(*workers, return_exceptions=True)

    log.info("consumer.stopped", streams=list(stream_list), group=group)


async def _delivery_count(redis: Redis, stream: str, group: str, entry_id: str) -> int:
    """How many times this pending entry has been delivered. Falls back to 1
    (first attempt) when XPENDING fails — degrading to the pre-DLQ behaviour
    (retry) rather than dead-lettering on a probe error."""
    try:
        pending = await redis.xpending_range(stream, group, min=entry_id, max=entry_id, count=1)
    except Exception as exc:
        log.warning("consumer.xpending_failed", entry_id=entry_id, error=str(exc))
        return 1
    if not pending:
        return 1
    info = pending[0]
    count = info.get("times_delivered") if isinstance(info, dict) else None
    return int(count) if count else 1


async def _dead_letter(
    redis: Redis,
    *,
    stream: str,
    group: str,
    entry_id: str,
    fields: dict[str, str],
    error: str,
    attempts: int,
) -> None:
    """Move a poison entry to the DLQ and ack it so it stops blocking the PEL.

    The DLQ entry carries the full original payload plus diagnosis fields —
    an operator can replay it by re-publishing the original fields to the
    source stream once the bug is fixed.
    """
    dlq_fields = {
        **{k: v for k, v in fields.items() if k not in TRACE_FIELDS},
        "dlq_source_stream": stream,
        "dlq_source_entry_id": entry_id,
        "dlq_error": error[:500],
        "dlq_attempts": str(attempts),
    }
    await xadd_capped(redis, DLQ_STREAM, dlq_fields)
    await redis.xack(stream, group, entry_id)
    log.error(
        "consumer.dead_lettered",
        entry_id=entry_id,
        stream=stream,
        dlq=DLQ_STREAM,
        attempts=attempts,
        error=error,
    )


async def handle_entry(
    redis: Redis,
    *,
    pipeline: Any,
    stream: str,
    group: str,
    entry_id: bytes | str,
    raw_fields: dict[bytes | str, bytes | str],
    on_processed: Callable[[InboundEvent], Awaitable[None]] | None = None,
    max_attempts: int = MAX_DELIVERY_ATTEMPTS,
) -> bool:
    """Process one stream entry: dispatch, ack on success, dead-letter after
    ``max_attempts`` failed deliveries (WP-04). Shared by the consumer loop
    and the stream claimer so both paths have identical semantics.

    Returns True when the entry was acked (success, malformed or DLQ),
    False when it stays pending for retry.
    """
    entry_id_str = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
    fields = _decode_fields(raw_fields)
    try:
        event = _to_event(fields)
    except KeyError as exc:
        log.warning(
            "consumer.malformed_entry",
            entry_id=entry_id_str,
            missing=str(exc),
        )
        await redis.xack(stream, group, entry_id_str)
        return True
    # WP-01: the ``turn`` span is the worker half of the end-to-end trace.
    # ``extract_trace_context`` rebuilds the webhook's context from the entry
    # fields so this span joins that trace; entries without ``traceparent``
    # start fresh.
    with get_tracer().start_as_current_span(
        "turn",
        context=extract_trace_context(fields),
        kind=otel_trace.SpanKind.CONSUMER,
        attributes={
            "tenant_id": str(event.tenant_id),
            "channel_id": str(event.channel_id),
            "messaging.provider": event.provider,
            "messaging.destination.name": stream,
        },
    ) as turn_span:
        started = time.perf_counter()
        try:
            result = await process_inbound(event, pipeline=pipeline)
        except Exception as exc:
            record_turn_error(tenant_id=str(event.tenant_id), stage="dispatch")
            # WP-06: windowed error counter consumed by the platform watcher
            # (alert when a tenant crosses the burst threshold). Best-effort.
            with contextlib.suppress(Exception):
                window = int(time.time()) // 600
                err_key = f"nexus:alert:turn_errors:{event.tenant_id}:{window}"
                await redis.incr(err_key)
                await redis.expire(err_key, 1_200)
            turn_span.set_status(otel_trace.Status(otel_trace.StatusCode.ERROR, str(exc)))
            turn_span.record_exception(exc)
            attempts = await _delivery_count(redis, stream, group, entry_id_str)
            log.error(
                "consumer.dispatch_failed",
                entry_id=entry_id_str,
                tenant_id=str(event.tenant_id),
                attempts=attempts,
                error=str(exc),
            )
            if attempts >= max_attempts:
                # Poison entry: retrying forever blocks the PEL and hides
                # the failure (V6). Park it where an operator can see it.
                with contextlib.suppress(Exception):
                    await _dead_letter(
                        redis,
                        stream=stream,
                        group=group,
                        entry_id=entry_id_str,
                        fields=fields,
                        error=str(exc),
                        attempts=attempts,
                    )
                return True
            # Below the cap: don't ack — leave it pending for retry.
            return False
        # WP-05: the turn SLI, labelled with the routed intent so the panel
        # can split p95 by conversation type.
        record_turn(
            duration_ms=(time.perf_counter() - started) * 1000,
            tenant_id=str(event.tenant_id),
            intent=(result or {}).get("intent") if isinstance(result, dict) else None,
            channel=event.provider,
        )
    await redis.xack(stream, group, entry_id_str)
    if on_processed is not None:
        with contextlib.suppress(Exception):
            await on_processed(event)
    return True
