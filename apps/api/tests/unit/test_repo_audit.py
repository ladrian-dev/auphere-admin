import pytest
from sqlalchemy import select, text

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import AuditLog
from nexus_api.repositories import AuditRepository

pytestmark = pytest.mark.asyncio


async def test_record_writes_with_tenant_from_context(db_session, seed_tenants):
    tid = seed_tenants["a"]
    repo = AuditRepository(db_session)
    with tenant_context(tid):
        async with db_session.begin():
            await db_session.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)}
            )
            await db_session.execute(text("SET LOCAL ROLE nexus_app"))
            entry = await repo.record(
                actor="admin:abc", action="agent_config.promote", target="config-123"
            )
            assert entry.tenant_id == tid
            assert entry.actor == "admin:abc"
            stmt = select(AuditLog).where(AuditLog.target == "config-123")
            row = (await db_session.execute(stmt)).scalar_one_or_none()
            assert row is not None


async def test_record_persists_before_after(db_session, seed_tenants):
    tid = seed_tenants["a"]
    repo = AuditRepository(db_session)
    with tenant_context(tid):
        async with db_session.begin():
            await db_session.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)}
            )
            await db_session.execute(text("SET LOCAL ROLE nexus_app"))
            entry = await repo.record(
                actor="x",
                action="agent_config.stage",
                target="t",
                before={"v": 1},
                after={"v": 2},
            )
            assert entry.before_json == {"v": 1}
            assert entry.after_json == {"v": 2}
