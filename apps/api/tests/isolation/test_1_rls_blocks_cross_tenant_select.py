"""Garantía 1 — Postgres RLS.

Two tenants insert agent_configs each. From a session scoped to tenant A, we
should see only A's rows. From an unscoped session, we should see zero rows
(fail-closed when app.tenant_id is empty).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text

from nexus_api.db.models import AgentConfig, AgentConfigStatus

from .conftest import set_tenant

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def _make_config(session, tenant_id, prompt):
    config = AgentConfig(
        tenant_id=tenant_id,
        version=1,
        status=AgentConfigStatus.STAGED,
        system_prompt_rendered=prompt,
    )
    session.add(config)
    await session.flush()
    return config


async def test_rls_blocks_cross_tenant_select(db_session, tenants_ab):
    a, b = tenants_ab["a"], tenants_ab["b"]

    async with db_session.begin():
        await set_tenant(db_session, a)
        await _make_config(db_session, a, "A prompt")

    async with db_session.begin():
        await set_tenant(db_session, b)
        await _make_config(db_session, b, "B prompt")

    # Scoped to A: see only A's row
    async with db_session.begin():
        await set_tenant(db_session, a)
        rows = (await db_session.execute(select(AgentConfig))).scalars().all()
        assert len(rows) == 1
        assert rows[0].tenant_id == a
        assert rows[0].system_prompt_rendered == "A prompt"


async def test_rls_blocks_cross_tenant_update(db_session, tenants_ab):
    a, b = tenants_ab["a"], tenants_ab["b"]

    async with db_session.begin():
        await set_tenant(db_session, a)
        cfg_a = await _make_config(db_session, a, "A original")

    async with db_session.begin():
        await set_tenant(db_session, b)
        # B tries to update A's row — RLS makes the row invisible, the update
        # affects 0 rows, no leak.
        result = await db_session.execute(
            AgentConfig.__table__.update()
            .where(AgentConfig.id == cfg_a.id)
            .values(system_prompt_rendered="hacked by B")
        )
        assert result.rowcount == 0

    async with db_session.begin():
        await set_tenant(db_session, a)
        cfg = await db_session.get(AgentConfig, cfg_a.id)
        assert cfg is not None
        assert cfg.system_prompt_rendered == "A original"


async def test_rls_unscoped_session_sees_nothing(db_session, tenants_ab):
    a = tenants_ab["a"]
    async with db_session.begin():
        await set_tenant(db_session, a)
        await _make_config(db_session, a, "A row")

    async with db_session.begin():
        # Switch to nexus_app (so RLS applies) but DON'T set app.tenant_id.
        # Policy: tenant_id = NULLIF('','')::uuid → tenant_id = NULL → false.
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        rows = (await db_session.execute(select(AgentConfig))).scalars().all()
        assert rows == []
