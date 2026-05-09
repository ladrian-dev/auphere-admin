"""Block H: health_check cron — auto-seed + idempotency.

The full happy path (dispatch + persist + reschedule) lives in
``test_health_check_cron_run.py`` (would require a fake AgendaPro
transport — gated by ``requires_browserbase`` markers). These tests
exercise the seeding logic + the no-creds skip.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from cryptography.fernet import Fernet

from nexus_api.config import get_settings
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    ScheduledJob,
    ScheduledJobKind,
    ScheduledJobStatus,
    Tenant,
    TenantCredentials,
    TenantPlan,
    TenantStatus,
)

pytestmark = pytest.mark.asyncio


async def _seed_tenant_with_agendapro(db_session) -> uuid.UUID:
    tid = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tid,
            name=f"HC {tid.hex[:6]}",
            slug=f"hc-{tid.hex[:6]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
        )
    )
    await db_session.commit()

    sm = get_sessionmaker()
    fernet = Fernet(get_settings().fernet_key.encode())
    async with sm() as session, tenant_scoped_session(session, tid):
        session.add(
            TenantCredentials(
                tenant_id=tid,
                integration="agendapro",
                encrypted_payload=fernet.encrypt(b'{"login":"x","password":"y","context_id":"c"}'),
            )
        )
        await session.commit()
    return tid


async def _seed_tenant_no_agendapro(db_session) -> uuid.UUID:
    tid = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tid,
            name=f"HC {tid.hex[:6]}",
            slug=f"hc-{tid.hex[:6]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
        )
    )
    await db_session.commit()
    return tid


async def test_cron_auto_seeds_health_check_job_when_creds_present(db_session, monkeypatch):
    """Without an explicit job + creds present, a PENDING job appears."""
    from nexus_worker.streams import health_check_cron as cron

    tid = await _seed_tenant_with_agendapro(db_session)

    # Stub out the dispatch — we only assert the seed path.
    async def fake_run(session, tenant_id, *, actor):
        from datetime import UTC, datetime

        from nexus_api.services.agendapro_health import HealthCheckResult

        return HealthCheckResult(
            healthy=True,
            relogin_attempted=False,
            relogin_succeeded=False,
            needs_reauth=False,
            checked_at=datetime.now(UTC),
            notes=None,
            new_context_id_persisted=False,
            audit_log_id=None,
        )

    monkeypatch.setattr(cron, "run_agendapro_health_check", fake_run)

    sm = get_sessionmaker()
    await cron._process_pending(sm)

    async with sm() as session, tenant_scoped_session(session, tid):
        rows = await session.execute(sa.select(ScheduledJob))
        jobs = list(rows.scalars())
        # One SENT (the seeded + dispatched job) + one PENDING (the next-week reschedule).
        statuses = sorted(j.status.value for j in jobs)
        kinds = {j.kind for j in jobs}
        assert kinds == {ScheduledJobKind.HEALTH_CHECK}
        assert ScheduledJobStatus.PENDING.value in statuses
        assert ScheduledJobStatus.SENT.value in statuses


async def test_cron_skips_tenants_without_agendapro(db_session):
    from nexus_worker.streams import health_check_cron as cron

    tid = await _seed_tenant_no_agendapro(db_session)
    sm = get_sessionmaker()
    await cron._process_pending(sm)

    async with sm() as session, tenant_scoped_session(session, tid):
        rows = await session.execute(sa.select(sa.func.count(ScheduledJob.id)))
        assert rows.scalar_one() == 0


async def test_cron_does_not_re_seed_when_pending_job_exists(db_session, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from nexus_worker.streams import health_check_cron as cron

    tid = await _seed_tenant_with_agendapro(db_session)

    # Pre-existing PENDING job dated in the future — auto-seed must NOT add a duplicate.
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tid):
        session.add(
            ScheduledJob(
                tenant_id=tid,
                kind=ScheduledJobKind.HEALTH_CHECK,
                run_at=datetime.now(UTC) + timedelta(days=3),
                payload={"seeded_by": "fixture"},
                status=ScheduledJobStatus.PENDING,
            )
        )
        await session.commit()

    # The future-dated job won't be picked up by the dispatcher (run_at > now);
    # auto-seed must noop.
    async def fake_run(session, tenant_id, *, actor):
        raise AssertionError("dispatch must not run — no due job")

    monkeypatch.setattr(cron, "run_agendapro_health_check", fake_run)

    await cron._process_pending(sm)

    async with sm() as session, tenant_scoped_session(session, tid):
        rows = await session.execute(sa.select(sa.func.count(ScheduledJob.id)))
        assert rows.scalar_one() == 1  # still just the fixture job
