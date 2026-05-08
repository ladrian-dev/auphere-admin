"""Lightweight in-process counters for the `isolation.*` metrics.

In production these should be exported to Prometheus / Langfuse via OTel; in block
B we only need observable counters that tests can assert on. A real exporter is
wired in block H.
"""

from __future__ import annotations

import threading
from collections import defaultdict


class Counters:
    def __init__(self) -> None:
        self._values: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def incr(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self._values[key] += amount

    def get(self, key: str) -> int:
        with self._lock:
            return self._values[key]

    def reset(self) -> None:
        with self._lock:
            self._values.clear()

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._values)


counters = Counters()


# Canonical metric names. Centralised here so tests, alerts, and runtime use the
# same strings. Mirrors the table in architecture/agent-isolation.md.
ISOLATION_UNSCOPED_QUERY = "isolation.unscoped_query"
ISOLATION_TOOL_WHITELIST_VIOLATION = "isolation.tool_whitelist_violation"
ISOLATION_KG_QUERY_UNSCOPED = "isolation.kg_query_unscoped"
ISOLATION_CHECKPOINT_THREAD_COLLISION = "isolation.checkpoint_thread_collision"
ISOLATION_PROMPT_RENDER_LEAKED_TOKEN = "isolation.prompt_render_leaked_token"
ISOLATION_LOG_MISSING_TENANT_TAG = "isolation.log_missing_tenant_tag"
ISOLATION_LLM_BATCH_CROSS_TENANT = "isolation.llm_batch_cross_tenant"
CHANNEL_UNRESOLVED_EVENT = "channel.unresolved_event"
