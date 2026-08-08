"""OpenTelemetry for the worker process (WP-01, plataforma v2 Fase 0).

The worker historically had Langfuse only — spans died at the queue and a
WhatsApp message produced two disconnected traces (webhook, then nothing).
This module gives every worker entrypoint a real ``TracerProvider`` with the
shared Resource, an optional OTLP exporter (same ``NEXUS_OTEL_ENABLED`` +
``OTEL_EXPORTER_OTLP_ENDPOINT`` contract as the API), and the context
extraction that stitches a stream entry back onto the webhook's trace.

``install_worker_tracing`` is idempotent per process; each entrypoint calls
it with its service name (``nexus-worker`` today; ``nexus-runner`` /
``nexus-scheduler`` / ``nexus-egress`` after WP-07).
"""

from __future__ import annotations

from typing import Any

import structlog
from opentelemetry import propagate, trace
from opentelemetry.context import Context
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider

log = structlog.get_logger(__name__)

_provider: TracerProvider | None = None

# Stream-entry field names that belong to the W3C trace context, not to the
# business payload. The consumer skips them when building the InboundEvent.
TRACE_FIELDS = frozenset({"traceparent", "tracestate"})


def install_worker_tracing(
    service_name: str,
    *,
    extra_processor: SpanProcessor | None = None,
) -> TracerProvider:
    """Install the global tracer provider for this worker process.

    ``extra_processor`` exists for tests (an in-memory exporter); production
    wiring is driven purely by env. Calling twice returns the existing
    provider — the SDK forbids replacing a global provider, and entrypoints
    that share a process (dev's all-in-one ``main.py``) share one anyway.
    """
    global _provider
    if _provider is not None:
        if extra_processor is not None:
            _provider.add_span_processor(extra_processor)
        return _provider

    # Reuse the API's Resource + exporter policy so both sides of the queue
    # describe themselves consistently in Grafana.
    from nexus_api.core.otel import build_provider

    _provider = build_provider(service_name)
    if extra_processor is not None:
        _provider.add_span_processor(extra_processor)
    trace.set_tracer_provider(_provider)
    log.info("otel.worker_tracing_installed", service=service_name)
    return _provider


def extract_trace_context(fields: dict[str, str]) -> Context | None:
    """Rebuild the webhook's trace context from a stream entry's fields.

    Returns ``None`` when the entry carries no ``traceparent`` — the turn
    span then starts a fresh trace, which is exactly right for entries
    published before this deploy or by non-instrumented producers.
    """
    if "traceparent" not in fields:
        return None
    return propagate.extract(fields)


def get_tracer() -> Any:
    return trace.get_tracer("nexus_worker")
