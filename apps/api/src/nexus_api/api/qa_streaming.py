"""SSE runtime for the QA Playground (ADR-021, Fase 1).

This module owns the per-process registry of in-flight ``qa.runs`` and
the translator that turns LangGraph ``astream_events(version="v2")``
events into the SSE protocol the assistant-ui frontend consumes.

Architecture
------------

::

   POST /qa/threads/{id}/send
        │   start_run()
        ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │ RunHandle (in process memory, keyed by run_id)                   │
   │                                                                  │
   │   asyncio.Task driving pipeline.astream_events(version="v2")     │
   │      │                                                           │
   │      ├──► translator: LangGraph event → list[SSEEvent]           │
   │      │                                                           │
   │      ├──► buffer (ring-bounded 256 events, FIFO, seq-numbered)   │
   │      │                                                           │
   │      └──► live_q (asyncio.Queue for subscribers)                 │
   │                                                                  │
   └──────────────────────────────────────────────────────────────────┘
        ▲                                            ▲
   GET /qa/threads/{id}/stream?run_id&since_seq      │
        │   subscribe()                              │
        │                                            │
   DELETE /qa/runs/{run_id}   cancel()              ─┘

Important constraints
---------------------

- **Single process**. Run state is in-memory. Production deploys with
  one uvicorn worker per service container — fine for MVP. Resumability
  across worker restarts is NOT supported; the frontend falls back to
  ``GET /qa/threads/{id}/messages`` for history.

- **Bounded buffer**. Up to 256 events per run. Older events are
  dropped FIFO. A reconnect with ``since_seq`` that points before the
  oldest retained event gets a single ``resume.gap`` event and must
  refetch full history.

- **Cancel semantics**. ``cancel(run_id)`` calls ``Task.cancel()``.
  The driver coroutine catches ``CancelledError``, awaits
  ``on_complete`` (which marks the ``qa.runs`` row as ``cancelled``),
  then emits ``run.completed`` with status ``cancelled``. The in-flight
  LLM call is left to complete
  on its own (we don't have a way to cancel an in-flight Anthropic
  call from here without burning the connection); we just stop relaying
  its tokens to the client.

- **RLS**. The streaming endpoint validates ownership of ``run_id`` via
  ``qa.runs`` + RLS BEFORE subscribing. Once subscribed there is no
  further DB read — events come from the in-memory buffer/queue.

See ``features/qa-playground-streaming-implementation.md`` for the full
event catalogue.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

import structlog

log = structlog.get_logger(__name__)


# ── SSE protocol (data classes, no I/O) ──────────────────────────────────────


@dataclass(frozen=True)
class SSEEvent:
    """One SSE message ready to be serialised + written to the wire.

    ``seq`` is the per-run monotonic sequence number used by the
    resume-from-buffer mechanism. ``event`` is the SSE event name (the
    string after ``event: ``). ``data`` is a JSON-serialisable dict.
    """

    seq: int
    event: str
    data: dict[str, Any]

    def to_wire(self) -> str:
        """Render to the SSE wire format: ``event: <name>\\ndata: <json>\\n\\n``.

        Custom field ``id: <seq>`` so EventSource clients receive a
        ``lastEventId`` for free; the frontend can replay using that or
        the explicit ``since_seq`` query param.
        """
        payload = json.dumps(self.data, default=_json_default, separators=(",", ":"))
        return f"id: {self.seq}\nevent: {self.event}\ndata: {payload}\n\n"


def _json_default(value: object) -> object:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"{type(value).__name__} is not JSON serialisable")


# ── translator: LangGraph event → list[SSEEvent payloads] ────────────────────
#
# The translator is a stateful instance (it keeps a seq counter and
# message_id mapping). Each call to ``translate`` returns 0 or more
# (event_name, data) pairs which the orchestrator assigns sequence
# numbers to.


@dataclass
class _TranslatorState:
    """Mutable state the translator carries between LangGraph events."""

    # Message id currently being streamed by the chat model. LangGraph
    # uses the same chunk.id across all chunks of one assistant turn.
    current_message_id: str | None = None
    # Whether we've already emitted ``run.started`` (defensive — should
    # only be one).
    started: bool = False


PendingSSE = tuple[str, dict[str, Any]]
"""(event_name, data) before sequence assignment."""


def translate_event(event: dict[str, Any], state: _TranslatorState) -> list[PendingSSE]:
    """Map one LangGraph v2 event to zero-or-more pending SSE messages.

    Pure-ish: only mutates the passed-in ``state``. Easy to unit-test
    with hand-crafted dicts.

    The LangGraph v2 event envelope is:
      ``{"event": "on_chat_model_stream", "name": "...", "data": {...},
         "tags": [...], "metadata": {...}, "run_id": "..."}``

    Reference: https://python.langchain.com/docs/concepts/streaming/
    """
    ev = event.get("event")
    data = event.get("data") or {}

    if ev == "on_chat_model_stream":
        chunk = data.get("chunk")
        if chunk is None:
            return []
        # Track the message_id so multiple deltas glue together client-side.
        chunk_id = getattr(chunk, "id", None)
        if chunk_id is None and hasattr(chunk, "get"):
            chunk_id = chunk.get("id")
        if chunk_id:
            state.current_message_id = chunk_id
        text_content = _extract_text(chunk)
        reasoning = _extract_reasoning(chunk)
        out: list[PendingSSE] = []
        if text_content:
            out.append(
                (
                    "text.delta",
                    {"message_id": state.current_message_id, "text": text_content},
                )
            )
        if reasoning:
            out.append(
                (
                    "reasoning.delta",
                    {"message_id": state.current_message_id, "text": reasoning},
                )
            )
        return out

    if ev == "on_chat_model_end":
        # Usage metadata only available on the final AIMessage.
        out_msg = data.get("output")
        usage = _extract_usage(out_msg)
        if usage:
            return [("cost.updated", usage)]
        return []

    if ev == "on_custom_event":
        name = event.get("name") or ""
        payload = data if isinstance(data, dict) else {}
        if name == "audit.blocked":
            return [("audit.blocked", dict(payload))]
        if name == "tool.call.started":
            return [("tool.call.started", dict(payload))]
        if name == "tool.call.completed":
            return [("tool.call.completed", dict(payload))]
        # Unknown custom events get a generic envelope so the client can
        # ignore safely — no silent drop.
        return [(f"custom.{name}", dict(payload))]

    if ev == "on_chain_end":
        # The ``ucm_formatter`` node ends after producing the UCM. We
        # surface that fast so the bubble renders before run.completed.
        name = event.get("name")
        if name == "ucm_formatter":
            output = data.get("output") or {}
            ucm = output.get("ucm") if isinstance(output, dict) else None
            if ucm:
                return [
                    (
                        "ucm.final",
                        {
                            "message_id": state.current_message_id,
                            "ucm": ucm,
                            "intent": output.get("intent") if isinstance(output, dict) else None,
                        },
                    )
                ]
        return []

    # Many other on_* events fire (chain_start, retriever, etc.). We
    # ignore them; the SSE protocol only carries what the Playground UI
    # needs.
    return []


def _extract_text(chunk: Any) -> str:
    """Pull the user-visible text from an AIMessageChunk-like object."""
    content = getattr(chunk, "content", None)
    if content is None and hasattr(chunk, "get"):
        content = chunk.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Claude 4.6 returns content blocks: [{"type":"text","text":"..."}].
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return ""


def _extract_reasoning(chunk: Any) -> str:
    """Pull thinking/reasoning blocks (Claude 4.6) from an AIMessageChunk."""
    content = getattr(chunk, "content", None)
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") in {
                "thinking",
                "reasoning",
            }:
                parts.append(str(block.get("text") or block.get("thinking") or ""))
        if parts:
            return "".join(parts)
    # additional_kwargs.reasoning_content is the OpenAI o1-style channel.
    extra = getattr(chunk, "additional_kwargs", None)
    if isinstance(extra, dict):
        r = extra.get("reasoning_content")
        if isinstance(r, str):
            return r
    return ""


def _extract_usage(msg: Any) -> dict[str, Any]:
    """Pull token + cost numbers from an AIMessage's usage_metadata."""
    if msg is None:
        return {}
    usage = getattr(msg, "usage_metadata", None)
    if not isinstance(usage, dict):
        if hasattr(msg, "get"):
            usage = msg.get("usage_metadata")
        if not isinstance(usage, dict):
            return {}
    out: dict[str, Any] = {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
    }
    # ``model`` name often lives on ``response_metadata``.
    response_meta = getattr(msg, "response_metadata", None)
    if isinstance(response_meta, dict):
        out["model"] = response_meta.get("model_name") or response_meta.get("model")
    return out


