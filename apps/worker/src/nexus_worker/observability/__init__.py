"""Block H observability — Langfuse SDK wiring + tracing helpers.

Phase 1 strategy:

- Langfuse Cloud (workspace ``auphere``). Self-host evaluated in Phase 2
  if cost > $50/mo per the locked decision.
- ``langfuse_client.get_client()`` returns either a real ``Langfuse``
  instance or a noop wrapper depending on ``NEXUS_LANGFUSE_PUBLIC_KEY``.
- ``tracing.trace_turn(...)`` is the per-pipeline-turn context manager;
  ``tracing.span(...)`` wraps a node or tool call. Both are noop when
  the SDK is disabled — production telemetry, dev/test silence.

The OTel TracerProvider that block B installed in the API process is
not duplicated here — Langfuse v3 is OpenTelemetry-native and exports
spans through the same provider.
"""

from nexus_worker.observability.langfuse_client import (
    LangfuseClientLike,
    get_client,
    init_langfuse,
    is_enabled,
    shutdown,
)
from nexus_worker.observability.tracing import (
    span,
    trace_turn,
    update_trace,
)

__all__ = [
    "LangfuseClientLike",
    "get_client",
    "init_langfuse",
    "is_enabled",
    "shutdown",
    "span",
    "trace_turn",
    "update_trace",
]
