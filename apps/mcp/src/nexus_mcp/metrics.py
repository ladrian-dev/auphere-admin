"""Tool-level counters shared by all MCP servers.

Block H instruments these with Langfuse / OpenLLMetry. Block D ships
in-process counters so tests can assert on them without standing up an
exporter. They live alongside the existing ``isolation.*`` counters in
``nexus_api.core.metrics`` and use the same ``Counters`` instance so a
single snapshot covers everything.
"""

from __future__ import annotations

from nexus_api.core.metrics import counters

TOOL_INVOKED = "tool.invoked"
TOOL_ERROR = "tool.error"
TOOL_LATENCY_MS = "tool.latency_ms"


def record_invocation(tool_name: str) -> None:
    counters.incr(f"{TOOL_INVOKED}:{tool_name}")
    counters.incr(TOOL_INVOKED)


def record_error(tool_name: str, error_class: str) -> None:
    counters.incr(f"{TOOL_ERROR}:{tool_name}:{error_class}")
    counters.incr(TOOL_ERROR)


def record_latency(tool_name: str, ms: int) -> None:
    # Block D keeps it simple: a sum + count counter pair so we can compute
    # an average. Block H replaces with a real histogram.
    counters.incr(f"{TOOL_LATENCY_MS}:sum:{tool_name}", ms)
    counters.incr(f"{TOOL_LATENCY_MS}:count:{tool_name}")
