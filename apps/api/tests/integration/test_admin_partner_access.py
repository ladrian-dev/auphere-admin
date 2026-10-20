"""Spec 032 — Auphere chooses which console views and services a partner has.

GET/PUT /admin/partners/{id}/access, the Companion's switch following its
module, the audit naming the operator, and the console reading the result.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.models import PARTNER_MODULES, PARTNER_NAV_MODULES, AuditLog, Partner

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _operator(db_session) -> str:
    from nexus_api.services import operator_identity

    account = await operator_identity.create_account(
        db_session, email=f"op-{uuid.uuid4().hex[:6]}@auphere.test", password="x" * 16, role="admin"
    )
    await db_session.commit()
    return str(account.id)


def _url(pid) -> str:
    return f"/admin/partners/{pid}/access"


async def test_a_partner_has_every_view_by_default(client, console_world, admin_headers) -> None:
    a = console_world["a"]
    res = await client.get(_url(a["partner_id"]), headers=admin_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["console_enabled"] is True
    # console_world switches the Companion on: its module reads it.
    assert body["modules"] == [*PARTNER_NAV_MODULES, "companion"]
    assert [c["id"] for c in body["catalog"]] == list(PARTNER_MODULES)
    assert {c["kind"] for c in body["catalog"] if c["id"] == "companion"} == {"assistant"}


async def test_modules_are_stored_in_canonical_order_and_audited(
    client, console_world, admin_headers, db_session
) -> None:
    a = console_world["a"]
    op = await _operator(db_session)
    res = await client.put(
        _url(a["partner_id"]),
        headers={**admin_headers, "X-Operator-Id": op},
        json={"console_enabled": True, "modules": ["billing", "panel", "usage"]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["modules"] == ["panel", "usage", "billing"]

    row = (
        await db_session.execute(
            sa.select(AuditLog).where(AuditLog.action == "partner_access.updated")
        )
    ).scalar_one()
    assert row.actor.startswith("operator:op-")
    assert row.target == f"partner:{a['partner_id']}"
    assert row.after_json["modules"] == ["panel", "usage", "billing"]


async def test_the_companion_switch_follows_its_module(
    client, console_world, admin_headers, db_session
) -> None:
    a = console_world["a"]
    op = await _operator(db_session)
    headers = {**admin_headers, "X-Operator-Id": op}

    off = await client.put(
        _url(a["partner_id"]), headers=headers, json={"console_enabled": True, "modules": ["panel"]}
    )
    assert off.status_code == 200, off.text
    db_session.expire_all()
    partner = await db_session.get(Partner, a["partner_id"])
    assert partner is not None and partner.companion_enabled is False

    on = await client.put(
        _url(a["partner_id"]),
        headers=headers,
        json={"console_enabled": True, "modules": ["panel", "companion"]},
    )
    assert on.status_code == 200, on.text
    db_session.expire_all()
    partner = await db_session.get(Partner, a["partner_id"])
    assert partner is not None and partner.companion_enabled is True


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"console_enabled": True, "modules": []}, "no_modules"),
        ({"console_enabled": True, "modules": ["companion"]}, "no_modules"),
    ],
)
async def test_a_console_that_is_on_needs_a_view(
    client, console_world, admin_headers, db_session, body, code
) -> None:
    a = console_world["a"]
    op = await _operator(db_session)
    res = await client.put(
        _url(a["partner_id"]), headers={**admin_headers, "X-Operator-Id": op}, json=body
    )
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == code


async def test_an_unknown_module_is_refused(
    client, console_world, admin_headers, db_session
) -> None:
    a = console_world["a"]
    op = await _operator(db_session)
    res = await client.put(
        _url(a["partner_id"]),
        headers={**admin_headers, "X-Operator-Id": op},
        json={"console_enabled": True, "modules": ["panel", "teleport"]},
    )
    assert res.status_code == 422


async def test_without_an_operator_nothing_changes(client, console_world, admin_headers) -> None:
    a = console_world["a"]
    res = await client.put(
        _url(a["partner_id"]),
        headers=admin_headers,
        json={"console_enabled": True, "modules": ["panel"]},
    )
    assert res.status_code == 400
    again = await client.get(_url(a["partner_id"]), headers=admin_headers)
    assert "clients" in again.json()["modules"]


async def test_an_unknown_partner_is_404(client, admin_headers) -> None:
    res = await client.get(_url(uuid.uuid4()), headers=admin_headers)
    assert res.status_code == 404


async def test_the_console_reads_the_partners_modules(
    client, console_world, admin_headers, db_session
) -> None:
    a = console_world["a"]
    op = await _operator(db_session)
    await client.put(
        _url(a["partner_id"]),
        headers={**admin_headers, "X-Operator-Id": op},
        json={"console_enabled": True, "modules": ["panel", "billing"]},
    )
    me = await client.get("/console/me", headers=a["headers"]())
    assert me.status_code == 200, me.text
    assert me.json()["modules"] == ["panel", "billing"]
    assert me.json()["companion_enabled"] is False


async def test_the_check_constraint_holds_the_catalog_and_nothing_else(db_session) -> None:
    """The migration's CHECK and the enum cannot drift."""
    sql = await db_session.scalar(
        sa.text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_partners_console_modules'"
        )
    )
    assert sql is not None
    for module in PARTNER_MODULES:
        assert f"'{module}'" in sql
    assert sql.count("::character varying") == len(PARTNER_MODULES) or sql.count("'") == 2 * len(
        PARTNER_MODULES
    )
