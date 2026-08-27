"""Unit tests for the in-memory streaming orchestrator (no DB, no langgraph).

We use a fake ``Driver`` that pushes a deterministic sequence of events
into the handle. This exercises ``start_run`` / ``subscribe`` / ``cancel``
without touching the real LangGraph pipeline.

Reference: ADR-021 Fase 1.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from nexus_api.api import qa_streaming
from nexus_api.api.qa_streaming import (
    BUFFER_MAX_EVENTS,
    PING_INTERVAL_SECONDS,
    RunHandle,
    SSEEvent,
    _next_seq,
    _push_event,
    cancel,
    start_run,
    subscribe,
)

pytestmark = pytest.mark.asyncio


def _parse_sse(wire: str) -> list[dict[str, str]]:
    """Parse the wire format into a list of ``{event, data, id}`` dicts."""
    events: list[dict[str, str]] = []
    blocks = [b for b in wire.split("\n\n") if b.strip()]
    for block in blocks:
        ev: dict[str, str] = {}
        for line in block.split("\n"):
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            ev[key.strip()] = val.lstrip()
        events.append(ev)
    return events


def _make_driver(payloads: list[tuple[str, dict[str, object]]]):
    """Build a Driver that pushes ``payloads`` then exits cleanly."""

    async def driver(handle: RunHandle) -> None:
        for name, data in payloads:
            _push_event(
                handle,
                SSEEvent(seq=_next_seq(handle), event=name, data=data),
            )
            await asyncio.sleep(0)  # let subscribers wake

    return driver


async def test_subscribe_replays_buffer_then_tails_live() -> None:
    """A subscriber that connects mid-run sees the existing buffer + the
    tail of new events emitted after subscription."""
    run_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    ready = asyncio.Event()
    pending = asyncio.Event()

    async def driver(handle: RunHandle) -> None:
        # Push three events synchronously, then signal the test to
        # subscribe, then push three more.
        for i in range(3):
            _push_event(
                handle,
                SSEEvent(seq=_next_seq(handle), event="text.delta", data={"text": f"a{i}"}),
            )
        ready.set()
        await pending.wait()
        for i in range(3):
            _push_event(
                handle,
                SSEEvent(seq=_next_seq(handle), event="text.delta", data={"text": f"b{i}"}),
            )

    await start_run(
        run_id=run_id,
        thread_id=thread_id,
        operator_id="op-1",
        driver=driver,
    )
    await ready.wait()

    received: list[str] = []

    async def consume() -> None:
        async for wire in subscribe(run_id):
            received.append(wire)

    consumer = asyncio.create_task(consume())
    # Give the consumer a tick to drain the buffer, then release the driver.
    await asyncio.sleep(0.05)
    pending.set()
    await consumer

    parsed = _parse_sse("".join(received))
    events_in_order = [p["event"] for p in parsed if p.get("event") not in {"ping"}]
    # run.started + 3 buffered text.delta + 3 live text.delta + run.completed
    assert events_in_order[0] == "run.started"
    assert events_in_order.count("text.delta") == 6
    assert events_in_order[-1] == "run.completed"
    statuses = [
        json.loads(p["data"])["status"] for p in parsed if p.get("event") == "run.completed"
    ]
    assert statuses == ["completed"]


async def test_subscribe_with_since_seq_skips_older_events() -> None:
    run_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    payloads = [("text.delta", {"text": str(i)}) for i in range(5)]
    await start_run(
        run_id=run_id,
        thread_id=thread_id,
        operator_id="op-1",
        driver=_make_driver(payloads),
    )
    # Wait for the driver to finish.
    handle = qa_streaming.get_handle(run_id)
    assert handle is not None
    await handle.task

    received: list[str] = []
    async for wire in subscribe(run_id, since_seq=4):
        received.append(wire)

    parsed = _parse_sse("".join(received))
    # since_seq=4 → skip seq 1..4 (run.started + 3 text.delta).
    # We get seq 5 (the 4th delta), seq 6 (the 5th delta), and the
    # run.completed event.
    event_seqs = [int(p["id"]) for p in parsed if p.get("id") and int(p["id"]) > 0]
    assert all(s > 4 for s in event_seqs)


async def test_buffer_overflow_emits_resume_gap() -> None:
    """A reconnect with since_seq pointing before the buffer minimum →
    one ``resume.gap`` event before the replay."""
    run_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    # Push more than BUFFER_MAX_EVENTS so the buffer rotates.
    payloads = [("text.delta", {"text": str(i)}) for i in range(BUFFER_MAX_EVENTS + 50)]
    await start_run(
        run_id=run_id,
        thread_id=thread_id,
        operator_id="op-1",
        driver=_make_driver(payloads),
    )
    handle = qa_streaming.get_handle(run_id)
    assert handle is not None
    await handle.task

    received: list[str] = []
    # since_seq=1 is below the oldest retained seq → expect resume.gap.
    async for wire in subscribe(run_id, since_seq=1):
        received.append(wire)

    parsed = _parse_sse("".join(received))
    event_names = [p["event"] for p in parsed]
    assert "resume.gap" in event_names
    # Order: resume.gap first, then the available replay.
    assert event_names[0] == "resume.gap"


async def test_subscribe_unknown_run_emits_resume_gap() -> None:
    """A subscribe for a run that doesn't exist → resume.gap with
    ``reason: run_unknown_or_evicted``."""
    received: list[str] = []
    async for wire in subscribe(uuid.uuid4()):
        received.append(wire)
    parsed = _parse_sse("".join(received))
    assert len(parsed) == 1
    assert parsed[0]["event"] == "resume.gap"
    data = json.loads(parsed[0]["data"])
    assert data["reason"] == "run_unknown_or_evicted"


async def test_cancel_marks_run_cancelled_and_completes() -> None:
    """``cancel()`` interrupts the driver and the lifecycle emits
    ``run.completed`` with status=cancelled."""
    run_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    driver_started = asyncio.Event()

    async def slow_driver(handle: RunHandle) -> None:
        driver_started.set()
        await asyncio.sleep(60)

    await start_run(
        run_id=run_id,
        thread_id=thread_id,
        operator_id="op-1",
        driver=slow_driver,
    )
    await driver_started.wait()

    received: list[str] = []

    async def consume() -> None:
        async for wire in subscribe(run_id):
            received.append(wire)

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0.02)
    assert await cancel(run_id) is True
    await consumer

    parsed = _parse_sse("".join(received))
    completion = [p for p in parsed if p.get("event") == "run.completed"]
    assert len(completion) == 1
    assert json.loads(completion[0]["data"])["status"] == "cancelled"


async def test_on_complete_callback_receives_handle() -> None:
    """The ``on_complete`` hook fires BEFORE ``run.completed`` with
    ``final_status`` and totals populated."""
    captured: dict[str, object] = {}

    async def on_complete(h: RunHandle) -> None:
        captured["status"] = h.final_status
        captured["error"] = h.final_error
        captured["input"] = h.total_input_tokens
        captured["output"] = h.total_output_tokens
        captured["completed_already"] = any(ev.event == "run.completed" for ev in h.buffer)

    async def driver(handle: RunHandle) -> None:
        # Push a cost.updated event by hand (the default driver does
        # this; here we drive directly to test the hook).
        handle.total_input_tokens += 100
        handle.total_output_tokens += 30

    run_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    await start_run(
        run_id=run_id,
        thread_id=thread_id,
        operator_id="op-1",
        driver=driver,
        on_complete=on_complete,
    )
    handle = qa_streaming.get_handle(run_id)
    assert handle is not None
    await handle.task

    assert captured["status"] == "completed"
    assert captured["error"] is None
    assert captured["input"] == 100
    assert captured["output"] == 30
    assert captured["completed_already"] is False
    assert any(ev.event == "run.completed" for ev in handle.buffer)


async def test_error_status_when_driver_raises() -> None:
    """A driver that raises → ``run.completed`` with status='error' and the
    exception message in ``error``."""

    async def driver(handle: RunHandle) -> None:
        raise RuntimeError("kaboom")

    run_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    await start_run(
        run_id=run_id,
        thread_id=thread_id,
        operator_id="op-1",
        driver=driver,
    )
    handle = qa_streaming.get_handle(run_id)
    assert handle is not None
    await handle.task

    received: list[str] = []
    async for wire in subscribe(run_id):
        received.append(wire)
    parsed = _parse_sse("".join(received))
    completion = next(p for p in parsed if p.get("event") == "run.completed")
    data = json.loads(completion["data"])
    assert data["status"] == "error"
    assert data["error"] == "kaboom"


async def test_ping_emitted_when_idle() -> None:
    """When the driver is idle for > PING_INTERVAL_SECONDS, the
    subscribe loop emits a ``ping`` heartbeat. We patch the interval
    down to keep the test fast."""
    run_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    idle_done = asyncio.Event()

    async def driver(handle: RunHandle) -> None:
        await idle_done.wait()

    # Monkey-patch the ping interval just for this test. The module
    # constant is read inside ``subscribe`` so the patch lands.
    import nexus_api.api.qa_streaming as mod

    original = mod.PING_INTERVAL_SECONDS
    mod.PING_INTERVAL_SECONDS = 0.05  # type: ignore[assignment]
    try:
        await start_run(
            run_id=run_id,
            thread_id=thread_id,
            operator_id="op-1",
            driver=driver,
        )

        received: list[str] = []

        async def consume() -> None:
            async for wire in subscribe(run_id):
                received.append(wire)
                if any("event: ping" in w for w in received):
                    idle_done.set()
                    return  # leave the live tail without waiting for completion

        consumer = asyncio.create_task(consume())
        await asyncio.wait_for(consumer, timeout=2.0)
        parsed = _parse_sse("".join(received))
        events = [p["event"] for p in parsed]
        assert "ping" in events
    finally:
        mod.PING_INTERVAL_SECONDS = original  # type: ignore[assignment]
        # Ensure the driver task completes so the next test isn't
        # racing against it.
        handle = qa_streaming.get_handle(run_id)
        if handle is not None:
            with contextlib_suppress():
                await asyncio.wait_for(handle.task, timeout=2.0)


def contextlib_suppress():  # tiny helper to avoid import boilerplate above
    import contextlib

    return contextlib.suppress(Exception)


async def test_ping_interval_default_is_reasonable() -> None:
    """Sanity check on the module constant. Stays low enough to detect
    dead connections but high enough that idle traffic is minimal."""
    assert 5 <= PING_INTERVAL_SECONDS <= 60
