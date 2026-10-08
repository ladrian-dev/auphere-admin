"""Spec 030 — aceptar la invitación de un cliente (R1.4, R1.5, R2.6).

La misma página de la consola (``/invite/{token}``) y los mismos dos
endpoints de servicio sirven a las dos invitaciones. Lo que fija este
archivo:

- ``GET /console/invitations/{token}`` encuentra la invitación de un cliente
  y dice de qué negocio es;
- aceptar crea la cuenta y la membresía de cliente, y abre sesión;
- con una cuenta que ya existe, se pide SU contraseña (un enlace no es un
  restablecimiento);
- la invariante entre tablas: quien ya es de un partner no acepta una
  invitación de cliente, y quien es de un cliente no acepta una de partner;
- la sesión resultante es de cliente.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.models import ClientMembership, PartnerInvitation
from nexus_api.repositories.partner_membership import hash_invitation_token
from nexus_api.services import console_identity, operator_identity
from tests.conftest import console_headers

pytestmark = pytest.mark.asyncio

PASSWORD = "una-clave-larga-y-segura-2026"


def _email() -> str:
    # ``console_auth.principals`` no se vacía entre tests: correos únicos.
    return f"v-{uuid.uuid4().hex[:10]}@minegocio.test"


def _svc() -> dict[str, str]:
    return console_headers(user_id="console-bff", partner_id=None, service=True)


async def _invite(client, db_session, console_world, admin_headers, email: str) -> str:
    w = console_world["a"]
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
        )
    headers = {**admin_headers, "X-Operator-Id": str(op.id)}
    await client.put(
        f"/admin/tenants/{w['tenant_id']}/client-access",
        headers=headers,
        json={"enabled": True, "modules": ["panel", "usage"]},
    )
    resp = await client.post(
        f"/admin/tenants/{w['tenant_id']}/client-members", headers=headers, json={"email": email}
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["accept_path"]).rsplit("/", 1)[-1]


async def test_lookup_names_the_business(client, db_session, console_world, admin_headers) -> None:
    email = _email()
    token = await _invite(client, db_session, console_world, admin_headers, email)
    resp = await client.get(f"/console/invitations/{token}", headers=_svc())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["partner_name"] == "Client A One"
    assert body["role"] == "client"
    assert body["email"] == email


async def test_accept_creates_account_membership_and_session(
    client, db_session, console_world, admin_headers
) -> None:
    token = await _invite(client, db_session, console_world, admin_headers, _email())
    resp = await client.post(
        f"/console/invitations/{token}/accept",
        headers=_svc(),
        json={"password": PASSWORD, "display_name": "Valeria Ríos"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "client"
    member = await db_session.scalar(sa.select(ClientMembership))
    assert member is not None
    assert member.status == "active" and member.accepted_at is not None
    assert body["membership_id"] == str(member.id)
    # La sesión que devuelve es de cliente.
    session_resp = await client.post(
        "/console/auth/session", headers=_svc(), json={"token": body["token"]}
    )
    principal = session_resp.json()["principal"]
    assert principal["kind"] == "client"
    assert principal["access"] == "ok"
    assert principal["modules"] == ["panel", "usage"]


async def test_existing_account_needs_its_own_password(
    client, db_session, console_world, admin_headers
) -> None:
    email = _email()
    async with db_session.begin():
        await console_identity.create_account(
            db_session, email=email, password="otra-clave-larga-2026-x"
        )
    token = await _invite(client, db_session, console_world, admin_headers, email)
    wrong = await client.post(
        f"/console/invitations/{token}/accept", headers=_svc(), json={"password": PASSWORD}
    )
    assert wrong.status_code == 409
    right = await client.post(
        f"/console/invitations/{token}/accept",
        headers=_svc(),
        json={"password": "otra-clave-larga-2026-x"},
    )
    assert right.status_code == 200, right.text


async def test_a_partner_member_cannot_accept_a_client_invitation(
    client, db_session, console_world, admin_headers
) -> None:
    """El admin lo comprueba al invitar; esto prueba la puerta de la
    aceptación, por si la cuenta se hizo de un partner entre medias."""
    email = _email()
    token = await _invite(client, db_session, console_world, admin_headers, email)
    w = console_world["a"]
    async with db_session.begin():
        account = await console_identity.create_account(db_session, email=email, password=PASSWORD)
        await db_session.execute(
            sa.text("UPDATE partner_memberships SET user_id = :u WHERE id = :m"),
            {"u": str(account.id), "m": w["membership_id"]},
        )
    resp = await client.post(
        f"/console/invitations/{token}/accept", headers=_svc(), json={"password": PASSWORD}
    )
    assert resp.status_code == 409
    assert "already_member" in str(resp.json()["detail"])


async def test_a_client_member_cannot_accept_a_partner_invitation(
    client, db_session, console_world, admin_headers
) -> None:
    email = _email()
    token = await _invite(client, db_session, console_world, admin_headers, email)
    accepted = await client.post(
        f"/console/invitations/{token}/accept", headers=_svc(), json={"password": PASSWORD}
    )
    assert accepted.status_code == 200
    partner_token = "p" * 43
    from datetime import UTC, datetime, timedelta

    db_session.add(
        PartnerInvitation(
            id=uuid.uuid4(),
            partner_id=console_world["b"]["partner_id"],
            email=email,
            role="analyst",
            token_hash=hash_invitation_token(partner_token),
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    await db_session.commit()
    resp = await client.post(
        f"/console/invitations/{partner_token}/accept", headers=_svc(), json={"password": PASSWORD}
    )
    assert resp.status_code == 409
    assert "already_member" in str(resp.json()["detail"])


async def test_unknown_token_is_404(client) -> None:
    resp = await client.get(f"/console/invitations/{'z' * 43}", headers=_svc())
    assert resp.status_code == 404
