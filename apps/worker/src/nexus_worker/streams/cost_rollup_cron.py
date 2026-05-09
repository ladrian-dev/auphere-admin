"""Cost rollup cron — daily message-cost snapshot + threshold alert.

For every active tenant, every hour:

1. Recomputes ``cost_usd_total`` for the current calendar day (UTC) by
   summing ``messages.cost_usd`` (block B has the column nullable —
   NULLs are treated as 0).
2. Upserts the row in ``daily_cost_snapshots`` keyed by
   ``(tenant_id, day)``.
3. If the new total exceeds ``tenants.cost_alert_threshold_usd_per_day``
   AND ``threshold_exceeded_at`` is still NULL for that day, flips the
   timestamp AND writes an ``audit_log`` with action
   ``cost.daily_threshold_exceeded`` — the operator alerter then turns
   that into a WhatsApp template (``alert_cost_threshold_v1``) to Lee.

The audit row carries the live total so the alerter can render the
amount without re-reading the snapshot.

Tick: 1 hour. The granularity matches the alert resolution we want;
faster ticks would just bump cost without reducing alert latency.

Recompute (vs incremental sum) is intentional — the snapshot survives
back-dated cost edits, recovers from a missed tick, and is cheap (the
day-window is bounded by Pro tier message volume).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AuditLog,
    DailyCostSnapshot,
    Message,
    Tenant,
    TenantStatus,
)
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 3600.0
ACTOR = "system:cost_rollup_cron"


async def run_cost_rollup_cron(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    """Background task. One pass per ``tick_seconds``."""
    log.info("cost_rollup_cron.start", tick_seconds=tick_seconds)
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            await _process(sm)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("cost_rollup_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("cost_rollup_cron.stopped")


async def _process(sm: sa.orm.sessionmaker) -> None:  # type: ignore[type-arg]
    async with sm() as session:
        rows = await session.execute(
            sa.select(Tenant.id, Tenant.cost_alert_threshold_usd_per_day).where(
                Tenant.status == TenantStatus.ACTIVE
            )
        )
        tenants = [(r[0], r[1] or Decimal("0")) for r in rows]

    today = datetime.now(UTC).date()
    for tid, threshold in tenants:
        async with sm() as session, tenant_scoped_session(session, tid):
            await _rollup_tenant(session, tid, today, threshold)


async def _rollup_tenant(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    day: date,
    threshold: Decimal,
) -> None:
    start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
    end = start + timedelta(days=1)

    agg = await session.execute(
        sa.select(
            sa.func.coalesce(sa.func.sum(Message.cost_usd), 0).label("total"),
            sa.func.count(Message.id).label("count"),
        ).where(Message.created_at >= start, Message.created_at < end)
    )
    row = agg.one()
    total = Decimal(str(row.total or 0))
    count = int(row.count or 0)

    snap_row = await session.execute(
        sa.select(DailyCostSnapshot).where(DailyCostSnapshot.day == day).limit(1)
    )
    snap = snap_row.scalar_one_or_none()
    just_breached = False
    if snap is None:
        snap = DailyCostSnapshot(
            tenant_id=tenant_id,
            day=day,
            cost_usd_total=total,
            message_count=count,
            threshold_exceeded_at=None,
        )
        session.add(snap)
    else:
        snap.cost_usd_total = total
        snap.message_count = count

    if (
        threshold is not None
        and threshold > Decimal("0")
        and total >= threshold
        and snap.threshold_exceeded_at is None
    ):
        snap.threshold_exceeded_at = datetime.now(UTC)
        just_breached = True

    if just_breached:
        audit = AuditLog(
            tenant_id=tenant_id,
            actor=ACTOR,
            action="cost.daily_threshold_exceeded",
            target=f"tenant:{tenant_id}:day:{day.isoformat()}",
            before_json=None,
            after_json={
                "day": day.isoformat(),
                "cost_usd_total": str(total),
                "threshold_usd": str(threshold),
                "message_count": count,
            },
        )
        session.add(audit)
        log.warning(
            "cost_rollup_cron.threshold_exceeded",
            tenant_id=str(tenant_id),
            day=day.isoformat(),
            total=str(total),
            threshold=str(threshold),
        )
