"""Spec 024 · T-ISO: the list a partner writes stays in the tenant of the
scope, and the route never takes a tenant or a sender from the caller.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import AgentConfig
from nexus_api.main import app
from tests.unit.test_endpoint_console_agent_tools import SETTINGS, _stage_and_publish

pytestmark = pytest.mark.asyncio


async def _admin_access(db_session, tenant_id) -> list[dict]:
    async with tenant_scoped_session(db_session, tenant_id):
        rows = (
            await db_session.scalars(
                sa.select(AgentConfig.policies).where(AgentConfig.tenant_id == tenant_id)
            )
        ).all()
    return [(p or {}).get("admin_access") for p in rows]


async def test_the_list_of_a_never_touches_b(client, console_world, db_session) -> None:
    a, b = console_world["a"], console_world["b"]
    await _stage_and_publish(client, a)
    await _stage_and_publish(client, b)

    saved = await client.put(
        f"/console/clients/{a['ref']}/agent/settings",
        headers=a["headers"](),
        json={
            "settings": SETTINGS,
            "audience": {"mode": "list", "numbers": [{"phone": "+34666261967"}]},
        },
    )
    assert saved.status_code == 200, saved.text

    assert all(x is None for x in await _admin_access(db_session, b["tenant_id"]))
    assert any(x for x in await _admin_access(db_session, a["tenant_id"]))

    # B cannot read A's list through its own scope either.
    crossed = await client.get(
        f"/console/clients/{a['ref']}/agent/settings", headers=b["headers"]()
    )
    assert crossed.status_code == 404


async def test_the_settings_route_takes_no_tenant_and_no_sender() -> None:
    schema = app.openapi()
    spec = schema["paths"]["/console/clients/{ref}/agent/settings"]
    prohibidos = {"tenant_id", "partner_id", "sender", "user_id", "wa_id"}
    for method, op in spec.items():
        if method not in {"get", "put"}:
            continue
        for prm in op.get("parameters", []):
            assert prm["name"] not in prohibidos, f"{method} acepta {prm['name']}"
    body = spec["put"]["requestBody"]["content"]["application/json"]["schema"]
    ref = body.get("$ref", "").rsplit("/", 1)[-1]
    props = set(schema["components"]["schemas"][ref]["properties"])
    # Spec 025 adds ``payment_review``; still no tenant nor sender.
    assert props == {"settings", "audience", "payment_review"}
