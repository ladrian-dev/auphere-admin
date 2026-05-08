"""Garantía 5 — Prompt rendering isolated.

system_prompt_rendered is persisted per-tenant. Two tenants with different
data should NEVER end up with the same prompt, and the prompt of A must
never contain B's known tokens (and vice versa).

Block B writes the prompts via the service; the runtime in block C reads them
verbatim (no Jinja2 at run-time).
"""

from __future__ import annotations

import pytest

from nexus_api.core.tenant_context import tenant_context
from nexus_api.services import AgentConfigService

from .conftest import set_tenant

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def _stage(session, tid, prompt):
    await set_tenant(session, tid)
    return await AgentConfigService(session).stage_new_version(
        actor="x",
        system_prompt_rendered=prompt,
        channels=[],
        tools=[],
        policies={},
    )


async def test_prompt_does_not_leak_between_tenants(db_session, tenants_ab):
    a, b = tenants_ab["a"], tenants_ab["b"]

    a_prompt = "Eres el agente de Cultor Barber. Barberos: Pedro, Ana."
    b_prompt = "Eres el agente de Otra Barbería. Barberos: Carlos."

    with tenant_context(a):
        async with db_session.begin():
            await _stage(db_session, a, a_prompt)
    with tenant_context(b):
        async with db_session.begin():
            await _stage(db_session, b, b_prompt)

    with tenant_context(a):
        async with db_session.begin():
            await set_tenant(db_session, a)
            cfgs = await AgentConfigService(db_session).list_versions()
            assert len(cfgs) == 1
            assert "Carlos" not in cfgs[0].system_prompt_rendered
            assert "Pedro" in cfgs[0].system_prompt_rendered

    with tenant_context(b):
        async with db_session.begin():
            await set_tenant(db_session, b)
            cfgs = await AgentConfigService(db_session).list_versions()
            assert len(cfgs) == 1
            assert "Pedro" not in cfgs[0].system_prompt_rendered
            assert "Carlos" in cfgs[0].system_prompt_rendered
