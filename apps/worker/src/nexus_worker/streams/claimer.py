"""Stream claimer (WP-04, plataforma v2 Fase 0) — closes V6.

A runner replica that dies mid-turn leaves its entries in the consumer
group's PEL, owned by a consumer name that will never read again. Before
this module nothing ever reclaimed them: the customer's message simply
vanished. The claimer runs ``XAUTOCLAIM`` periodically, takes ownership of
entries idle beyond ``min_idle_ms`` and pushes them through the exact same
``handle_entry`` path as the live consumer (same DLQ semantics, same turn
span, same ordering guarantees per delivery).

It also measures the backlog (XPENDING summary + age of the oldest pending
entry) on every tick and reports it through ``on_backlog`` — WP-06 wires
that callback to the operator alert channel; until then it logs at ERROR
when thresholds are exceeded.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from nexus_api.core.otel_metrics import set_queue_lag
from redis.asyncio import Redis

from nexus_worker.streams.consumer import handle_entry

log = structlog.get_logger(__name__)

# Entries idle beyond this are considered orphaned (their consumer died or
# is wedged). 120s > any sane turn duration (LLM timeouts cap a turn well
# below this), so we never steal an entry that is actively being processed.
DEFAULT_MIN_IDLE_MS = 120_000
DEFAULT_INTERVAL_S = 30.0

# Backlog thresholds (plan §WP-04): more pending entries than this, or an
# oldest entry pending longer than this, means consumers are not keeping up.
BACKLOG_COUNT_THRESHOLD = 100
BACKLOG_AGE_THRESHOLD_S = 300.0

BacklogHook = Callable[[int, float], Awaitable[None]]


async def _check_backlog(
    redis: Redis,
    *,
    stream: str,
    group: str,
    on_backlog: BacklogHook | None,
) -> None:
    """Measure PEL depth + oldest pending age; report when over threshold."""
    try:
        summary = await redis.xpending(stream, group)
    except Exception as exc:
        log.warning("claimer.xpending_failed", stream=stream, error=str(exc))
        return
    pending_count = int(summary.get("pending") or 0) if isinstance(summary, dict) else 0
    oldest_age_s = 0.0
    min_id = summary.get("min") if isinstance(summary, dict) else None
    if pending_count and min_id:
        min_id_str = min_id.decode() if isinstance(min_id, bytes) else str(min_id)
        with contextlib.suppress(ValueError, IndexError):
            entry_ms = int(min_id_str.split("-")[0])
            oldest_age_s = max(0.0, time.time() - entry_ms / 1000.0)
    # WP-05: feed the queue-lag observable gauges on every tick.
    set_queue_lag(stream, entries=pending_count, oldest_pending_s=oldest_age_s)
    if pending_count > BACKLOG_COUNT_THRESHOLD or oldest_age_s > BACKLOG_AGE_THRESHOLD_S:
        log.error(
            "claimer.backlog_over_threshold",
            stream=stream,
            pending=pending_count,
            oldest_age_s=round(oldest_age_s, 1),
        )
        if on_backlog is not None:
            with contextlib.suppress(Exception):
                await on_backlog(pending_count, oldest_age_s)


async def run_stream_claimer(
    redis: Redis,
    pipeline: Any,
    *,
    stream: str | None = None,
    streams: list[str] | tuple[str, ...] | None = None,
    group: str,
    consumer_name: str,
    min_idle_ms: int = DEFAULT_MIN_IDLE_MS,
    interval_s: float = DEFAULT_INTERVAL_S,
    stop: asyncio.Event | None = None,
    on_processed: Callable[..., Awaitable[None]] | None = None,
    on_backlog: BacklogHook | None = None,
) -> None:
    stream_list: tuple[str, ...] = tuple(streams or ())
    if stream is not None:
        stream_list = (stream, *stream_list)
    if not stream_list:
        raise ValueError("run_stream_claimer needs at least one stream")
    log.info(
        "claimer.start",
        streams=list(stream_list),
        group=group,
        consumer=consumer_name,
        min_idle_ms=min_idle_ms,
    )
    while stop is None or not stop.is_set():
        for stream_name in stream_list:
            try:
                await claim_once(
                    redis,
                    pipeline,
                    stream=stream_name,
                    group=group,
                    consumer_name=consumer_name,
                    min_idle_ms=min_idle_ms,
                    on_processed=on_processed,
                )
                await _check_backlog(
                    redis, stream=stream_name, group=group, on_backlog=on_backlog
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("claimer.tick_failed", stream=stream_name, error=str(exc))
        if stop is None:
            await asyncio.sleep(interval_s)
        else:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=interval_s)
    log.info("claimer.stopped", streams=list(stream_list))


async def claim_once(
    redis: Redis,
    pipeline: Any,
    *,
    stream: str,
    group: str,
    consumer_name: str,
    min_idle_ms: int = DEFAULT_MIN_IDLE_MS,
    on_processed: Callable[..., Awaitable[None]] | None = None,
) -> int:
    """One XAUTOCLAIM sweep. Returns how many entries were reclaimed.

    Cursor-based: XAUTOCLAIM returns the next start id; ``0-0`` means the
    scan wrapped. Reclaimed entries flow through ``handle_entry`` — a
    reclaim IS a delivery, so the DLQ attempt-cap counts it like any other.
    """
    reclaimed = 0
    start_id: bytes | str = "0-0"
    while True:
        reply = await redis.xautoclaim(
            stream,
            group,
            consumer_name,
            min_idle_time=min_idle_ms,
            start_id=start_id,
            count=32,
        )
        # redis-py returns [next_start_id, entries] (+ deleted ids on Redis 7).
        next_id, entries = reply[0], reply[1]
        for entry_id, raw_fields in entries:
            # XAUTOCLAIM can surface tombstones (entry trimmed away) as None
            # fields on some server versions — skip them; they are already gone.
            if raw_fields is None:
                continue
            reclaimed += 1
            log.info(
                "claimer.reclaimed",
                stream=stream,
                entry_id=entry_id.decode() if isinstance(entry_id, bytes) else entry_id,
            )
            await handle_entry(
                redis,
                pipeline=pipeline,
                stream=stream,
                group=group,
                entry_id=entry_id,
                raw_fields=raw_fields,
                on_processed=on_processed,
            )
        next_id_str = next_id.decode() if isinstance(next_id, bytes) else str(next_id)
        if not entries or next_id_str == "0-0":
            return reclaimed
        start_id = next_id_str
