"""Block H: no_show_scrape cron — TZ window guard + skip flow.

A live end-to-end of the scrape would require a fake AgendaPro
transport — those tests live behind the ``requires_browserbase``
mark. Here we exercise the time-of-day window helper + the no-creds
skip flow.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from nexus_worker.streams.no_show_scrape_cron import (
    LOCAL_HOUR_TARGET,
    _is_local_window,
)

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    ScheduledJob,
    Tenant,
    TenantPlan,
    TenantStatus,
)


def test_is_local_window_true_at_target_hour():
    # 22:00 in America/Santiago is 01:00 UTC (winter offset). Compute back.
    fake_local = datetime(2026, 5, 9, LOCAL_HOUR_TARGET, 30, tzinfo=UTC)
    # Convert from naive UTC at any time and pass corresponding TZ.
    assert _is_local_window(fake_local, "UTC") is True


def test_is_local_window_false_at_other_hour():
    fake_local = datetime(2026, 5, 9, LOCAL_HOUR_TARGET - 1, 30, tzinfo=UTC)
    assert _is_local_window(fake_local, "UTC") is False


def test_is_local_window_falls_back_to_utc_for_invalid_tz():
    # Bogus TZ should not crash; fallback defaults to UTC.
    fake_local = datetime(2026, 5, 9, LOCAL_HOUR_TARGET, 0, tzinfo=UTC)
    assert _is_local_window(fake_local, "Mars/Olympus") is True


@pytest.mark.asyncio
async def test_cron_skips_tenants_outside_window(  # type: ignore[no-untyped-def]
    db_session, monkeypatch
):
    from nexus_worker.streams import no_show_scrape_cron as cron

    tid = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tid,
            name="NS",
            slug=f"ns-{tid.hex[:6]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
            timezone="UTC",
        )
    )
    await db_session.commit()

    monkeypatch.setattr(cron, "_is_local_window", lambda *_a, **_kw: False)

    sm = get_sessionmaker()
    await cron._process_pending(sm)

    async with sm() as session, tenant_scoped_session(session, tid):
        rows = await session.execute(sa.select(sa.func.count(ScheduledJob.id)))
        assert rows.scalar_one() == 0


@pytest.mark.asyncio
async def test_cron_skips_tenants_without_agendapro_inside_window(db_session, monkeypatch):
    from nexus_worker.streams import no_show_scrape_cron as cron

    tid = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tid,
            name="NS2",
            slug=f"ns2-{tid.hex[:6]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
            timezone="UTC",
        )
    )
    await db_session.commit()
    monkeypatch.setattr(cron, "_is_local_window", lambda *_a, **_kw: True)

    sm = get_sessionmaker()
    await cron._process_pending(sm)

    async with sm() as session, tenant_scoped_session(session, tid):
        rows = await session.execute(sa.select(sa.func.count(ScheduledJob.id)))
        assert rows.scalar_one() == 0
