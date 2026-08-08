"""Redis Stream consumer — reads ``nexus:inbound`` and dispatches to the pipeline.

A consumer group lets multiple worker replicas share the work without dropping
messages (each entry is delivered exactly once across the group). The group is
created idempotently on first read.

Failures: on exception during dispatch we LOG and DO NOT ack, so the entry
becomes pending and a retry kicks in via ``XCLAIM`` later. Block H wires the
DLQ + alerting; for block C we just log loudly so failures show up in dev.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
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


async def run_inbound_consumer(
    redis: Redis,
    pipeline: Any,
    *,
    stream: str,
    group: str,
    consumer_name: str,
    block_ms: int = 5_000,
    stop: asyncio.Event | None = None,
    on_processed: Callable[[InboundEvent], Awaitable[None]] | None = None,
) -> None:
    await _ensure_group(redis, stream, group)
    log.info("consumer.start", stream=stream, group=group, consumer=consumer_name)

    while stop is None or not stop.is_set():
        try:
            response = await redis.xreadgroup(
                groupname=group,
                consumername=consumer_name,
                streams={stream: ">"},
                count=10,
                block=block_ms,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("consumer.xreadgroup_failed", error=str(exc))
            await asyncio.sleep(1.0)
            continue

        if not response:
            continue

        for _stream_name, entries in response:
            for entry_id, raw_fields in entries:
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
                    continue
                # WP-01: the ``turn`` span is the worker half of the
                # end-to-end trace. ``extract_trace_context`` rebuilds the
                # webhook's context from the entry fields so this span joins
                # that trace; entries without ``traceparent`` start fresh.
                dispatched = False
                for attempt in range(1, _MAX_DISPATCH_ATTEMPTS + 1):
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
                        try:
                            await process_inbound(event, pipeline=pipeline)
                            dispatched = True
                            break
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:
                            turn_span.set_status(
                                otel_trace.Status(otel_trace.StatusCode.ERROR, str(exc))
                            )
                            turn_span.record_exception(exc)
                            transient = _is_transient_db_error(exc)
                            if transient and attempt < _MAX_DISPATCH_ATTEMPTS:
                                delay = _DISPATCH_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                                log.warning(
                                    "consumer.dispatch_retry",
                                    entry_id=entry_id_str,
                                    tenant_id=str(event.tenant_id),
                                    attempt=attempt,
                                    delay=round(delay, 2),
                                    error=str(exc),
                                )
                                await asyncio.sleep(delay)
                                continue
                            log.error(
                                "consumer.dispatch_failed",
                                entry_id=entry_id_str,
                                tenant_id=str(event.tenant_id),
                                error=str(exc),
                                attempts=attempt,
                                transient=transient,
                            )
                            break
                if not dispatched:
                    log.error(
                            "consumer.dispatch_failed",
                            entry_id=entry_id_str,
                            tenant_id=str(event.tenant_id),
                            error=str(exc),
                        )
                        # Don't ack — leave it pending for retry.
                    continue
                await redis.xack(stream, group, entry_id_str)
                if on_processed is not None:
                    with contextlib.suppress(Exception):
                        await on_processed(event)

    log.info("consumer.stopped", stream=stream, group=group)
