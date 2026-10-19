"""Spec 037 — the client's capabilities, from the operator panel.

The same reading and the same one-change-per-call write as the partner
console (spec 017 R5), on the client's own tenant scope, signed by the
operator in the audit.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.models import AuditLog

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _operator(db_session) -> tuple[str, str]:
    from nexus_api.services import operator_identity

    email = f"op-{uuid.uuid4().hex[:6]}@auphere.test"
    account = await operator_identity.create_account(
        db_session, email=email, password="x" * 16, role="admin"
    )
    await db_session.commit()
    return str(account.id), email


async def test_the_panel_reads_and_switches_a_capability(
    client, console_world, admin_headers, db_session
) -> None:
    a = console_world["a"]
    url = f"/admin/tenants/{a['tenant_id']}/capabilities"

    res = await client.get(f"{url}?all=true", headers=admin_headers)
    assert res.status_code == 200, res.text
    items = [i for g in res.json()["groups"] for i in g["items"]]
    tool = next(i for i in items if i["kind"] == "tool" and i["activatable"] and not i["enabled"])
    # Business names, as in the console.
    assert tool["business_name"] and tool["business_name"] != tool["key"]

    op, email = await _operator(db_session)
    body = {"key": tool["key"], "kind": "tool", "enabled": True}
    missing = await client.put(url, headers=admin_headers, json=body)
    assert missing.status_code == 400

    done = await client.put(url, headers={**admin_headers, "X-Operator-Id": op}, json=body)
    assert done.status_code == 200, done.text
    assert done.json()["capability"]["enabled"] is True

    again = await client.get(f"{url}?all=true", headers=admin_headers)
    after = {i["key"]: i for g in again.json()["groups"] for i in g["items"]}
    assert after[tool["key"]]["enabled"] is True

    row = (
        (
            await db_session.execute(
                sa.select(AuditLog)
                .where(AuditLog.target == f"capability:{tool['key']}")
                .order_by(AuditLog.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    assert row is not None
    assert row.actor == f"operator:{email}"


async def test_capabilities_need_the_admin_token(client, console_world) -> None:
    a = console_world["a"]
    res = await client.get(f"/admin/tenants/{a['tenant_id']}/capabilities")
    assert res.status_code in (401, 403)
