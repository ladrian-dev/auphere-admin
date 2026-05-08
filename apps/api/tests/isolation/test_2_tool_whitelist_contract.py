"""Garantía 2 — Tool whitelist por agente.

Block C implements the runtime enforcement (LangGraph filtering before passing
tools to the LLM). Block B verifies the DATA contract that the runtime relies
on:

- agent_config.tools is the only source of truth (no global default in DB).
- AgentConfigService.stage_new_version() rejects tools not in tool_catalog.
- Tools are stored verbatim and queryable per tenant.

This is a structural test: when Bloque C builds, its runtime test re-uses
exactly this whitelist semantic. Currently the runtime check itself isn't
written — it does NOT exist yet — so this test file ensures the surrounding
plumbing is correct.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from nexus_api.core.errors import AgentConfigConflict
from nexus_api.core.tenant_context import tenant_context
from nexus_api.services import AgentConfigService

from .conftest import set_tenant

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def _scope(s, tid):
    await s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)})
    await s.execute(text("SET LOCAL ROLE nexus_app"))


async def test_tool_whitelist_persisted_per_tenant(db_session, tenants_ab):
    a, b = tenants_ab["a"], tenants_ab["b"]

    with tenant_context(a):
        async with db_session.begin():
            await set_tenant(db_session, a)
            await AgentConfigService(db_session).stage_new_version(
                actor="x",
                system_prompt_rendered="A",
                channels=[],
                tools=["booking.check_availability", "queue.join_queue"],
                policies={},
            )

    with tenant_context(b):
        async with db_session.begin():
            await set_tenant(db_session, b)
            await AgentConfigService(db_session).stage_new_version(
                actor="x",
                system_prompt_rendered="B",
                channels=[],
                tools=["client.get_history"],
                policies={},
            )

    # Read each back from its own scope and confirm whitelists don't leak.
    with tenant_context(a):
        async with db_session.begin():
            await set_tenant(db_session, a)
            cfgs = await AgentConfigService(db_session).list_versions()
            assert len(cfgs) == 1
            assert cfgs[0].tools == [
                "booking.check_availability",
                "queue.join_queue",
            ]

    with tenant_context(b):
        async with db_session.begin():
            await set_tenant(db_session, b)
            cfgs = await AgentConfigService(db_session).list_versions()
            assert len(cfgs) == 1
            assert cfgs[0].tools == ["client.get_history"]


async def test_tool_whitelist_rejects_uncatalogued_entry(db_session, tenants_ab):
    a = tenants_ab["a"]
    with tenant_context(a):
        async with db_session.begin():
            await _scope(db_session, a)
            with pytest.raises(AgentConfigConflict):
                await AgentConfigService(db_session).stage_new_version(
                    actor="x",
                    system_prompt_rendered="A",
                    channels=[],
                    tools=["payment.charge"],  # not in catalog
                    policies={},
                )
