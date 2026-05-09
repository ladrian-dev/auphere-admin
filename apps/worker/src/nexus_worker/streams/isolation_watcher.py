"""Isolation watcher — ``isolation_events`` → ``audit_log`` → operator alert.

The ``record_isolation_event`` call site bumps in-memory counters and
enqueues a row to ``isolation_events`` (block H, ``core/metrics.py``).
This watcher picks those rows up and writes a single
``isolation.violation_detected`` audit per (tenant, metric, hour) so
the operator alerter doesn't spam Lee on a burst of correlated events.

Tick: 60s. We over-tick for liveness (P1 metric, low volume); the
hourly dedup keeps notification volume bounded.

Pattern shared with ``operator_alerts.py``: outer scan over ACTIVE
tenants, inner ``tenant_scoped_session`` runs the dedup query against
``isolation_events`` joined with ``audit_log``.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AuditLog,
    IsolationEvent,
    Tenant,
    TenantStatus,
)
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 60.0
ACTOR = "system:isolation_watcher"
ACTION = "isolation.violation_detected"
DEDUP_WINDOW = timedelta(hours=1)


async def run_isolation_watcher(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    """Background task. One pass per ``tick_seconds``."""
    log.info("isolation_watcher.start", tick_seconds=tick_seconds)
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            await _process(sm)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("isolation_watcher.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("isolation_watcher.stopped")


async def _process(sm: sa.orm.sessionmaker) -> None:  # type: ignore[type-arg]
    async with sm() as session:
        rows = await session.execute(
            sa.select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE)
        )
        tenant_ids = [r[0] for r in rows]

    for tid in tenant_ids:
        async with sm() as session, tenant_scoped_session(session, tid):
            await _process_tenant(session, tid)


async def _process_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    since = now - DEDUP_WINDOW
    # Distinct metrics with at least one isolation_event row in the
    # last hour. RLS scopes by tenant_id automatically.
    metrics_rows = await session.execute(
        sa.select(
            IsolationEvent.metric.label("metric"),
            sa.func.count(IsolationEvent.id).label("count_24h"),
            sa.func.max(IsolationEvent.created_at).label("last_at"),
        )
        .where(IsolationEvent.created_at >= since)
        .group_by(IsolationEvent.metric)
    )
    rows = list(metrics_rows.all())
    if not rows:
        return

    for row in rows:
        metric_name = str(row.metric)
        count_24h = int(row.count_24h)
        last_at = row.last_at
        target = f"tenant:{tenant_id}:metric:{metric_name}"
        existing = await session.execute(
            sa.select(sa.literal(1))
            .select_from(AuditLog)
            .where(
                AuditLog.action == ACTION,
                AuditLog.target == target,
                AuditLog.created_at >= since,
            )
            .limit(1)
        )
        if existing.first() is not None:
            continue
        audit = AuditLog(
            tenant_id=tenant_id,
            actor=ACTOR,
            action=ACTION,
            target=target,
            before_json=None,
            after_json={
                "metric": metric_name,
                "count": count_24h,
                "last_at": last_at.isoformat() if last_at else None,
                "window": "1h",
            },
        )
        session.add(audit)
        log.warning(
            "isolation_watcher.audit_emitted",
            tenant_id=str(tenant_id),
            metric=metric_name,
            count=count_24h,
        )
