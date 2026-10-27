"""Spec 047, T003 — ``jobs-consumer`` contra Postgres (research D43).

Las pruebas sin base del consumidor están en
``apps/worker/tests/unit/test_jobs_consumer.py``. Aquí, la misma ronda con la
fila de verdad (``DbJobStore``): la API crea y encola, el worker lo corre, y lo
que queda en ``jobs`` es lo que la consola leerá.

- un trabajo pasa por ``running`` con su progreso por bloques y acaba ``done``;
- un manejador fuera de plazo deja ``failed``/``timeout``;
- la entrada de una réplica que murió con el trabajo en marcha se reclama: no
  se corre otra vez, y la caducidad lo da por ``timeout``.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.jobs import (
    JOBS_GROUP,
    DbJobStore,
    JobContext,
    JobRegistry,
    drain_once,
    reclaim_once,
)
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Job, Tenant, TenantPlan, TenantStatus
from nexus_api.services import jobs

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def tenant(db_session: AsyncSession) -> uuid.UUID:
    tid = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tid,
            name="Café Origen",
            slug=f"jobs-c-{tid.hex[:8]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
        )
    )
    await db_session.commit()
    return tid


async def _submit(db_session: AsyncSession, tenant_id: uuid.UUID, redis: Any, kind: str) -> Job:
    async with tenant_scoped_session(db_session, tenant_id):
        job = await jobs.create_job(db_session, kind=kind)
    await jobs.enqueue_job(redis, job)
    return job


async def _row(db_session: AsyncSession, tenant_id: uuid.UUID, job_id: uuid.UUID) -> Job:
    async with tenant_scoped_session(db_session, tenant_id):
        job = await jobs.get_job(db_session, job_id)
    assert job is not None
    return job


async def test_the_worker_runs_a_job_to_done(
    db_session: AsyncSession, tenant: uuid.UUID, fake_redis: Any
) -> None:
    job = await _submit(db_session, tenant, fake_redis, "agent_draft")
    seen: list[str] = []

    async def draft(ctx: JobContext) -> dict[str, Any]:
        seen.append(ctx.kind)
        assert await ctx.progress(step="purpose", block={"key": "purpose", "value": "Citas"})
        return {"draft_revision": 1}

    registry = JobRegistry()
    registry.register("agent_draft", draft, timeout_s=5)
    assert await drain_once(fake_redis, registry=registry, store=DbJobStore()) == 1

    row = await _row(db_session, tenant, job.id)
    assert seen == ["agent_draft"]
    assert row.status == "done"
    assert row.result == {"draft_revision": 1}
    assert row.progress == {"step": "purpose", "blocks": [{"key": "purpose", "value": "Citas"}]}
    assert row.started_at is not None
    assert row.finished_at is not None
    assert (await fake_redis.xpending(jobs.JOBS_STREAM, JOBS_GROUP))["pending"] == 0


async def test_a_handler_past_its_deadline_leaves_the_row_failed_timeout(
    db_session: AsyncSession, tenant: uuid.UUID, fake_redis: Any
) -> None:
    job = await _submit(db_session, tenant, fake_redis, "tests")

    async def slow(ctx: JobContext) -> None:
        await asyncio.sleep(10)

    registry = JobRegistry()
    registry.register("tests", slow, timeout_s=0.05)
    await drain_once(fake_redis, registry=registry, store=DbJobStore())

    row = await _row(db_session, tenant, job.id)
    assert (row.status, row.error_code) == ("failed", "timeout")


async def test_a_dead_replicas_running_job_is_reclaimed_and_expires(
    db_session: AsyncSession, tenant: uuid.UUID, fake_redis: Any
) -> None:
    job = await _submit(db_session, tenant, fake_redis, "publish")
    # A replica read the entry, started the job and died: no heartbeat since.
    await fake_redis.xgroup_create(jobs.JOBS_STREAM, JOBS_GROUP, id="0", mkstream=True)
    await fake_redis.xreadgroup(
        groupname=JOBS_GROUP, consumername="c-dead", streams={jobs.JOBS_STREAM: ">"}, count=1
    )
    async with tenant_scoped_session(db_session, tenant):
        await jobs.start_job(db_session, job.id)
        await db_session.execute(
            sa.update(Job)
            .where(Job.id == job.id)
            .values(updated_at=sa.func.now() - jobs.RUNNING_STALE_AFTER * 2)
        )
    runs: list[int] = []

    async def publish(ctx: JobContext) -> None:  # pragma: no cover - must not run
        runs.append(1)

    registry = JobRegistry()
    registry.register("publish", publish, timeout_s=5)
    reclaimed = await reclaim_once(fake_redis, registry=registry, store=DbJobStore(), min_idle_ms=0)

    assert reclaimed == 1
    assert runs == []  # never run twice
    row = await _row(db_session, tenant, job.id)
    assert (row.status, row.error_code) == ("failed", "timeout")
    assert (await fake_redis.xpending(jobs.JOBS_STREAM, JOBS_GROUP))["pending"] == 0
