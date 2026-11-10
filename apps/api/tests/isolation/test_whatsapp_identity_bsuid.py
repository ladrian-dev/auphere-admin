"""Spec 050: WhatsApp identity by BSUID does not cross any boundary.

1. The same BSUID under two tenants is two people (garantía 1).
2. Inside a tenant, a BSUID resolves only to its own row; two people are
   never merged (garantía 8).
3. Attaching a BSUID never changes ``identifier``, the key of the agent's
   thread (garantía 4).
4. No agent tool takes a phone or a BSUID as an argument: the person is the
   server's, never the model's (garantía 8, requisito 2.7).
"""

from __future__ import annotations

import uuid

import pytest
from nexus_worker.persistence.messages import upsert_customer
from sqlalchemy import select

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Customer

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

BSUID = "ES.700000000000000007"


async def _upsert(tid: uuid.UUID, **kw) -> Customer:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tid):
        return await upsert_customer(s, **kw)


async def test_the_same_bsuid_in_two_tenants_is_two_people(tenants_ab):
    a, b = tenants_ab["a"], tenants_ab["b"]
    ca = await _upsert(a, identifier=BSUID, bsuid=BSUID)
    cb = await _upsert(b, identifier=BSUID, bsuid=BSUID)
    assert ca.id != cb.id
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, b):
        rows = (await s.scalars(select(Customer.id).where(Customer.bsuid == BSUID))).all()
    assert rows == [cb.id]


async def test_attaching_a_bsuid_never_moves_the_thread_key(tenants_ab):
    a = tenants_ab["a"]
    c = await _upsert(a, identifier="34688000008", phone="34688000008")
    linked = await _upsert(
        a, identifier="34688000008", phone="34688000008", bsuid="ES.800000000000000008"
    )
    assert linked.id == c.id and linked.identifier == "34688000008"


def test_no_agent_tool_takes_a_bsuid_argument():
    """The agent never names the person: no tool schema carries a BSUID."""
    import json

    from nexus_mcp import build_default_registry
    from nexus_mcp.registry import reset_default_registry

    reset_default_registry()
    reg = build_default_registry()
    forbidden = ("bsuid", "user_id_meta", "wa_id")
    offenders = []
    for tool in reg.get_openai_tools(reg.names()):
        params = json.dumps(tool.get("function", {}).get("parameters", {}))
        hit = [f for f in forbidden if f'"{f}"' in params]
        if hit:
            offenders.append((tool["function"]["name"], hit))
    assert offenders == []
