"""Reminder cron — dispatches ``scheduled_jobs`` rows of kind=reminder.

Block D's ``notification.schedule_reminder`` tool persists a row in
``scheduled_jobs`` with ``kind='reminder'`` + ``payload``. Block H wires the
full cron dispatcher (also handles ``health_check`` and ``no_show_scrape``);
block F ships only the ``reminder`` kind because the booking flow needs it
for the smoke 1 / 5 / 6 scenarios.

Each tick (~30s):

1. Discover active tenants (RLS-free read on ``tenants``).
2. For each tenant, open a tenant-scoped session, ``SELECT ... FOR UPDATE
   SKIP LOCKED`` rows where status='pending' AND kind='reminder' AND
   run_at <= now().
3. For each row, call ``MCPRegistry.dispatch('notification.send_template',
   args)`` with the payload — that writes a ``messages.status='pending'``
   row, which the outbound dispatcher then drains.
4. Mark the job ``sent``.

If the dispatch fails, increment ``attempts`` + ``last_error``. The cron is
NOT a destination of failure handling — it just records and retries on the
next tick.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    ScheduledJob,
    ScheduledJobKind,
    ScheduledJobStatus,
    Tenant,
    TenantStatus,
)
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 30.0


async def run_reminder_cron(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    """Background task. One pass per ``tick_seconds``."""
    log.info("reminder_cron.start", tick_seconds=tick_seconds)
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            await _process_pending(sm)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("reminder_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("reminder_cron.stopped")


async def _process_pending(sm: sa.orm.sessionmaker) -> None:  # type: ignore[type-arg]
    async with sm() as session:
        tenant_ids_result = await session.execute(
            sa.select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE)
        )
        tenant_ids = [r[0] for r in tenant_ids_result]

    for tid in tenant_ids:
        async with sm() as session, tenant_scoped_session(session, tid):
            await _dispatch_tenant_reminders(session, tid)


async def _dispatch_tenant_reminders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> None:
    now = datetime.now(UTC)
    rows_result = await session.execute(
        sa.select(ScheduledJob)
        .where(
            ScheduledJob.kind == ScheduledJobKind.REMINDER,
            ScheduledJob.status == ScheduledJobStatus.PENDING,
            ScheduledJob.run_at <= now,
        )
        .order_by(ScheduledJob.run_at.asc())
        .limit(50)
        .with_for_update(skip_locked=True)
    )
    jobs = list(rows_result.scalars())
    if not jobs:
        return
    log.info("reminder_cron.batch", tenant_id=str(tenant_id), count=len(jobs))

    # Lazy import to avoid pulling the whole MCP graph at module import.
    from nexus_mcp import MCPRegistry, build_default_registry

    registry: MCPRegistry = build_default_registry()
    for job in jobs:
        await _dispatch_one(session, job, registry, tenant_id)


async def _dispatch_one(
    session: AsyncSession,
    job: ScheduledJob,
    registry: Any,
    tenant_id: uuid.UUID,
) -> None:
    payload = cast(dict[str, Any], job.payload or {})
    template_name = payload.get("template")
    conversation_id = payload.get("conversation_id")
    if not template_name or not conversation_id:
        job.status = ScheduledJobStatus.FAILED
        job.last_error = "payload missing 'template' and/or 'conversation_id'"
        return
    args: dict[str, Any] = {
        "conversation_id": conversation_id,
        "template_name": template_name,
        "parameters": payload.get("params") or payload.get("parameters") or {},
    }
    try:
        await registry.dispatch(
            "notification.send_template",
            args,
            whitelist=["notification.send_template"],
        )
    except Exception as exc:
        job.attempts += 1
        job.last_error = f"{type(exc).__name__}: {exc}"[:500]
        log.warning(
            "reminder_cron.dispatch_failed",
            tenant_id=str(tenant_id),
            job_id=str(job.id),
            attempts=job.attempts,
            error=job.last_error,
        )
        return
    job.status = ScheduledJobStatus.SENT
    job.last_error = None
    log.info(
        "reminder_cron.dispatched",
        tenant_id=str(tenant_id),
        job_id=str(job.id),
        template=template_name,
    )
