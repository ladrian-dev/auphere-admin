"""Per-tenant isolation metrics for the operator panel.

``GET /admin/tenants/:tenant_id/isolation/metrics``

Reads the last 24h of ``isolation_events`` for the active tenant (RLS
scopes the query) and aggregates by ``metric``. Returns count +
``last_breach_at`` per canonical metric so the dashboard can render a
"0 / 24h" card for guarantees that are passing and a red card for
guarantees with > 0 breaches.

The 7 canonical metrics from architecture/agent-isolation.md are
returned with default zeros even if no events exist — the panel needs
the full set to render its grid.

``isolation.unscoped_query`` is a system-level metric (the enforcer
fires before any tenant context exists) and never persists rows; the
endpoint includes it with count=0 + a note.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import scoped_session_from_path
from nexus_api.core.metrics import (
    ISOLATION_CHECKPOINT_THREAD_COLLISION,
    ISOLATION_KG_QUERY_UNSCOPED,
    ISOLATION_LLM_BATCH_CROSS_TENANT,
    ISOLATION_LOG_MISSING_TENANT_TAG,
    ISOLATION_PROMPT_RENDER_LEAKED_TOKEN,
    ISOLATION_TOOL_WHITELIST_VIOLATION,
    ISOLATION_UNSCOPED_QUERY,
)
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import IsolationEvent

router = APIRouter()
log = structlog.get_logger()


_CANONICAL_METRICS: tuple[str, ...] = (
    ISOLATION_UNSCOPED_QUERY,
    ISOLATION_TOOL_WHITELIST_VIOLATION,
    ISOLATION_KG_QUERY_UNSCOPED,
    ISOLATION_CHECKPOINT_THREAD_COLLISION,
    ISOLATION_PROMPT_RENDER_LEAKED_TOKEN,
    ISOLATION_LOG_MISSING_TENANT_TAG,
    ISOLATION_LLM_BATCH_CROSS_TENANT,
)


class IsolationMetric(BaseModel):
    metric: str
    count_24h: int
    last_breach_at: datetime | None
    persisted: bool


class IsolationMetricsOut(BaseModel):
    tenant_id: uuid.UUID
    window_hours: int
    generated_at: datetime
    metrics: list[IsolationMetric]


@router.get(
    "/tenants/{tenant_id}/isolation/metrics",
    response_model=IsolationMetricsOut,
    dependencies=[Depends(require_admin_token)],
)
async def get_isolation_metrics(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
) -> IsolationMetricsOut:
    now = datetime.now(UTC)
    since = now - timedelta(hours=24)

    rows = await session.execute(
        sa.select(
            IsolationEvent.metric,
            sa.func.count(IsolationEvent.id).label("count_24h"),
            sa.func.max(IsolationEvent.created_at).label("last_breach_at"),
        )
        .where(IsolationEvent.created_at >= since)
        .group_by(IsolationEvent.metric)
    )
    by_metric: dict[str, tuple[int, datetime | None]] = {
        row.metric: (int(row.count_24h), row.last_breach_at) for row in rows
    }

    metrics: list[IsolationMetric] = []
    for name in _CANONICAL_METRICS:
        count, last = by_metric.get(name, (0, None))
        metrics.append(
            IsolationMetric(
                metric=name,
                count_24h=count,
                last_breach_at=last,
                persisted=name != ISOLATION_UNSCOPED_QUERY,
            )
        )

    return IsolationMetricsOut(
        tenant_id=tenant_id,
        window_hours=24,
        generated_at=now,
        metrics=metrics,
    )