# ── orchestrator: per-run lifecycle ──────────────────────────────────────────


BUFFER_MAX_EVENTS = 256
PING_INTERVAL_SECONDS = 15.0


@dataclass
class RunHandle:
    """In-memory state for one in-flight ``qa.runs`` row.

    ``buffer`` is a bounded deque used for resume-from-replay. Each
    subscriber gets its own ``asyncio.Queue`` for live tailing — that
    keeps slow consumers from blocking the driver, and a disconnecting
    client doesn't leave a stale queue forever (the driver enqueues
    sentinel ``None`` on completion and the subscriber drops out).
    """

    run_id: uuid.UUID
    thread_id: uuid.UUID
    operator_id: str
    started_at_monotonic: float
    task: asyncio.Task[None]
    buffer: deque[SSEEvent] = field(default_factory=lambda: deque(maxlen=BUFFER_MAX_EVENTS))
    live_queues: list[asyncio.Queue[SSEEvent | None]] = field(default_factory=list)
    seq: int = 0
    done: bool = False
    # The oldest seq still retained in ``buffer``. ``since_seq < min_seq``
    # → buffer rotated past, signal resume.gap.
    min_seq_in_buffer: int = 0
    # Cost accumulators (updated by the default driver as cost.updated
    # events flow through). Used by the on-completion DB writer to
    # finalise the qa.runs row.
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    # Final lifecycle outcome, set by ``_run_with_lifecycle`` once the
    # driver exits (or raises). ``None`` while running.
    final_status: str | None = None
    final_error: str | None = None


