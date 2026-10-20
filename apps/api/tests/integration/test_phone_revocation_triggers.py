"""Spec 031 · revocar — R7.1 a R7.6 (tareas T051 y T052).

La sesión del teléfono dura meses. Lo que este fichero fija es la otra cara:
**cada puerta que ya cerraba la web cierra también el teléfono**, y la persona y
Auphere pueden cerrar un teléfono concreto, perdido, sin tocar los demás.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import AuditLog, ClientPhone
from nexus_api.services import operator_identity
from tests.conftest import (
    add_client_member,
    add_client_phone,
    make_client_access,
    make_console_account,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def world(db_session, console_world, admin_headers) -> dict[str, Any]:
    w = console_world["a"]
    await make_client_access(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    member = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )
    other = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )
    iphone = await add_client_phone(db_session, membership_id=member["membership_id"])
    android = await add_client_phone(
        db_session, membership_id=member["membership_id"], platform="android"
    )
    theirs = await add_client_phone(db_session, membership_id=other["membership_id"])
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
        )
    return {
        "w": w,
        "member": member,
        "other": other,
        "iphone": iphone,
        "android": android,
        "theirs": theirs,
        "admin": {**admin_headers, "X-Operator-Id": str(op.id)},
        "operator_email": op.email,
    }


async def _state(db_session, phone_id: uuid.UUID) -> tuple[str | None, str | None, str | None]:
    db_session.expire_all()
    row = (
        await db_session.execute(
            sa.select(
                ClientPhone.revoked_reason, ClientPhone.revoked_by, ClientPhone.push_token
            ).where(ClientPhone.id == phone_id)
        )
    ).one()
    return row.revoked_reason, row.revoked_by, row.push_token


async def _reads(client, phone: dict[str, Any]) -> int:
    resp = await client.get("/console/lite/me", headers=phone["headers"]())
    return int(resp.status_code)


async def test_signing_out_closes_only_this_phone(client, db_session, world) -> None:
    resp = await client.delete("/console/lite/phones/current", headers=world["iphone"]["headers"]())

    assert resp.status_code == 204
    reason, by, _ = await _state(db_session, world["iphone"]["phone_id"])
    assert reason == "signed_out" and by is not None and by.startswith("client:")
    assert await _reads(client, world["iphone"]) == 403
    assert await _reads(client, world["android"]) == 200


async def test_the_person_lists_and_closes_their_own_phones_from_the_web(
    client, db_session, world
) -> None:
    web = world["member"]["headers"]
    listed = await client.get("/console/lite/phones", headers=web())
    assert listed.status_code == 200
    ids = {p["id"] for p in listed.json()}
    assert ids == {str(world["iphone"]["phone_id"]), str(world["android"]["phone_id"])}
    assert all(p["current"] is False for p in listed.json())

    closed = await client.delete(
        f"/console/lite/phones/{world['android']['phone_id']}", headers=web()
    )
    assert closed.status_code == 204
    reason, _, _ = await _state(db_session, world["android"]["phone_id"])
    assert reason == "closed_by_person"
    assert await _reads(client, world["android"]) == 403
    assert await _reads(client, world["iphone"]) == 200


async def test_the_app_marks_the_phone_it_is_calling_from(client, world) -> None:
    listed = await client.get("/console/lite/phones", headers=world["iphone"]["headers"]())
    current = [p for p in listed.json() if p["current"]]
    assert [p["id"] for p in current] == [str(world["iphone"]["phone_id"])]


async def test_nobody_closes_someone_elses_phone(client, db_session, world) -> None:
    resp = await client.delete(
        f"/console/lite/phones/{world['theirs']['phone_id']}",
        headers=world["member"]["headers"](),
    )
    assert resp.status_code == 404
    reason, _, _ = await _state(db_session, world["theirs"]["phone_id"])
    assert reason is None


async def test_auphere_closes_a_lost_phone_from_the_admin(client, db_session, world) -> None:
    w, member = world["w"], world["member"]
    base = f"/admin/tenants/{w['tenant_id']}/client-members/{member['membership_id']}/phones"

    listed = await client.get(base, headers=world["admin"])
    assert listed.status_code == 200
    assert {p["id"] for p in listed.json()} == {
        str(world["iphone"]["phone_id"]),
        str(world["android"]["phone_id"]),
    }

    resp = await client.delete(f"{base}/{world['iphone']['phone_id']}", headers=world["admin"])
    assert resp.status_code == 204
    reason, by, token = await _state(db_session, world["iphone"]["phone_id"])
    assert reason == "closed_by_auphere"
    assert by == f"operator:{world['operator_email']}"
    assert token is None
    audit = await db_session.scalar(
        sa.select(AuditLog.actor).where(
            AuditLog.action == "client_phone.closed",
            AuditLog.target == f"client_phone:{world['iphone']['phone_id']}",
        )
    )
    assert audit == f"operator:{world['operator_email']}"


async def test_the_admin_needs_an_operator_to_close(client, world, admin_headers) -> None:
    w, member = world["w"], world["member"]
    url = (
        f"/admin/tenants/{w['tenant_id']}/client-members/{member['membership_id']}"
        f"/phones/{world['iphone']['phone_id']}"
    )
    resp = await client.delete(url, headers=admin_headers)
    assert resp.status_code == 400


async def test_the_admin_cannot_close_a_phone_through_another_person(client, world) -> None:
    w, other = world["w"], world["other"]
    url = (
        f"/admin/tenants/{w['tenant_id']}/client-members/{other['membership_id']}"
        f"/phones/{world['iphone']['phone_id']}"
    )
    resp = await client.delete(url, headers=world["admin"])
    assert resp.status_code == 404


async def test_removing_the_person_closes_their_phones(client, db_session, world) -> None:
    w, member = world["w"], world["member"]
    resp = await client.post(
        f"/admin/tenants/{w['tenant_id']}/client-members/{member['membership_id']}/revoke",
        headers=world["admin"],
    )
    assert resp.status_code == 204, resp.text

    for key in ("iphone", "android"):
        reason, by, token = await _state(db_session, world[key]["phone_id"])
        assert (reason, by, token) == ("member_removed", "system", None)
        assert await _reads(client, world[key]) == 403
    reason, _, _ = await _state(db_session, world["theirs"]["phone_id"])
    assert reason is None


async def test_turning_access_off_closes_every_phone_of_the_client(
    client, db_session, world
) -> None:
    w = world["w"]
    resp = await client.put(
        f"/admin/tenants/{w['tenant_id']}/client-access",
        headers=world["admin"],
        json={"enabled": False, "modules": ["panel", "inbox", "usage"]},
    )
    assert resp.status_code == 200, resp.text

    for key in ("iphone", "android", "theirs"):
        reason, _, _ = await _state(db_session, world[key]["phone_id"])
        assert reason == "access_disabled"


async def test_removing_a_module_closes_nothing(client, db_session, world) -> None:
    w = world["w"]
    resp = await client.put(
        f"/admin/tenants/{w['tenant_id']}/client-access",
        headers=world["admin"],
        json={"enabled": True, "modules": ["panel"]},
    )
    assert resp.status_code == 200, resp.text

    reason, _, _ = await _state(db_session, world["iphone"]["phone_id"])
    assert reason is None
    me = await client.get("/console/lite/me", headers=world["iphone"]["headers"]())
    assert me.json()["nav"] == ["panel"]


async def test_a_password_reset_closes_the_persons_phones(db_session, world) -> None:
    from nexus_api.db.models import ClientMembership
    from nexus_api.services import principal_access

    w = world["w"]
    account = await make_console_account(db_session)
    membership_id = uuid.uuid4()
    db_session.add(
        ClientMembership(
            id=membership_id,
            partner_id=w["partner_id"],
            tenant_id=w["tenant_id"],
            user_id=str(account),
            email="reset@minegocio.test",
            status="active",
        )
    )
    await db_session.commit()
    phone = await add_client_phone(db_session, membership_id=membership_id)

    async with db_session.begin():
        result = await principal_access.revoke_all_access(
            db_session, principal_id=account, reason="password_reset", actor="system"
        )

    assert result["phones_closed"] == 1
    reason, by, _ = await _state(db_session, phone["phone_id"])
    assert (reason, by) == ("password_reset", "system")
    # Los de otra persona siguen abiertos.
    other, _, _ = await _state(db_session, world["iphone"]["phone_id"])
    assert other is None
