"""Health-check cron — periodic AgendaPro context verification.

For every tenant with an active AgendaPro integration this cron:

1. Auto-seeds a ``scheduled_jobs(kind='health_check', status='pending',
   run_at=now())`` row when one doesn't exist. Block E pre-extended the
   enum but did not seed.
2. Drains pending rows whose ``run_at <= now()`` via
   ``run_agendapro_health_check`` (in-process — no HTTP roundtrip), so
   the audit_log row that the operator alerter consumes lands inside
   the same transaction.
3. Re-schedules a new pending job 7 days out on success. On failure the
   job is parked at ``failed`` with ``last_error``; the next tick tries
   again only because auto-seed will create a new pending row.

Tick: 1 hour. The cadence requirement is "weekly per tenant"; tighter
ticks only matter when re-trying after a failure window.

Pattern shared with ``reminder_cron.py`` (block F):
- Discover ACTIVE tenants (RLS-free read).
- Per tenant: open ``tenant_scoped_session`` → ``FOR UPDATE SKIP LOCKED``.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    ScheduledJob,
    ScheduledJobKind,
    ScheduledJobStatus,
    Tenant,
    TenantCredentials,
    TenantStatus,
)
from nexus_api.services.agendapro_health import (
    AgendaProNotConfigured,
    run_agendapro_health_check,
)
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 3600.0
RESCHEDULE_INTERVAL = timedelta(days=7)
ACTOR = "system:health_check_cron"


async def run_health_check_cron(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    """Background task. One pass per ``tick_seconds``."""
    log.info("health_check_cron.start", tick_seconds=tick_seconds)
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            await _process_pending(sm)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("health_check_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("health_check_cron.stopped")


async def _process_pending(sm: sa.orm.sessionmaker) -> None:  # type: ignore[type-arg]
    async with sm() as session:
        tenant_rows = await session.execute(
            sa.select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE)
        )
        tenant_ids = [r[0] for r in tenant_rows]

    for tid in tenant_ids:
        # Phase 1 — seed under a fresh tenant-scoped transaction.
        async with sm() as session, tenant_scoped_session(session, tid):
            has_creds = await _tenant_has_agendapro(session)
            if not has_creds:
                continue
            await _ensure_seed(session, tid)

        # Phase 2 — dispatch any due rows in a separate tenant-scoped tx.
        # Two sessions because ``SET LOCAL`` (RLS scope, role) is
        # transaction-bound: keeping seed + dispatch separate avoids
        # mixing semantics inside one session manager.
        async with sm() as session, tenant_scoped_session(session, tid):
            await _dispatch_due_jobs(session, tid)


async def _dispatch_due_jobs(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    rows = await session.execute(
        sa.select(ScheduledJob)
        .where(
            ScheduledJob.kind == ScheduledJobKind.HEALTH_CHECK,
            ScheduledJob.status == ScheduledJobStatus.PENDING,
            ScheduledJob.run_at <= now,
        )
        .order_by(ScheduledJob.run_at.asc())
        .limit(5)
        .with_for_update(skip_locked=True)
    )
    jobs = list(rows.scalars())
    if not jobs:
        return
    log.info(
        "health_check_cron.batch",
        tenant_id=str(tenant_id),
        count=len(jobs),
    )
    for job in jobs:
        await _run_one(session, job, tenant_id)


async def _tenant_has_agendapro(session: AsyncSession) -> bool:
    row = await session.execute(
        sa.select(sa.literal(1))
        .select_from(TenantCredentials)
        .where(TenantCredentials.integration == "agendapro")
        .limit(1)
    )
    return row.first() is not None


async def _ensure_seed(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Idempotent — only seeds if no PENDING health_check job exists."""
    existing = await session.execute(
        sa.select(sa.literal(1))
        .select_from(ScheduledJob)
        .where(
            ScheduledJob.kind == ScheduledJobKind.HEALTH_CHECK,
            ScheduledJob.status == ScheduledJobStatus.PENDING,
        )
        .limit(1)
    )
    if existing.first() is not None:
        return
    seed = ScheduledJob(
        tenant_id=tenant_id,
        kind=ScheduledJobKind.HEALTH_CHECK,
        run_at=datetime.now(UTC),
        payload={"seeded_by": ACTOR},
        status=ScheduledJobStatus.PENDING,
    )
    session.add(seed)
    log.info("health_check_cron.seed", tenant_id=str(tenant_id))


async def _run_one(
    session: AsyncSession,
    job: ScheduledJob,
    tenant_id: uuid.UUID,
) -> None:
    try:
        result = await run_agendapro_health_check(session, tenant_id, actor=ACTOR)
    except AgendaProNotConfigured:
        # Race: creds disappeared between the discovery and the dispatch.
        # Mark the job cancelled — it'll be re-seeded next tick if creds
        # come back.
        job.status = ScheduledJobStatus.CANCELLED
        job.last_error = "agendapro_not_configured"
        return
    except Exception as exc:
        job.attempts += 1
        job.last_error = f"{type(exc).__name__}: {exc}"[:500]
        log.warning(
            "health_check_cron.dispatch_failed",
            tenant_id=str(tenant_id),
            job_id=str(job.id),
            attempts=job.attempts,
            error=job.last_error,
        )
        return

    job.status = ScheduledJobStatus.SENT
    job.last_error = None
    payload: dict[str, Any] = dict(job.payload or {})
    payload["last_run_at"] = result.checked_at.isoformat()
    payload["last_run_healthy"] = result.healthy
    payload["last_needs_reauth"] = result.needs_reauth
    job.payload = payload

    # Re-schedule a fresh pending row for next week.
    next_run = datetime.now(UTC) + RESCHEDULE_INTERVAL
    follow_up = ScheduledJob(
        tenant_id=tenant_id,
        kind=ScheduledJobKind.HEALTH_CHECK,
        run_at=next_run,
        payload={"scheduled_by": ACTOR, "previous_job_id": str(job.id)},
        status=ScheduledJobStatus.PENDING,
    )
    session.add(follow_up)
    log.info(
        "health_check_cron.dispatched",
        tenant_id=str(tenant_id),
        job_id=str(job.id),
        healthy=result.healthy,
        needs_reauth=result.needs_reauth,
        next_run_at=next_run.isoformat(),
    )