_runs: dict[uuid.UUID, RunHandle] = {}
_runs_lock = asyncio.Lock()
# How long we retain a finished RunHandle in memory so late reconnects can
# still drain the tail. Bigger than the SSE reconnect default (~3s) but
# small enough that long-finished runs don't pile up.
_RETENTION_SECONDS = 60.0


def _next_seq(handle: RunHandle) -> int:
    handle.seq += 1
    return handle.seq


def _push_event(handle: RunHandle, ev: SSEEvent) -> None:
    """Append to buffer + broadcast to all live subscribers."""
    if len(handle.buffer) == handle.buffer.maxlen:
        # About to evict — track the new minimum sequence retained.
        handle.min_seq_in_buffer = handle.buffer[0].seq + 1
    handle.buffer.append(ev)
    for q in handle.live_queues:
        # put_nowait — if a subscriber is slow we let the queue grow
        # unbounded for them. asyncio.Queue without maxsize is fine
        # because a single run produces O(hundreds) of events, capped
        # by the buffer maxlen anyway.
        try:
            q.put_nowait(ev)
        except Exception:
            log.warning("qa.streaming.subscriber_put_failed", run_id=str(handle.run_id))


async def start_run(
    *,
    run_id: uuid.UUID,
    thread_id: uuid.UUID,
    operator_id: str,
    driver: Driver,
    on_complete: OnComplete | None = None,
) -> RunHandle:
    """Register the run and spawn the driver task.

    ``driver`` is an async callable that, given the handle, drives
    ``astream_events`` and pushes events. We pass it as an injectable so
    tests can plug a fake driver without faking LangGraph internals.

    ``on_complete`` runs once after the driver exits (success, error or
    cancel) and is awaited BEFORE ``run.completed`` is pushed. It
    receives the handle with ``final_status`` and ``final_error``
    populated, so callers can commit the ``qa.runs`` row first. The SSE
    must not lie: a client that sees ``run.completed`` can trust the
    row is already finalised.
    """
    loop = asyncio.get_running_loop()
    # Build the task and the handle together, registering the handle
    # FIRST so the lifecycle coroutine can find it via ``_runs[run_id]``
    # immediately. To break the chicken-and-egg with the task ref, we
    # create a placeholder noop task and replace it before the
    # lifecycle coroutine even gets scheduled.
    placeholder: asyncio.Task[None] = loop.create_task(asyncio.sleep(0))
    handle = RunHandle(
        run_id=run_id,
        thread_id=thread_id,
        operator_id=operator_id,
        started_at_monotonic=time.monotonic(),
        task=placeholder,
    )
    async with _runs_lock:
        _runs[run_id] = handle
    handle.task = loop.create_task(
        _run_with_lifecycle(driver, run_id, on_complete),
        name=f"qa-run-{run_id}",
    )
    return handle


