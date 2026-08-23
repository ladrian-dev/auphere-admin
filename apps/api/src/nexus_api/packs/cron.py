"""Due crons. Times persisted UTC; partner TZ is display-only."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.partner import Partner
from nexus_api.db.models.workflow import WorkflowCron, WorkflowPack, WorkflowRun

log = structlog.get_logger(__name__)

StartRun = Callable[[AsyncSession, WorkflowCron, WorkflowPack], Awaitable[None]]


def next_run_utc(
    hour: int,
    minute: int,
    timezone: str,
    *,
    now: datetime | None = None,
) -> datetime:
    tz = ZoneInfo(timezone)
    now_local = (now or datetime.now(UTC)).astimezone(tz)
    candidate = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now_local:
        candidate = candidate + timedelta(days=1)
    return candidate.astimezone(UTC)


def is_dead(cron: WorkflowCron, *, now: datetime) -> bool:
    if not cron.enabled:
        return True
    return bool(cron.end_time is not None and cron.end_time <= now)


async def process_due_workflow_crons(
    *,
    now: datetime | None = None,
    start_run: StartRun | None = None,
) -> int:
    """Fire enabled, unexpired crons whose ``run_at_utc`` is due. Dead ones never fire."""
    when = now or datetime.now(UTC)
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    starter = start_run or _default_start_run
    sm = get_sessionmaker()
    async with sm() as session:
        partner_ids = list((await session.scalars(sa.select(Partner.id))).all())

    fired = 0
    for partner_id in partner_ids:
        async with sm() as session, session.begin():
            await apply_partner_to_session(session, partner_id)
            crons = list((await session.scalars(sa.select(WorkflowCron))).all())
            for cron in crons:
                if cron.end_time is not None and cron.end_time <= when and cron.enabled:
                    cron.enabled = False
                    log.info("workflow_cron.disabled_expired", pack_id=str(cron.pack_id))
                if is_dead(cron, now=when):
                    continue
                if cron.run_at_utc > when:
                    continue
                pack = await session.get(WorkflowPack, cron.pack_id)
                if pack is None:
                    cron.enabled = False
                    continue
                await starter(session, cron, pack)
                cron.run_at_utc = next_run_utc(cron.hour, cron.minute, cron.timezone, now=when)
                fired += 1
    return fired


async def _default_start_run(session: AsyncSession, cron: WorkflowCron, pack: WorkflowPack) -> None:
    run_id = str(uuid.uuid4())
    thread_id = f"pack:{pack.id}:{run_id}"
    session.add(
        WorkflowRun(
            partner_id=cron.partner_id,
            pack_id=pack.id,
            thread_id=thread_id,
            status="pending",
        )
    )
    log.info(
        "workflow_cron.fired",
        pack_id=str(pack.id),
        thread_id=thread_id,
        run_id=run_id,
    )
