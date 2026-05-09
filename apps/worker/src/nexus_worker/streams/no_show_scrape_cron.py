"""No-show scrape cron — daily 22:00 (tenant local) AgendaPro pull.

For every tenant with an active AgendaPro integration this cron, when
the local time hits 22:00 (the smoke-6 window for ``no_show_followup``):

1. Scrapes today's no-show list via
   ``agendapro.scrape_no_shows`` (subprocess MCP).
2. For each customer in the result, schedules a
   ``notification.send_template`` with template ``no_show_followup``.
3. Persists a ``scheduled_jobs(kind='no_show_scrape')`` row marked
   ``sent`` with the count, so re-runs the same calendar day are
   idempotent.

Tick: 1 hour. The cron checks the tenant local time and runs at most
once per tenant per local day.

Time-of-day guard relies on ``zoneinfo`` (stdlib) using the tenant's
``timezone`` column. If the column is missing, falls back to UTC.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 3600.0
LOCAL_HOUR_TARGET = 22
ACTOR = "system:no_show_scrape_cron"


async def run_no_show_scrape_cron(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    """Background task. One pass per ``tick_seconds``."""
    log.info("no_show_scrape_cron.start", tick_seconds=tick_seconds)
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            await _process_pending(sm)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("no_show_scrape_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("no_show_scrape_cron.stopped")


async def _process_pending(sm: sa.orm.sessionmaker) -> None:  # type: ignore[type-arg]
    async with sm() as session:
        tenant_rows = await session.execute(
            sa.select(Tenant.id, Tenant.timezone).where(
                Tenant.status == TenantStatus.ACTIVE
            )
        )
        tenants = [(r[0], r[1] or "UTC") for r in tenant_rows]

    now_utc = datetime.now(UTC)
    for tid, tz_name in tenants:
        if not _is_local_window(now_utc, tz_name):
            continue
        async with sm() as session, tenant_scoped_session(session, tid):
            await _process_tenant(session, tid, tz_name)


def _is_local_window(now_utc: datetime, tz_name: str) -> bool:
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
    local = now_utc.astimezone(tz)
    return local.hour == LOCAL_HOUR_TARGET


def _local_today(tz_name: str) -> date:
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()


async def _process_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, tz_name: str
) -> None:
    has_creds = await _tenant_has_agendapro(session)
    if not has_creds:
        return

    today = _local_today(tz_name)
    if await _already_ran_today(session, today):
        return

    job = ScheduledJob(
        tenant_id=tenant_id,
        kind=ScheduledJobKind.NO_SHOW_SCRAPE,
        run_at=datetime.now(UTC),
        payload={"local_day": today.isoformat(), "timezone": tz_name, "scheduled_by": ACTOR},
        status=ScheduledJobStatus.PENDING,
    )
    session.add(job)
    await session.flush()

    try:
        no_shows = await _scrape_no_shows(session)
    except Exception as exc:
        job.status = ScheduledJobStatus.FAILED
        job.last_error = f"{type(exc).__name__}: {exc}"[:500]
        log.warning(
            "no_show_scrape_cron.scrape_failed",
            tenant_id=str(tenant_id),
            error=job.last_error,
        )
        return

    scheduled = 0
    for entry in no_shows:
        ok = await _schedule_followup(session, entry)
        if ok:
            scheduled += 1

    job.status = ScheduledJobStatus.SENT
    payload: dict[str, Any] = dict(job.payload or {})
    payload.update(
        {
            "scraped_count": len(no_shows),
            "scheduled_count": scheduled,
            "completed_at": datetime.now(UTC).isoformat(),
        }
    )
    job.payload = payload
    log.info(
        "no_show_scrape_cron.dispatched",
        tenant_id=str(tenant_id),
        scraped=len(no_shows),
        scheduled=scheduled,
    )


async def _tenant_has_agendapro(session: AsyncSession) -> bool:
    row = await session.execute(
        sa.select(sa.literal(1))
        .select_from(TenantCredentials)
        .where(TenantCredentials.integration == "agendapro")
        .limit(1)
    )
    return row.first() is not None


async def _already_ran_today(session: AsyncSession, today: date) -> bool:
    """Check ``scheduled_jobs(kind=no_show_scrape)`` whose payload.local_day
    matches today. Idempotency at the calendar-day granularity."""
    rows = await session.execute(
        sa.select(ScheduledJob.payload).where(
            ScheduledJob.kind == ScheduledJobKind.NO_SHOW_SCRAPE,
            ScheduledJob.status.in_(
                (ScheduledJobStatus.SENT, ScheduledJobStatus.FAILED)
            ),
            ScheduledJob.run_at >= datetime.now(UTC) - timedelta(hours=36),
        )
    )
    target = today.isoformat()
    for (payload,) in rows:
        if isinstance(payload, dict) and payload.get("local_day") == target:
            return True
    return False


async def _scrape_no_shows(session: AsyncSession) -> list[dict[str, Any]]:
    """Invoke ``agendapro.scrape_no_shows`` via dispatch_internal."""
    from nexus_mcp import build_default_registry, get_internal_caller_token

    registry = build_default_registry()
    envelope = await registry.dispatch_internal(
        "agendapro.scrape_no_shows",
        {},
        caller_token=get_internal_caller_token(),
    )
    result = envelope.get("result") or {}
    items = result.get("no_shows") or result.get("items") or []
    if not isinstance(items, list):
        return []
    return [dict(x) for x in items if isinstance(x, dict)]


async def _schedule_followup(session: AsyncSession, entry: dict[str, Any]) -> bool:
    """Push a ``notification.send_template`` via the registry — that
    inserts the outbound ``messages`` row that the dispatcher drains."""
    conversation_id = entry.get("conversation_id")
    if not conversation_id:
        return False
    customer_name = entry.get("customer_name") or "cliente"
    barber_name = entry.get("barber_name") or ""
    fee_label = entry.get("fee_label") or ""
    from nexus_mcp import build_default_registry

    registry = build_default_registry()
    try:
        await registry.dispatch(
            "notification.send_template",
            {
                "conversation_id": conversation_id,
                "template_name": "no_show_followup",
                "parameters": {
                    "customer_name": customer_name,
                    "barber_name": barber_name,
                    "fee_label": fee_label,
                },
            },
            whitelist=["notification.send_template"],
        )
    except Exception as exc:
        log.warning(
            "no_show_scrape_cron.followup_failed",
            conversation_id=str(conversation_id),
            error=str(exc),
        )
        return False
    return True


# Re-exported for tests.
__all__ = [
    "LOCAL_HOUR_TARGET",
    "_is_local_window",
    "_local_today",
    "run_no_show_scrape_cron",
]


# ``time`` is re-exported so tests that monkeypatch ``datetime.now`` can
# rely on the ``LOCAL_HOUR_TARGET`` constant being meaningful.
_ = time
