"""Reminder cron: drains scheduled_jobs of kind=reminder, dispatching them
through ``notification.send_template`` which writes a ``messages.status='pending'``
row that the outbound dispatcher then sends to YCloud.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.streams.reminder_cron import _process_pending

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Message,
    MessageDirection,
    MessageStatus,
    ScheduledJob,
    ScheduledJobKind,
    ScheduledJobStatus,
)

pytestmark = pytest.mark.asyncio


async def _seed_scheduled(
    *,
    tenant_info: dict[str, Any],
    template: str,
    run_at: datetime,
    extra_payload: dict | None = None,
) -> uuid.UUID:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_info["tenant_id"]):
        payload: dict[str, Any] = {
            "conversation_id": str(tenant_info["conversation_id"]),
            "template": template,
            "language": "es_CL",
            "params": {"customer_name": "Juan", "barber_name": "Luis"},
        }
        if extra_payload:
            payload.update(extra_payload)
        job = ScheduledJob(
            tenant_id=tenant_info["tenant_id"],
            kind=ScheduledJobKind.REMINDER,
            run_at=run_at,
            payload=payload,
            status=ScheduledJobStatus.PENDING,
        )
        session.add(job)
        await session.flush()
        await session.refresh(job)
        return job.id


async def _read_job(tenant_id: uuid.UUID, job_id: uuid.UUID) -> ScheduledJob:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        result = await session.execute(sa.select(ScheduledJob).where(ScheduledJob.id == job_id))
        return result.scalar_one()


async def _count_pending_outbound(tenant_id: uuid.UUID) -> int:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        result = await session.execute(
            sa.select(sa.func.count())
            .select_from(Message)
            .where(
                Message.direction == MessageDirection.OUTBOUND,
                Message.status == MessageStatus.PENDING,
            )
        )
        return int(result.scalar_one())


async def test_reminder_cron_dispatches_due_jobs(
    two_tenants_with_channels: dict[str, dict[str, Any]],
):
    info = two_tenants_with_channels["a"]
    job_id = await _seed_scheduled(
        tenant_info=info,
        template="reminder_1h",
        run_at=datetime.now(UTC) - timedelta(minutes=1),  # already due
    )

    sm = get_sessionmaker()
    await _process_pending(sm)

    job = await _read_job(info["tenant_id"], job_id)
    assert job.status is ScheduledJobStatus.SENT
    # The notification.send_template tool wrote a pending outbound row that
    # the outbound dispatcher would drain on the next tick.
    assert await _count_pending_outbound(info["tenant_id"]) == 1


async def test_reminder_cron_skips_future_jobs(
    two_tenants_with_channels: dict[str, dict[str, Any]],
):
    info = two_tenants_with_channels["a"]
    job_id = await _seed_scheduled(
        tenant_info=info,
        template="reminder_24h",
        run_at=datetime.now(UTC) + timedelta(hours=23),  # not yet due
    )

    sm = get_sessionmaker()
    await _process_pending(sm)

    job = await _read_job(info["tenant_id"], job_id)
    assert job.status is ScheduledJobStatus.PENDING
    assert await _count_pending_outbound(info["tenant_id"]) == 0


async def test_reminder_cron_isolation_two_tenants(
    two_tenants_with_channels: dict[str, dict[str, Any]],
):
    info_a = two_tenants_with_channels["a"]
    info_b = two_tenants_with_channels["b"]
    past = datetime.now(UTC) - timedelta(minutes=1)
    a_job = await _seed_scheduled(tenant_info=info_a, template="reminder_1h", run_at=past)
    b_job = await _seed_scheduled(tenant_info=info_b, template="reminder_1h", run_at=past)

    sm = get_sessionmaker()
    await _process_pending(sm)

    a = await _read_job(info_a["tenant_id"], a_job)
    b = await _read_job(info_b["tenant_id"], b_job)
    assert a.status is ScheduledJobStatus.SENT
    assert b.status is ScheduledJobStatus.SENT
    # Each tenant has exactly one pending outbound row — no cross-tenant
    # bleed.
    assert await _count_pending_outbound(info_a["tenant_id"]) == 1
    assert await _count_pending_outbound(info_b["tenant_id"]) == 1
