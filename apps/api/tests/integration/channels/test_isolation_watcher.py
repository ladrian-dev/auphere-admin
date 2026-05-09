"""Block H: isolation_watcher — isolation_events → audit_log dedup."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AuditLog,
    IsolationEvent,
    Tenant,
    TenantPlan,
    TenantStatus,
)

pytestmark = pytest.mark.asyncio


async def _seed_tenant(db_session) -> uuid.UUID:
    tid = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tid,
            name=f"W {tid.hex[:6]}",
            slug=f"w-{tid.hex[:6]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
        )
    )
    await db_session.commit()
    return tid


async def _seed_isolation_event(tenant_id: uuid.UUID, metric: str) -> None:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        session.add(IsolationEvent(tenant_id=tenant_id, metric=metric, payload={}))
        await session.commit()


async def test_watcher_emits_one_audit_per_metric_per_hour(db_session):
    from nexus_worker.streams.isolation_watcher import _process

    tid = await _seed_tenant(db_session)
    await _seed_isolation_event(tid, "isolation.tool_whitelist_violation")
    await _seed_isolation_event(tid, "isolation.tool_whitelist_violation")
    await _seed_isolation_event(tid, "isolation.kg_query_unscoped")

    sm = get_sessionmaker()
    await _process(sm)

    async with sm() as session, tenant_scoped_session(session, tid):
        rows = await session.execute(
            sa.select(AuditLog).where(AuditLog.action == "isolation.violation_detected")
        )
        items = list(rows.scalars())
        assert len(items) == 2  # one per metric


async def test_watcher_does_not_double_emit(db_session):
    from nexus_worker.streams.isolation_watcher import _process

    tid = await _seed_tenant(db_session)
    await _seed_isolation_event(tid, "isolation.tool_whitelist_violation")

    sm = get_sessionmaker()
    await _process(sm)
    await _process(sm)

    async with sm() as session, tenant_scoped_session(session, tid):
        count = await session.execute(
            sa.select(sa.func.count(AuditLog.id)).where(
                AuditLog.action == "isolation.violation_detected"
            )
        )
        assert count.scalar_one() == 1


async def test_watcher_isolates_tenants(db_session):
    from nexus_worker.streams.isolation_watcher import _process

    a = await _seed_tenant(db_session)
    b = await _seed_tenant(db_session)
    await _seed_isolation_event(a, "isolation.tool_whitelist_violation")
    # Tenant B has no events.

    sm = get_sessionmaker()
    await _process(sm)

    async with sm() as session, tenant_scoped_session(session, a):
        count_a = (
            await session.execute(
                sa.select(sa.func.count(AuditLog.id)).where(
                    AuditLog.action == "isolation.violation_detected"
                )
            )
        ).scalar_one()
    async with sm() as session, tenant_scoped_session(session, b):
        count_b = (
            await session.execute(
                sa.select(sa.func.count(AuditLog.id)).where(
                    AuditLog.action == "isolation.violation_detected"
                )
            )
        ).scalar_one()
    assert count_a == 1
    assert count_b == 0
