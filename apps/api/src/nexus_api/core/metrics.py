"""Lightweight in-process counters + persisted isolation event ledger.

Block B shipped the in-memory ``counters`` for the seven ``isolation.*``
metrics (and ``tool.*`` from block D). Block H persists each event to the
``isolation_events`` table so the operator panel can render real numbers
+ ``last_breach_at`` per tenant — and so we have an audit trail beyond
the lifetime of a single process.

Persistence flow:

1. Call sites (registry, pipeline, llm router, ...) invoke
   ``record_isolation_event(metric, tenant_id, payload)``. The function
   bumps the in-memory counter AND enqueues an event.
2. ``isolation_event_drainer`` (async task) pulls from the queue and
   writes rows in a tenant-scoped session. Started by both the API and
   the worker on startup.
3. The ``GET /admin/tenants/:id/isolation/metrics`` endpoint reads the
   last 24h from ``isolation_events`` per tenant.

The unscoped-query path (``isolation_enforcer``) increments the counter
only — that branch fires from a sync SQLAlchemy event handler with no
known tenant (the violation IS the missing tenant), so persistence
doesn't apply. Production raises in that case anyway; the dashboard
notes this guarantee is system-level.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections import defaultdict, deque
from typing import TYPE_CHECKING, Any, TypedDict

import structlog

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

log = structlog.get_logger(__name__)


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

# Persisted metrics — every increment of these writes a row to
# ``isolation_events``. ``isolation.unscoped_query`` is excluded because
# the enforcer fires before any tenant context exists.
PERSISTED_ISOLATION_METRICS = frozenset(
    {
        ISOLATION_TOOL_WHITELIST_VIOLATION,
        ISOLATION_KG_QUERY_UNSCOPED,
        ISOLATION_CHECKPOINT_THREAD_COLLISION,
        ISOLATION_PROMPT_RENDER_LEAKED_TOKEN,
        ISOLATION_LOG_MISSING_TENANT_TAG,
        ISOLATION_LLM_BATCH_CROSS_TENANT,
    }
)


class IsolationEventDict(TypedDict):
    metric: str
    tenant_id: uuid.UUID
    payload: dict[str, Any]


_DEFAULT_MAXSIZE = 10_000
_event_queue: deque[IsolationEventDict] = deque(maxlen=_DEFAULT_MAXSIZE)
_queue_lock = threading.Lock()


def get_event_queue() -> deque[IsolationEventDict]:
    """The module-level event buffer.

    A loop-agnostic ``deque`` (vs. ``asyncio.Queue``) so producers in
    sync code (the SQLAlchemy ``before_cursor_execute`` event handler)
    and async code (registry, pipeline, LLM router) can both push
    without a running event loop. The drainer is async and polls.
    """
    return _event_queue


def reset_event_queue() -> None:
    """Test helper — drops any pending events."""
    with _queue_lock:
        _event_queue.clear()


def record_isolation_event(
    metric: str,
    tenant_id: uuid.UUID,
    payload: dict[str, Any] | None = None,
) -> None:
    """Bump the in-memory counter AND enqueue a row for persistence.

    Both global (``metric``) and per-tenant (``metric:tenant_id``) counters
    are incremented so tests and the dashboard can read either view.
    Persistence is best-effort — the counter is the source of truth at
    runtime; the row is the source of truth across restarts.
    """
    counters.incr(metric)
    counters.incr(f"{metric}:{tenant_id}")
    if metric not in PERSISTED_ISOLATION_METRICS:
        return
    with _queue_lock:
        if len(_event_queue) >= _DEFAULT_MAXSIZE:
            log.warning(
                "isolation_events.queue_full",
                metric=metric,
                tenant_id=str(tenant_id),
            )
            return
        _event_queue.append(
            IsolationEventDict(
                metric=metric,
                tenant_id=tenant_id,
                payload=payload or {},
            )
        )


def _pop_batch(limit: int) -> list[IsolationEventDict]:
    out: list[IsolationEventDict] = []
    with _queue_lock:
        while _event_queue and len(out) < limit:
            out.append(_event_queue.popleft())
    return out


async def isolation_event_drainer(
    stop: asyncio.Event,
    *,
    sessionmaker_factory: sessionmaker[Any] | None = None,
    poll_seconds: float = 1.0,
    batch_size: int = 100,
) -> None:
    """Pull events from the queue and persist them to ``isolation_events``.

    Started by both the API (lifespan startup) and the worker (asyncio
    task in main). Each event opens a tenant-scoped session so RLS
    inserts succeed. Failures are logged and skipped — never blocking
    the producer.
    """
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import IsolationEvent

    sm = sessionmaker_factory or get_sessionmaker()
    log.info("isolation_event_drainer.start")
    while not stop.is_set():
        batch = _pop_batch(batch_size)
        if not batch:
            try:
                await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
            except TimeoutError:
                continue
            else:
                break
        for event in batch:
            try:
                tenant_id = event["tenant_id"]
                async with sm() as session, tenant_scoped_session(session, tenant_id):
                    row = IsolationEvent(
                        tenant_id=tenant_id,
                        metric=event["metric"],
                        payload=event["payload"],
                    )
                    session.add(row)
                    await session.commit()
            except Exception as exc:
                log.error(
                    "isolation_events.persist_failed",
                    error=str(exc),
                    metric=event.get("metric"),
                    tenant_id=str(event.get("tenant_id")),
                )
    log.info("isolation_event_drainer.stopped")