# A Driver is a coroutine that, given a RunHandle, pushes events into
# its buffer/queues until completion. Defined as a Protocol so tests can
# plug in a fake driver without depending on langgraph internals.


class Driver(Protocol):
    async def __call__(self, handle: RunHandle) -> None: ...


OnComplete = Callable[[RunHandle], Awaitable[None]]


async def _run_with_lifecycle(
    driver: Driver,
    run_id: uuid.UUID,
    on_complete: OnComplete | None = None,
) -> None:
    """Wrap a driver with start/completion/cancel lifecycle bookkeeping.

    Emits ``run.started`` first, runs the driver, awaits ``on_complete``
    (so the ``qa.runs`` row is committed), then emits ``run.completed``.
    Always signals subscribers via sentinel so they don't hang.
    """
    handle = _runs.get(run_id)
    if handle is None:
        return  # registration race — nothing we can do

    handle.buffer.append(
        SSEEvent(
            seq=_next_seq(handle),
            event="run.started",
            data={
                "run_id": str(handle.run_id),
                "thread_id": str(handle.thread_id),
                "started_at": time.time(),
            },
        )
    )
    # Re-broadcast to anyone already subscribed.
    for q in handle.live_queues:
        with contextlib.suppress(Exception):
            q.put_nowait(handle.buffer[-1])

    status: str = "completed"
    error: str | None = None
    try:
        await driver(handle)
    except asyncio.CancelledError:
        status = "cancelled"
        # Don't re-raise: we want the finally block to run the
        # on_complete hook and then emit the completion event before
        # the task is observed as cancelled. The task ends in DONE
        # state with no exception, which is fine — ``cancel()``
        # already signalled the intent.
    except Exception as exc:
        status = "error"
        error = str(exc)
        log.exception("qa.streaming.run_failed", run_id=str(run_id))
    finally:
        handle.final_status = status
        handle.final_error = error
        # Commit the qa.runs row (and any other on_complete work)
        # BEFORE the client can observe run.completed. A subscriber
        # that sees the SSE can trust the row is already closed.
        if on_complete is not None:
            try:
                await on_complete(handle)
            except Exception:
                log.exception("qa.streaming.on_complete_failed", run_id=str(run_id))
        completed = SSEEvent(
            seq=_next_seq(handle),
            event="run.completed",
            data={
                "run_id": str(handle.run_id),
                "ended_at": time.time(),
                "status": status,
                **({"error": error} if error else {}),
            },
        )
        handle.buffer.append(completed)
        for q in handle.live_queues:
            try:
                q.put_nowait(completed)
                # Sentinel so subscribers exit their generators.
                q.put_nowait(None)
            except Exception:
                pass
        handle.done = True
        # Schedule cleanup after the retention window.
        loop = asyncio.get_running_loop()
        loop.call_later(_RETENTION_SECONDS, _drop_run, run_id)


def _drop_run(run_id: uuid.UUID) -> None:
    """Remove a finished run from the in-memory registry."""
    _runs.pop(run_id, None)


