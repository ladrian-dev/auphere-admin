"""WP-01 (plataforma v2, Fase 0): the worker half of the end-to-end trace.

The consumer must rebuild the webhook's trace context from the stream entry's
``traceparent`` and open the ``turn`` span as its child — otherwise every
WhatsApp message produces two disconnected traces and the Grafana view of
"webhook → queue → runner" is a lie.

Also pins that the trace-context fields never leak into ``InboundEvent``
construction (they are transport metadata, not business payload).

fakeredis quirk: a blocking ``XREADGROUP`` on an *empty* stream spins the
event loop, so the harness stops the consumer from ``on_processed`` — the
consumer only ever blocks when there is data to read.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

import pytest
from fakeredis import aioredis as fakeaioredis
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from nexus_worker.observability.otel import install_worker_tracing
from nexus_worker.streams import consumer as consumer_mod

pytestmark = pytest.mark.asyncio

STREAM = "nexus:inbound"
GROUP = "nexus-worker-test"

# A fixed upstream context, as the webhook would have injected it.
UPSTREAM_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
UPSTREAM_SPAN_ID = "b7ad6b7169203331"
UPSTREAM_TRACEPARENT = f"00-{UPSTREAM_TRACE_ID}-{UPSTREAM_SPAN_ID}-01"


@pytest.fixture
def span_exporter() -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    install_worker_tracing("nexus-worker-test", extra_processor=SimpleSpanProcessor(exporter))
    exporter.clear()
    return exporter


def _entry_fields(**extra: str) -> dict[str, str]:
    return {
        "tenant_id": str(uuid.uuid4()),
        "channel_id": str(uuid.uuid4()),
        "user_id": "56911112222",
        "content": "hola",
        "provider": "meta",
        **extra,
    }


async def _consume_all(redis, monkeypatch, *, expected: int = 1) -> list:
    """Run the consumer until ``expected`` entries are processed, then stop.

    Stops from ``on_processed`` so the consumer never issues a blocking read
    against an empty stream (see module docstring). Returns the events that
    reached ``process_inbound``.
    """
    captured: list = []

    async def fake_process_inbound(event, *, pipeline):
        captured.append(event)
        return {}

    monkeypatch.setattr(consumer_mod, "process_inbound", fake_process_inbound)

    # Group anchored at 0 so entries added before the consumer starts are
    # delivered (the production group uses ``$`` but exists long before).
    with contextlib.suppress(Exception):
        await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)

    stop = asyncio.Event()
    seen = 0

    async def on_processed(event):
        nonlocal seen
        seen += 1
        if seen >= expected:
            stop.set()

    await asyncio.wait_for(
        consumer_mod.run_inbound_consumer(
            redis,
            pipeline=None,
            stream=STREAM,
            group=GROUP,
            consumer_name="c1",
            block_ms=10,
            stop=stop,
            on_processed=on_processed,
        ),
        timeout=10.0,
    )
    return captured


async def test_turn_span_joins_webhook_trace(monkeypatch, span_exporter) -> None:
    redis = fakeaioredis.FakeRedis()
    fields = _entry_fields(traceparent=UPSTREAM_TRACEPARENT)
    await redis.xadd(STREAM, fields)

    await _consume_all(redis, monkeypatch)

    turns = [s for s in span_exporter.get_finished_spans() if s.name == "turn"]
    assert len(turns) == 1
    turn = turns[0]
    assert f"{turn.context.trace_id:032x}" == UPSTREAM_TRACE_ID
    assert turn.parent is not None
    assert f"{turn.parent.span_id:016x}" == UPSTREAM_SPAN_ID
    assert turn.attributes["tenant_id"] == fields["tenant_id"]
    assert turn.attributes["channel_id"] == fields["channel_id"]


async def test_turn_span_fresh_trace_without_traceparent(monkeypatch, span_exporter) -> None:
    redis = fakeaioredis.FakeRedis()
    await redis.xadd(STREAM, _entry_fields())

    await _consume_all(redis, monkeypatch)

    turns = [s for s in span_exporter.get_finished_spans() if s.name == "turn"]
    assert len(turns) == 1
    assert turns[0].parent is None
    assert f"{turns[0].context.trace_id:032x}" != UPSTREAM_TRACE_ID


async def test_trace_fields_do_not_leak_into_event(monkeypatch, span_exporter) -> None:
    redis = fakeaioredis.FakeRedis()
    fields = _entry_fields(traceparent=UPSTREAM_TRACEPARENT, tracestate="vendor=1")
    await redis.xadd(STREAM, fields)

    captured = await _consume_all(redis, monkeypatch)

    assert len(captured) == 1
    event = captured[0]
    assert str(event.tenant_id) == fields["tenant_id"]
    assert event.content == "hola"
