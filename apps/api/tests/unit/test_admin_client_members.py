"""Spec 030 — las personas del cliente, desde el admin (R1.4 a R1.7, R1.9).

``/admin/tenants/{tenant_id}/client-members``: invitar, reenviar y revocar.
Lo que fija este archivo:

- invitar crea un enlace de un solo uso con caducidad de 21 días y lo manda
  por correo; el enlace solo se guarda como hash;
- una cuenta es de un partner o de un cliente, nunca de los dos, y nunca de
  dos clientes: el admin lo dice al invitar;
- reenviar mata el enlace anterior; revocar cierra las sesiones;
- la lista enseña personas e invitaciones con su estado.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.db.models import ClientInvitation, ClientMembership, ConsoleSession
from nexus_api.services import console_identity, operator_identity
from tests.conftest import console_headers

pytestmark = pytest.mark.asyncio

PASSWORD = "una-clave-larga-y-segura-2026"


async def _setup(client, db_session, console_world, admin_headers, *, modules=("panel",)):
    w = console_world["a"]
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
        )
    headers = {**admin_headers, "X-Operator-Id": str(op.id)}
    resp = await client.put(
        f"/admin/tenants/{w['tenant_id']}/client-access",
        headers=headers,
        json={"enabled": True, "modules": list(modules)},
    )
    assert resp.status_code == 200, resp.text
    return w, headers


def _members(tenant_id: uuid.UUID) -> str:
    return f"/admin/tenants/{tenant_id}/client-members"


async def _accept(client, path: str, password: str = PASSWORD):
    token = path.rsplit("/", 1)[-1]
    svc = console_headers(user_id="console-bff", partner_id=None, service=True)
    return await client.post(
        f"/console/invitations/{token}/accept", headers=svc, json={"password": password}
    )


async def test_invite_creates_a_hashed_21_day_link(
    client, db_session, console_world, admin_headers
) -> None:
    w, headers = await _setup(client, db_session, console_world, admin_headers)
    resp = await client.post(
        _members(w["tenant_id"]),
        headers=headers,
        json={"email": "Valeria@MiNegocio.test", "name": "Valeria Ríos"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == "valeria@minegocio.test"
    assert body["status"] == "pending"
    assert body["accept_path"].startswith("/invite/")
    token = body["accept_path"].rsplit("/", 1)[-1]
    row = await db_session.scalar(sa.select(ClientInvitation))
    assert row is not None
    assert token not in row.token_hash
    left = row.expires_at - datetime.now(UTC)
    assert timedelta(days=20) < left <= timedelta(days=21)


async def test_listing_shows_people_and_invitations(
    client, db_session, console_world, admin_headers
) -> None:
    w, headers = await _setup(client, db_session, console_world, admin_headers)
    first = await client.post(
        _members(w["tenant_id"]), headers=headers, json={"email": "a@minegocio.test"}
    )
    await client.post(_members(w["tenant_id"]), headers=headers, json={"email": "b@minegocio.test"})
    assert (await _accept(client, first.json()["accept_path"])).status_code == 200
    members = (
        await client.get(f"/admin/tenants/{w['tenant_id']}/client-access", headers=headers)
    ).json()["members"]
    by_email = {m["email"]: m for m in members}
    assert by_email["a@minegocio.test"]["kind"] == "member"
    assert by_email["a@minegocio.test"]["status"] == "active"
    assert by_email["b@minegocio.test"]["kind"] == "invitation"
    assert by_email["b@minegocio.test"]["status"] == "pending"


async def test_a_partner_member_cannot_be_invited(
    client, db_session, console_world, admin_headers
) -> None:
    w, headers = await _setup(client, db_session, console_world, admin_headers)
    async with db_session.begin():
        account = await console_identity.create_account(
            db_session, email="owner-a@example.com", password=PASSWORD
        )
        await db_session.execute(
            sa.text("UPDATE partner_memberships SET user_id = :u WHERE id = :m"),
            {"u": str(account.id), "m": w["membership_id"]},
        )
    resp = await client.post(
        _members(w["tenant_id"]), headers=headers, json={"email": "owner-a@example.com"}
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "account_is_partner_member"


async def test_a_person_of_another_client_cannot_be_invited(
    client, db_session, console_world, admin_headers
) -> None:
    w, headers = await _setup(client, db_session, console_world, admin_headers)
    b = console_world["b"]
    async with db_session.begin():
        account = await console_identity.create_account(
            db_session, email="de-otro@cliente.test", password=PASSWORD
        )
        db_session.add(
            ClientMembership(
                partner_id=b["partner_id"],
                tenant_id=b["tenant_id"],
                user_id=str(account.id),
                email=account.email,
            )
        )
    resp = await client.post(
        _members(w["tenant_id"]), headers=headers, json={"email": "de-otro@cliente.test"}
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "account_is_other_client"


async def test_already_member_and_access_off(
    client, db_session, console_world, admin_headers
) -> None:
    w, headers = await _setup(client, db_session, console_world, admin_headers)
    first = await client.post(
        _members(w["tenant_id"]), headers=headers, json={"email": "a@minegocio.test"}
    )
    assert (await _accept(client, first.json()["accept_path"])).status_code == 200
    again = await client.post(
        _members(w["tenant_id"]), headers=headers, json={"email": "a@minegocio.test"}
    )
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "already_member"

    await client.put(
        f"/admin/tenants/{w['tenant_id']}/client-access",
        headers=headers,
        json={"enabled": False, "modules": ["panel"]},
    )
    off = await client.post(
        _members(w["tenant_id"]), headers=headers, json={"email": "c@minegocio.test"}
    )
    assert off.status_code == 409
    assert off.json()["detail"]["code"] == "access_disabled"


async def test_resend_kills_the_previous_link(
    client, db_session, console_world, admin_headers
) -> None:
    w, headers = await _setup(client, db_session, console_world, admin_headers)
    first = (
        await client.post(
            _members(w["tenant_id"]), headers=headers, json={"email": "a@minegocio.test"}
        )
    ).json()
    resent = await client.post(f"{_members(w['tenant_id'])}/{first['id']}/resend", headers=headers)
    assert resent.status_code == 201, resent.text
    assert resent.json()["accept_path"] != first["accept_path"]
    old = await _accept(client, first["accept_path"])
    assert old.status_code == 404
    new = await _accept(client, resent.json()["accept_path"])
    assert new.status_code == 200, new.text


async def test_revoke_a_person_closes_sessions_and_is_idempotent(
    client, db_session, console_world, admin_headers
) -> None:
    w, headers = await _setup(client, db_session, console_world, admin_headers)
    inv = (
        await client.post(
            _members(w["tenant_id"]), headers=headers, json={"email": "a@minegocio.test"}
        )
    ).json()
    assert (await _accept(client, inv["accept_path"])).status_code == 200
    member = await db_session.scalar(sa.select(ClientMembership))
    assert member is not None
    for _ in range(2):
        resp = await client.post(f"{_members(w['tenant_id'])}/{member.id}/revoke", headers=headers)
        assert resp.status_code == 204, resp.text
    db_session.expire_all()
    member = await db_session.scalar(sa.select(ClientMembership))
    assert member is not None and member.status == "revoked"
    live = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(ConsoleSession)
        .where(ConsoleSession.principal_id == uuid.UUID(member.user_id))
    )
    assert live == 0


async def test_revoke_an_invitation(client, db_session, console_world, admin_headers) -> None:
    w, headers = await _setup(client, db_session, console_world, admin_headers)
    inv = (
        await client.post(
            _members(w["tenant_id"]), headers=headers, json={"email": "a@minegocio.test"}
        )
    ).json()
    resp = await client.post(f"{_members(w['tenant_id'])}/{inv['id']}/revoke", headers=headers)
    assert resp.status_code == 204
    assert (await _accept(client, inv["accept_path"])).status_code == 404


async def test_ids_of_another_tenant_are_404(
    client, db_session, console_world, admin_headers
) -> None:
    w, headers = await _setup(client, db_session, console_world, admin_headers)
    inv = (
        await client.post(
            _members(w["tenant_id"]), headers=headers, json={"email": "a@minegocio.test"}
        )
    ).json()
    other = console_world["b"]["tenant_id"]
    resp = await client.post(f"{_members(other)}/{inv['id']}/revoke", headers=headers)
    assert resp.status_code == 404
