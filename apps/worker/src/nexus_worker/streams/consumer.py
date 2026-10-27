"""Redis Stream consumer — reads ``nexus:inbound`` and dispatches to the pipeline.

A consumer group lets multiple worker replicas share the work without dropping
messages (each entry is delivered exactly once across the group). The group is
created idempotently on first read.

Spec 047, ola 1 (requisitos 1.1, 1.2 y 2.1; research D43). Each entry is
**saved first** and only then acked: ``accept_inbound`` writes the message
before any gate looks at it, and the entry is acked once it is in the base —
never before. Then the entry schedules the turn of its conversation in the
deferred queue (``runtime/turns.py``) at ``+coalesce_window_ms``; every new
message pushes it back, so a burst of bubbles is one turn. The turn poller
(``_TurnRunner``) picks due turns up and runs them, one at a time per
conversation across replicas (the lease in ``turn_effects``). A window of 0
keeps the old shape: the turn runs inline, right after saving.

Failures (WP-04): on exception while saving we LOG and DO NOT ack, so the
entry stays pending and gets redelivered — by this replica on restart, or by
another replica via the stream claimer (``claimer.py``, ``XAUTOCLAIM``).
After ``MAX_DELIVERY_ATTEMPTS`` failed deliveries the entry is moved to
``nexus:inbound:dlq`` and acked, so a poison message can't block its slot
forever while staying invisible. A turn that fails after the entry was acked is
retried from the deferred queue with the same ``turn_id``.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, cast

import structlog
from nexus_api.core.otel_metrics import record_turn, record_turn_error
from nexus_api.core.streams import xadd_capped
from opentelemetry import trace as otel_trace
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from nexus_worker.observability.otel import TRACE_FIELDS, extract_trace_context, get_tracer
from nexus_worker.runtime import turns
from nexus_worker.runtime.dispatcher import (
    InboundEvent,
    accept_inbound,
    process_inbound,
    run_turn,
)

log = structlog.get_logger(__name__)

# WP-04: after this many failed deliveries an entry is moved to the DLQ
# instead of retrying forever (V6 — poison messages used to sit in the PEL
# silently until someone noticed the conversation had died).
MAX_DELIVERY_ATTEMPTS = 5
DLQ_STREAM = "nexus:inbound:dlq"

#: How often the turn poller looks for due turns, and the most it picks up
#: per look. Far below the 3 s window: the extra latency is a rounding error.
TURN_POLL_S = 0.25
TURN_POLL_BATCH = 32
#: A turn that failed is retried after ``2**attempt`` seconds, capped.
MAX_RETRY_BACKOFF_S = 60


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
        # Lo pone el webhook cuando toca acuse de lectura; su ausencia
        # significa "no marcar" (canal send-only, remitente no admin en
        # línea de coexistencia, o una entrada anterior a este cambio).
        mark_read=fields.get("mark_read") == "1",
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


def _window_from_settings() -> int:
    from nexus_worker.config import get_worker_settings

    return get_worker_settings().runner_coalesce_window_ms


# ── El turno diferido ────────────────────────────────────────────────────────


async def _bump_turn_errors(redis: Redis, tenant_id: uuid.UUID) -> None:
    """WP-06: windowed error counter consumed by the platform watcher."""
    with contextlib.suppress(Exception):
        window = int(time.time()) // 600
        err_key = f"nexus:alert:turn_errors:{tenant_id}:{window}"
        await redis.incr(err_key)
        await redis.expire(err_key, 1_200)


async def execute_due_turn(
    redis: Redis,
    *,
    queue: str,
    member: str,
    token: int,
    pipeline: Any,
    window_ms: int,
    now_ms: int | None = None,
) -> dict[str, Any] | None:
    """Corre un turno recogido de la cola y la deja como toca:

    - terminó (contestó o una puerta lo paró) → fuera de la cola, salvo que un
      mensaje nuevo lo haya vuelto a programar mientras corría;
    - la conversación estaba ocupada → otra vez tras la ventana;
    - falló → otra vez tras ``2**intento`` segundos, con el mismo ``turn_id``.
    Nunca lanza: el poller no puede caerse por un turno.
    """
    tenant_id, conversation_id = turns.parse_member(member)
    now = int(time.time() * 1000) if now_ms is None else now_ms
    started = time.perf_counter()
    with get_tracer().start_as_current_span(
        "turn",
        kind=otel_trace.SpanKind.CONSUMER,
        attributes={"tenant_id": str(tenant_id), "conversation_id": str(conversation_id)},
    ) as span:
        try:
            result = await run_turn(
                tenant_id=tenant_id, conversation_id=conversation_id, pipeline=pipeline
            )
        except turns.TurnRetry as exc:
            record_turn_error(tenant_id=str(tenant_id), stage="turn")
            await _bump_turn_errors(redis, tenant_id)
            span.set_status(otel_trace.Status(otel_trace.StatusCode.ERROR, exc.error))
            backoff_ms = min(2**exc.attempt, MAX_RETRY_BACKOFF_S) * 1000
            await turns.reschedule(redis, queue=queue, member=member, at_ms=now + backoff_ms)
            log.error(
                "consumer.turn_failed",
                tenant_id=str(tenant_id),
                conversation_id=str(conversation_id),
                turn_id=str(exc.turn_id),
                attempt=exc.attempt,
                error=exc.error,
            )
            return None
        except Exception as exc:
            # Could not even claim (the base is down): try again shortly.
            record_turn_error(tenant_id=str(tenant_id), stage="claim")
            span.set_status(otel_trace.Status(otel_trace.StatusCode.ERROR, str(exc)))
            await turns.reschedule(redis, queue=queue, member=member, at_ms=now + window_ms)
            log.error(
                "consumer.turn_claim_failed",
                tenant_id=str(tenant_id),
                conversation_id=str(conversation_id),
                error=str(exc),
            )
            return None
    if result.get("turn") == "busy":
        # Requisito 1.2: one turn at a time. This message waits for the turn
        # that is running and goes into the next one.
        await turns.reschedule(redis, queue=queue, member=member, at_ms=now + window_ms)
        return result
    await turns.settle(redis, queue=queue, member=member, token=token)
    if result.get("turn") != "none":
        # WP-05: the turn SLI, labelled with the routed intent.
        record_turn(
            duration_ms=(time.perf_counter() - started) * 1000,
            tenant_id=str(tenant_id),
            intent=result.get("intent"),
            channel="meta",
        )
    return result


async def drain_due_turns(
    redis: Redis,
    *,
    queues: list[str] | tuple[str, ...],
    pipeline: Any,
    now_ms: int | None = None,
    limit: int = TURN_POLL_BATCH,
    window_ms: int | None = None,
) -> int:
    """Una pasada: recoge los turnos vencidos y los corre, en paralelo entre
    conversaciones. Devuelve cuántos corrió. Es lo que hace el poller en cada
    vuelta; separado para que las pruebas puedan ejercer exactamente una."""
    window = _window_from_settings() if window_ms is None else window_ms
    jobs: list[Awaitable[Any]] = []
    for queue in queues:
        members, token = await turns.pop_due(redis, queue=queue, limit=limit, now_ms=now_ms)
        for member in members:
            jobs.append(
                execute_due_turn(
                    redis,
                    queue=queue,
                    member=member,
                    token=token,
                    pipeline=pipeline,
                    window_ms=window,
                    now_ms=now_ms,
                )
            )
    if not jobs:
        return 0
    results = await asyncio.gather(*jobs)
    return sum(1 for r in results if r is not None and r.get("turn") not in {"busy", "none"})


class _TurnRunner:
    """El poller de la cola diferida: recoge lo vencido y lo corre en tareas,
    con el mismo tope de turnos simultáneos que el consumidor."""

    def __init__(
        self,
        redis: Redis,
        *,
        queues: tuple[str, ...],
        pipeline: Any,
        inflight: asyncio.Semaphore,
        capacity: int,
        window_ms: int,
    ) -> None:
        self.redis = redis
        self.queues = queues
        self.pipeline = pipeline
        self.inflight = inflight
        self.capacity = capacity
        self.window_ms = window_ms
        self.tasks: set[asyncio.Task[None]] = set()

    async def _one(self, queue: str, member: str, token: int) -> None:
        async with self.inflight:
            await execute_due_turn(
                self.redis,
                queue=queue,
                member=member,
                token=token,
                pipeline=self.pipeline,
                window_ms=self.window_ms,
            )

    async def run(self, stop: asyncio.Event | None) -> None:
        while stop is None or not stop.is_set():
            try:
                for queue in self.queues:
                    # Never pick up more than can run now: a picked-up turn
                    # waits parked, and parked is not lost but it is slower.
                    free = self.capacity - len(self.tasks)
                    if free <= 0:
                        break
                    members, token = await turns.pop_due(
                        self.redis, queue=queue, limit=min(free, TURN_POLL_BATCH)
                    )
                    for member in members:
                        task = asyncio.create_task(self._one(queue, member, token))
                        self.tasks.add(task)
                        task.add_done_callback(self.tasks.discard)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("consumer.turn_poll_failed", error=str(exc))
            await asyncio.sleep(TURN_POLL_S)

    async def drain(self) -> None:
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)


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
    coalesce_window_ms: int | None = None,
) -> None:
    """WP-09: concurrent consumer partitioned by ``thread_id``.

    One reader task feeds ``slots`` FIFO queues; one worker per slot
    processes strictly in order. A global semaphore caps simultaneous turns
    per replica so concurrency can't exhaust the DB pool or provider quotas.

    WP-10: reads a LIST of streams in one XREADGROUP (tier streams + the
    legacy one during the transition release). ``stream=`` remains accepted
    as the single-stream spelling.

    Spec 047: with a coalescing window the slots only save and schedule — fast
    — and the turn poller runs the turns. Its queues are this consumer's
    streams', so a priority tenant's turn stays in the priority pool.
    """
    if slots is None or max_inflight is None:
        from nexus_worker.config import get_worker_settings

        ws = get_worker_settings()
        slots = slots or ws.runner_slots
        max_inflight = max_inflight or ws.runner_max_inflight
    if coalesce_window_ms is None:
        coalesce_window_ms = _window_from_settings()

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
        coalesce_window_ms=coalesce_window_ms,
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
                        coalesce_window_ms=coalesce_window_ms,
                    )
            except Exception as exc:  # handle_entry never raises; belt+braces
                log.error("consumer.slot_worker_failed", error=str(exc))

    workers = [
        asyncio.create_task(_slot_worker(queue), name=f"slot-{i}") for i, queue in enumerate(queues)
    ]
    # The deferred turns of this consumer's streams. Runs also with a window
    # of 0: an inline turn that found its conversation busy is scheduled here.
    runner = _TurnRunner(
        redis,
        queues=tuple(turns.due_queue(s) for s in stream_list),
        pipeline=pipeline,
        inflight=inflight,
        capacity=max_inflight,
        window_ms=max(coalesce_window_ms, 1000),
    )
    poller = asyncio.create_task(runner.run(stop), name="turn-poller")

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

            # stubs de redis >=8 tipan xreadgroup como unión amplia; el shape
            # real con decode_responses off es list[(stream, [(id, fields)])].
            typed_response = cast("list[tuple[Any, list[tuple[Any, Any]]]]", response)
            for stream_name, entries in typed_response:
                source = stream_name.decode() if isinstance(stream_name, bytes) else stream_name
                for entry_id, raw_fields in entries:
                    decoded = _decode_fields(raw_fields)
                    await queues[slot_for(decoded, slots)].put((source, entry_id, raw_fields))
    finally:
        # Graceful drain: workers finish whatever is queued, then exit on
        # the sentinel. Anything not yet processed stays unacked in the PEL
        # and is redelivered (or reclaimed) — never lost. A turn picked up
        # and not finished stays parked in its queue and comes due again.
        for queue in queues:
            await queue.put(_SLOT_SENTINEL)
        await asyncio.gather(*workers, return_exceptions=True)
        poller.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await poller
        await runner.drain()

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


async def _save_and_schedule(
    redis: Redis, event: InboundEvent, *, stream: str, window_ms: int
) -> dict[str, Any]:
    """Spec 047: guardar, y programar el turno de la conversación."""
    accepted = await accept_inbound(event)
    if accepted.skipped is not None or accepted.conversation_id is None:
        return {"skipped": accepted.skipped or "tenant_unknown"}
    await turns.schedule_turn(
        redis,
        queue=turns.due_queue(stream),
        tenant_id=event.tenant_id,
        conversation_id=accepted.conversation_id,
        window_ms=window_ms,
    )
    return {
        "scheduled": True,
        "conversation_id": str(accepted.conversation_id),
        "inbound_message_id": str(accepted.message_id) if accepted.message_id else None,
    }


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
    coalesce_window_ms: int = 0,
) -> bool:
    """Process one stream entry: save it (and run or schedule its turn), ack
    on success, dead-letter after ``max_attempts`` failed deliveries (WP-04).
    Shared by the consumer loop and the stream claimer so both paths have
    identical semantics. A reclaimed entry (the claimer) runs its turn inline:
    its window passed long ago.

    Returns True when the entry was acked (saved, malformed or DLQ), False
    when it stays pending for retry. **It never acks an entry it did not save**
    (spec 047, requisito 2.1).
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
            if coalesce_window_ms > 0:
                result = await _save_and_schedule(
                    redis, event, stream=stream, window_ms=coalesce_window_ms
                )
            else:
                result = await process_inbound(event, pipeline=pipeline)
        except Exception as exc:
            record_turn_error(tenant_id=str(event.tenant_id), stage="dispatch")
            # WP-06: windowed error counter consumed by the platform watcher
            # (alert when a tenant crosses the burst threshold). Best-effort.
            await _bump_turn_errors(redis, event.tenant_id)
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
        result = result if isinstance(result, dict) else {}
        if result.get("turn") == "busy" and result.get("conversation_id"):
            # Inline turn, conversation busy: the message is saved without a
            # turn and goes into the next one, from the deferred queue.
            with contextlib.suppress(Exception):
                await turns.schedule_turn(
                    redis,
                    queue=turns.due_queue(stream),
                    tenant_id=event.tenant_id,
                    conversation_id=uuid.UUID(str(result["conversation_id"])),
                    window_ms=max(_window_from_settings(), 1000),
                )
        if not result.get("scheduled"):
            # WP-05: the turn SLI, labelled with the routed intent so the panel
            # can split p95 by conversation type.
            record_turn(
                duration_ms=(time.perf_counter() - started) * 1000,
                tenant_id=str(event.tenant_id),
                intent=result.get("intent"),
                channel=event.provider,
            )
    await redis.xack(stream, group, entry_id_str)
    if on_processed is not None:
        with contextlib.suppress(Exception):
            await on_processed(event)
    return True