def get_handle(run_id: uuid.UUID) -> RunHandle | None:
    """Look up an in-flight or recently-finished run."""
    return _runs.get(run_id)


async def cancel(run_id: uuid.UUID) -> bool:
    """Request cancellation. Returns True if the run existed and was alive."""
    handle = _runs.get(run_id)
    if handle is None or handle.done:
        return False
    handle.task.cancel()
    return True


# ── subscribe: async generator emitting wire-format strings ──────────────────


async def subscribe(
    run_id: uuid.UUID,
    *,
    since_seq: int = 0,
) -> AsyncIterator[str]:
    """Yield SSE wire-format strings for a run.

    Resume semantics:
      - If ``since_seq`` is 0 (initial connect): replay everything in
        the buffer, then live-tail.
      - If ``since_seq > 0`` and ``since_seq < min_seq_in_buffer``: emit
        a single ``resume.gap`` event so the client knows to refetch
        history, then continue live-tailing from current.
      - If ``since_seq >= last seq in buffer``: skip the replay, just
        live-tail.

    The generator exits when the run is done AND no more events are
    queued. A heartbeat ``ping`` is emitted every ``PING_INTERVAL_SECONDS``
    while waiting on the live queue so dead connections surface fast.
    """
    handle = _runs.get(run_id)
    if handle is None:
        # Synthesise a single resume.gap so the client falls back to
        # ``GET /qa/threads/{id}/messages``.
        yield SSEEvent(
            seq=0,
            event="resume.gap",
            data={"reason": "run_unknown_or_evicted"},
        ).to_wire()
        return

    q: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
    handle.live_queues.append(q)

    try:
        # 1. Replay from buffer.
        if handle.buffer:
            buf_min = handle.buffer[0].seq
            if since_seq > 0 and since_seq < buf_min:
                yield SSEEvent(
                    seq=0,
                    event="resume.gap",
                    data={
                        "reason": "buffer_overflow",
                        "since_seq": since_seq,
                        "available_from": buf_min,
                    },
                ).to_wire()
            for ev in list(handle.buffer):
                if ev.seq > since_seq:
                    yield ev.to_wire()

        if handle.done:
            # Drain anything the lifecycle pushed AFTER the snapshot above
            # (rare race; the put_nowait/sentinel sequence guards it).
            while not q.empty():
                drained = q.get_nowait()
                if drained is None:
                    return
                if drained.seq > since_seq:
                    yield drained.to_wire()
            return

        # 2. Live tail with heartbeat.
        while True:
            try:
                tailed: SSEEvent | None = await asyncio.wait_for(
                    q.get(), timeout=PING_INTERVAL_SECONDS
                )
            except TimeoutError:
                # No event in PING_INTERVAL — keep the connection warm
                # so reverse proxies don't close. Seq=0 so resume logic
                # ignores pings.
                yield SSEEvent(
                    seq=0,
                    event="ping",
                    data={"ts": time.time()},
                ).to_wire()
                continue
            if tailed is None:
                return
            yield tailed.to_wire()
    finally:
        with contextlib.suppress(ValueError):
            handle.live_queues.remove(q)


# ── default driver: pipeline.astream_events → translator → push ──────────────


async def default_pipeline_driver(
    *,
    pipeline: Any,
    state: dict[str, Any],
    config: dict[str, Any],
) -> Driver:
    """Build the canonical driver that uses ``pipeline.astream_events``.

    Factory pattern so the caller picks the pipeline once (lazy
    process-cached in qa.py) and the driver closes over it. The
    returned callable matches the ``Driver`` Protocol.
    """

    async def _driver(handle: RunHandle) -> None:
        translator_state = _TranslatorState()
        async for event in pipeline.astream_events(state, config=config, version="v2"):
            pending = translate_event(event, translator_state)
            for name, data in pending:
                if name == "cost.updated":
                    handle.total_input_tokens += int(data.get("input_tokens") or 0)
                    handle.total_output_tokens += int(data.get("output_tokens") or 0)
                _push_event(
                    handle,
                    SSEEvent(seq=_next_seq(handle), event=name, data=data),
                )

    return _driver
