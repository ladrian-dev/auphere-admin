import pytest
from sqlalchemy import text

from nexus_api.core.errors import AgentConfigConflict
from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import AgentConfigStatus
from nexus_api.services import AgentConfigService

pytestmark = pytest.mark.asyncio


async def _scope(s, tid):
    await s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)})
    await s.execute(text("SET LOCAL ROLE nexus_app"))


async def test_stage_records_audit(db_session, seed_tenants):
    tid = seed_tenants["a"]
    with tenant_context(tid):
        async with db_session.begin():
            await _scope(db_session, tid)
            svc = AgentConfigService(db_session)
            cfg = await svc.stage_new_version(
                actor="alice",
                system_prompt_rendered="prompt",
                channels=[],
                tools=["booking.check_availability"],
                policies={},
            )
            assert cfg.version == 1
            assert cfg.status == AgentConfigStatus.STAGED


async def test_stage_rejects_unknown_tool(db_session, seed_tenants):
    tid = seed_tenants["a"]
    with tenant_context(tid):
        async with db_session.begin():
            await _scope(db_session, tid)
            svc = AgentConfigService(db_session)
            with pytest.raises(AgentConfigConflict, match="not in catalog"):
                await svc.stage_new_version(
                    actor="alice",
                    system_prompt_rendered="prompt",
                    channels=[],
                    tools=["this.does.not.exist"],
                    policies={},
                )


async def test_promote_then_rollback_swaps_active(db_session, seed_tenants):
    tid = seed_tenants["a"]
    with tenant_context(tid):
        async with db_session.begin():
            await _scope(db_session, tid)
            svc = AgentConfigService(db_session)
            v1 = await svc.stage_new_version(
                actor="a",
                system_prompt_rendered="v1",
                channels=[],
                tools=[],
                policies={},
            )
            v2 = await svc.stage_new_version(
                actor="a",
                system_prompt_rendered="v2",
                channels=[],
                tools=[],
                policies={},
            )
            await svc.promote(v1.version, actor="a")
            await svc.promote(v2.version, actor="a")
            await db_session.refresh(v2)
            assert v2.status == AgentConfigStatus.ACTIVE
            await svc.rollback(v1.version, actor="a")
            await db_session.refresh(v1)
            await db_session.refresh(v2)
            assert v1.status == AgentConfigStatus.ACTIVE
            assert v2.status == AgentConfigStatus.ARCHIVED


async def test_rollback_to_active_version_raises(db_session, seed_tenants):
    tid = seed_tenants["a"]
    with tenant_context(tid):
        async with db_session.begin():
            await _scope(db_session, tid)
            svc = AgentConfigService(db_session)
            v1 = await svc.stage_new_version(
                actor="a",
                system_prompt_rendered="v1",
                channels=[],
                tools=[],
                policies={},
            )
            await svc.promote(v1.version, actor="a")
            with pytest.raises(AgentConfigConflict, match="already active"):
                await svc.rollback(v1.version, actor="a")
