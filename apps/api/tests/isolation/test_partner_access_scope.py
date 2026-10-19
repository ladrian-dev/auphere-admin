"""Spec 032 — one partner's modules never reach another partner.

``partners`` carries no RLS on purpose: it is platform data the console gate
reads **before** any scope exists (like ``console_enabled``). The boundary is
the path and the principal: changing A's modules changes what A's people read
and leaves B's byte-identical.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def test_changing_a_leaves_b_untouched(
    client, console_world, admin_headers, db_session
) -> None:
    from nexus_api.services import operator_identity

    a, b = console_world["a"], console_world["b"]
    op = await operator_identity.create_account(
        db_session, email=f"op-{uuid.uuid4().hex[:6]}@auphere.test", password="x" * 16, role="admin"
    )
    await db_session.commit()
    before_b = (await client.get("/console/me", headers=b["headers"]())).json()["modules"]

    res = await client.put(
        f"/admin/partners/{a['partner_id']}/access",
        headers={**admin_headers, "X-Operator-Id": str(op.id)},
        json={"console_enabled": True, "modules": ["usage"]},
    )
    assert res.status_code == 200, res.text

    me_a = (await client.get("/console/me", headers=a["headers"]())).json()
    me_b = (await client.get("/console/me", headers=b["headers"]())).json()
    assert me_a["modules"] == ["usage"]
    assert me_b["modules"] == before_b
    assert "usage" in me_b["modules"] and "panel" in me_b["modules"]
