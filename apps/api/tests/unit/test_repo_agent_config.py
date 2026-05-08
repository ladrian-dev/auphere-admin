import pytest
from sqlalchemy import text

from nexus_api.core.errors import AgentConfigConflict, IsolationViolation
from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import AgentConfigStatus
from nexus_api.repositories import AgentConfigRepository

pytestmark = pytest.mark.asyncio


async def _scope(session, tid):
    """Set both contextvar and SET LOCAL for the running session."""
    await session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)})
    await session.execute(text("SET LOCAL ROLE nexus_app"))


async def test_create_staged_assigns_version_1(db_session, seed_tenants):
    tid = seed_tenants["a"]
    repo = AgentConfigRepository(db_session)
    with tenant_context(tid):
        async with db_session.begin():
            await _scope(db_session, tid)
            config = await repo.create_staged(
                system_prompt_rendered="prompt v1",
                channels=[],
                tools=[],
                policies={},
                seed_template_ref=None,
                kg_schema_id=None,
                created_by=None,
            )
            assert config.version == 1
            assert config.status == AgentConfigStatus.STAGED


async def test_create_staged_increments_version(db_session, seed_tenants):
    tid = seed_tenants["a"]
    repo = AgentConfigRepository(db_session)
    with tenant_context(tid):
        async with db_session.begin():
            await _scope(db_session, tid)
            v1 = await repo.create_staged(
                system_prompt_rendered="v1",
                channels=[],
                tools=[],
                policies={},
                seed_template_ref=None,
                kg_schema_id=None,
                created_by=None,
            )
            v2 = await repo.create_staged(
                system_prompt_rendered="v2",
                channels=[],
                tools=[],
                policies={},
                seed_template_ref=None,
                kg_schema_id=None,
                created_by=None,
            )
            assert v1.version == 1
            assert v2.version == 2


async def test_promote_makes_active_and_archives_previous(db_session, seed_tenants):
    tid = seed_tenants["a"]
    repo = AgentConfigRepository(db_session)
    with tenant_context(tid):
        async with db_session.begin():
            await _scope(db_session, tid)
            v1 = await repo.create_staged(
                system_prompt_rendered="v1",
                channels=[],
                tools=[],
                policies={},
                seed_template_ref=None,
                kg_schema_id=None,
                created_by=None,
            )
            v2 = await repo.create_staged(
                system_prompt_rendered="v2",
                channels=[],
                tools=[],
                policies={},
                seed_template_ref=None,
                kg_schema_id=None,
                created_by=None,
            )
            await repo.promote(v1.version, promoted_by="alice")
            await repo.promote(v2.version, promoted_by="bob")
            await db_session.refresh(v1)
            await db_session.refresh(v2)
            assert v1.status == AgentConfigStatus.ARCHIVED
            assert v2.status == AgentConfigStatus.ACTIVE
            assert v2.promoted_by == "bob"


async def test_promote_unknown_version_raises(db_session, seed_tenants):
    tid = seed_tenants["a"]
    repo = AgentConfigRepository(db_session)
    with tenant_context(tid):
        async with db_session.begin():
            await _scope(db_session, tid)
            with pytest.raises(AgentConfigConflict):
                await repo.promote(999, promoted_by="x")


async def test_promote_idempotent_for_active(db_session, seed_tenants):
    tid = seed_tenants["a"]
    repo = AgentConfigRepository(db_session)
    with tenant_context(tid):
        async with db_session.begin():
            await _scope(db_session, tid)
            v1 = await repo.create_staged(
                system_prompt_rendered="v1",
                channels=[],
                tools=[],
                policies={},
                seed_template_ref=None,
                kg_schema_id=None,
                created_by=None,
            )
            await repo.promote(v1.version, promoted_by="alice")
            again = await repo.promote(v1.version, promoted_by="bob")
            assert again.status == AgentConfigStatus.ACTIVE


async def test_rollback_restores_archived_version(db_session, seed_tenants):
    tid = seed_tenants["a"]
    repo = AgentConfigRepository(db_session)
    with tenant_context(tid):
        async with db_session.begin():
            await _scope(db_session, tid)
            v1 = await repo.create_staged(
                system_prompt_rendered="v1",
                channels=[],
                tools=[],
                policies={},
                seed_template_ref=None,
                kg_schema_id=None,
                created_by=None,
            )
            v2 = await repo.create_staged(
                system_prompt_rendered="v2",
                channels=[],
                tools=[],
                policies={},
                seed_template_ref=None,
                kg_schema_id=None,
                created_by=None,
            )
            await repo.promote(v1.version, promoted_by="a")
            await repo.promote(v2.version, promoted_by="b")
            await repo.rollback(v1.version, promoted_by="c")
            await db_session.refresh(v1)
            await db_session.refresh(v2)
            assert v1.status == AgentConfigStatus.ACTIVE
            assert v2.status == AgentConfigStatus.ARCHIVED


async def test_rollback_unknown_raises(db_session, seed_tenants):
    tid = seed_tenants["a"]
    repo = AgentConfigRepository(db_session)
    with tenant_context(tid):
        async with db_session.begin():
            await _scope(db_session, tid)
            with pytest.raises(AgentConfigConflict):
                await repo.rollback(42, promoted_by="x")


async def test_get_active_returns_only_active(db_session, seed_tenants):
    tid = seed_tenants["a"]
    repo = AgentConfigRepository(db_session)
    with tenant_context(tid):
        async with db_session.begin():
            await _scope(db_session, tid)
            v1 = await repo.create_staged(
                system_prompt_rendered="v1",
                channels=[],
                tools=[],
                policies={},
                seed_template_ref=None,
                kg_schema_id=None,
                created_by=None,
            )
            assert await repo.get_active() is None
            await repo.promote(v1.version, promoted_by="x")
            active = await repo.get_active()
            assert active is not None
            assert active.id == v1.id


async def test_repo_methods_require_tenant_context(db_session, seed_tenants):
    """Repos NEVER accept tenant_id as an argument and require ctx be set."""
    repo = AgentConfigRepository(db_session)
    # No tenant_context — calling list() should raise IsolationViolation
    # because require_current_tenant() short-circuits.
    with pytest.raises(IsolationViolation):
        await repo.list_all()


async def test_unique_version_per_tenant(db_session, seed_tenants):
    """UNIQUE(tenant_id, version) enforced — two tenants can both have version 1."""
    a, b = seed_tenants["a"], seed_tenants["b"]
    repo_a = AgentConfigRepository(db_session)
    with tenant_context(a):
        async with db_session.begin():
            await _scope(db_session, a)
            await repo_a.create_staged(
                system_prompt_rendered="A v1",
                channels=[],
                tools=[],
                policies={},
                seed_template_ref=None,
                kg_schema_id=None,
                created_by=None,
            )

    repo_b = AgentConfigRepository(db_session)
    with tenant_context(b):
        async with db_session.begin():
            await _scope(db_session, b)
            v1_b = await repo_b.create_staged(
                system_prompt_rendered="B v1",
                channels=[],
                tools=[],
                policies={},
                seed_template_ref=None,
                kg_schema_id=None,
                created_by=None,
            )
            assert v1_b.version == 1
