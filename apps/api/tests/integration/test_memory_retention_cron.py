"""Smoke coverage for the agent_memory_versions retention sweep.

The cron is the only consumer of the audit table — without it, every
``str_replace`` / ``insert`` / ``delete`` accumulates forever. This
test seeds version rows with a fake ``versioned_at`` straddling the
retention window and verifies the sweep deletes the stale half while
preserving the fresh half.
"""

from __future__ import annotations

import uuid

import pytest
from nexus_worker.streams.memory_versions_retention import _drain_once
from sqlalchemy import text

pytestmark = [pytest.mark.asyncio]


async def _seed_version(
    db_session,
    *,
    tenant_id: uuid.UUID,
    days_ago: int,
    operation: str,
) -> None:
    """Insert a row directly into ``agent_memory_versions`` with a
    backdated ``versioned_at``. We bypass the trigger because we want
    deterministic timestamps, not whatever ``now()`` is on the test DB.
    """
    await db_session.execute(
        text(
            "INSERT INTO agent_memory_versions "
            "(memory_id, tenant_id, customer_id, path, content, operation, versioned_at) "
            "VALUES (gen_random_uuid(), :tid, NULL, '/memories/tenant/x.md', "
            "'snapshot', :op, now() - make_interval(days => :days))"
        ),
        {"tid": str(tenant_id), "op": operation, "days": days_ago},
    )


async def test_drain_clears_rows_past_window(db_session, monkeypatch) -> None:
    from nexus_api.db.models import Tenant, TenantPlan

    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(id=tenant_id, name="Mem", slug=f"mem-{tenant_id.hex[:6]}", plan=TenantPlan.PRO)
    )
    await db_session.commit()

    # Insert as DB owner — bypass RLS. Tests use the same role as
    # alembic so this works.
    async with db_session.begin():
        for days_ago, op in [(35, "insert"), (40, "update"), (45, "delete")]:
            await _seed_version(db_session, tenant_id=tenant_id, days_ago=days_ago, operation=op)
        for days_ago, op in [(1, "insert"), (10, "update"), (29, "delete")]:
            await _seed_version(db_session, tenant_id=tenant_id, days_ago=days_ago, operation=op)

    # Force the default 30-day window via env (also asserts the env
    # parsing path is exercised).
    monkeypatch.setenv("NEXUS_MEMORY_RETENTION_DAYS", "30")

    deleted = await _drain_once()
    assert deleted == 3

    async with db_session.begin():
        remaining = (
            await db_session.execute(text("SELECT count(*) FROM agent_memory_versions"))
        ).scalar_one()
    assert remaining == 3


async def test_retention_days_floor_at_1(monkeypatch) -> None:
    """Pathological env value (negative / zero / garbage) clamps to a
    safe floor so an operator typo cannot blow the audit trail."""
    from nexus_worker.streams.memory_versions_retention import _retention_days

    monkeypatch.setenv("NEXUS_MEMORY_RETENTION_DAYS", "0")
    assert _retention_days() == 1

    monkeypatch.setenv("NEXUS_MEMORY_RETENTION_DAYS", "-7")
    assert _retention_days() == 1

    monkeypatch.setenv("NEXUS_MEMORY_RETENTION_DAYS", "not-a-number")
    assert _retention_days() == 30
