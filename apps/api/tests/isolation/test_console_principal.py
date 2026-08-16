"""Isolation guarantee — the console principal (PLAN-CONSOLE-V1 CP-03).

The BFF mints a 60-second EdDSA token; the backend verifies it and then
re-derives partner + role from ``partner_memberships`` on its own. Pinned
here:

- credential problems are 401 (missing, garbage, wrong key, expired,
  over-long lifetime, replayed ``jti``);
- authorization problems are 403 (no membership, other partner's
  membership, suspended member/partner, console switched off for the
  partner, role without the permission);
- the ROLE COMES FROM THE DATABASE, not from the token;
- service tokens and principal tokens are not interchangeable;
- the master switch (``NEXUS_CONSOLE_ENABLED``) closes everything (503).
"""

from __future__ import annotations

import time
import uuid

import pytest
import sqlalchemy as sa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nexus_api.config import get_settings
from nexus_api.core import console_auth
from nexus_api.db.models import Partner, PartnerMembership
from tests.conftest import add_console_member, console_headers, mint_console_token

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

ME = "/console/me"


# ── 401: credential problems ───────────────────────────────────────────


async def test_missing_bearer_is_401(client, console_world) -> None:
    assert (await client.get(ME)).status_code == 401
    assert (await client.get(ME, headers={"Authorization": "Bearer"})).status_code == 401
    assert (await client.get(ME, headers={"Authorization": "Basic abc"})).status_code == 401


async def test_garbage_and_foreign_signature_are_401(client, console_world) -> None:
    w = console_world["a"]
    assert (await client.get(ME, headers={"Authorization": "Bearer not.a.jwt"})).status_code == 401

    other = Ed25519PrivateKey.generate()
    other_pem = other.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    forged = console_headers(
        user_id=w["user_id"], partner_id=w["partner_id"], private_pem=other_pem
    )
    resp = await client.get(ME, headers=forged)
    assert resp.status_code == 401


async def test_expired_token_is_401(client, console_world) -> None:
    w = console_world["a"]
    # Issued 3 minutes ago with a 60 s life: dead even with 5 s leeway.
    headers = console_headers(
        user_id=w["user_id"], partner_id=w["partner_id"], issued_at=int(time.time()) - 180
    )
    resp = await client.get(ME, headers=headers)
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


async def test_lifetime_over_policy_is_401_even_if_valid(client, console_world) -> None:
    """A correctly signed token that claims 10 minutes of life is not one
    the BFF is allowed to mint — refused regardless of signature."""
    w = console_world["a"]
    headers = console_headers(user_id=w["user_id"], partner_id=w["partner_id"], ttl=600)
    resp = await client.get(ME, headers=headers)
    assert resp.status_code == 401
    assert "lifetime" in resp.json()["detail"].lower()


async def test_replayed_jti_is_401(client, console_world) -> None:
    w = console_world["a"]
    headers = console_headers(
        user_id=w["user_id"], partner_id=w["partner_id"], jti=uuid.uuid4().hex
    )
    first = await client.get(ME, headers=headers)
    assert first.status_code == 200
    second = await client.get(ME, headers=headers)
    assert second.status_code == 401
    assert "already used" in second.json()["detail"].lower()


async def test_replay_guard_degrades_to_memory_when_redis_fails(
    client, console_world, fake_redis
) -> None:
    """Redis down → the per-replica memory set still refuses a replay."""
    w = console_world["a"]

    async def _boom(*_a: object, **_k: object) -> None:
        raise ConnectionError("redis down")

    fake_redis.set = _boom  # type: ignore[assignment]
    headers = console_headers(
        user_id=w["user_id"], partner_id=w["partner_id"], jti=uuid.uuid4().hex
    )
    assert (await client.get(ME, headers=headers)).status_code == 200
    assert (await client.get(ME, headers=headers)).status_code == 401


async def test_missing_required_claims_are_401(client, console_world) -> None:
    w = console_world["a"]
    # No jti.
    import jwt as _jwt

    from tests.conftest import CONSOLE_TEST_PRIVATE_PEM

    settings = get_settings()
    now = int(time.time())
    token = _jwt.encode(
        {
            "iss": settings.console_jwt_issuer,
            "aud": settings.console_jwt_audience,
            "sub": w["user_id"],
            "partner_id": str(w["partner_id"]),
            "iat": now,
            "exp": now + 60,
        },
        CONSOLE_TEST_PRIVATE_PEM,
        algorithm="EdDSA",
    )
    assert (await client.get(ME, headers={"Authorization": f"Bearer {token}"})).status_code == 401
    # Wrong audience.
    bad_aud = console_headers(user_id=w["user_id"], partner_id=w["partner_id"], aud="someone-else")
    assert (await client.get(ME, headers=bad_aud)).status_code == 401


# ── 403: authorization problems ────────────────────────────────────────


async def test_unknown_user_is_403_not_404(client, console_world) -> None:
    w = console_world["a"]
    headers = console_headers(user_id="user_nobody", partner_id=w["partner_id"])
    resp = await client.get(ME, headers=headers)
    assert resp.status_code == 403


async def test_membership_of_other_partner_is_403(client, console_world) -> None:
    """A's real user claiming to be in B: the DB says otherwise."""
    a, b = console_world["a"], console_world["b"]
    headers = console_headers(user_id=a["user_id"], partner_id=b["partner_id"])
    resp = await client.get(ME, headers=headers)
    assert resp.status_code == 403
    # And the error is the same generic one as for an unknown user.
    unknown = await client.get(
        ME, headers=console_headers(user_id="user_nobody", partner_id=b["partner_id"])
    )
    assert resp.json() == unknown.json()


async def test_suspended_member_is_403(client, console_world, db_session) -> None:
    w = console_world["a"]
    member = await add_console_member(
        db_session, partner_id=w["partner_id"], role="builder", status="suspended"
    )
    assert (await client.get(ME, headers=member["headers"]())).status_code == 403


async def test_suspended_partner_is_403(client, console_world, db_session) -> None:
    w = console_world["a"]
    await db_session.execute(
        sa.update(Partner).where(Partner.id == w["partner_id"]).values(status="suspended")
    )
    await db_session.commit()
    resp = await client.get(ME, headers=w["headers"]())
    assert resp.status_code == 403
    assert "suspended" in resp.json()["detail"].lower()


async def test_console_disabled_for_partner_is_403(client, console_world, db_session) -> None:
    w = console_world["a"]
    await db_session.execute(
        sa.update(Partner).where(Partner.id == w["partner_id"]).values(console_enabled=False)
    )
    await db_session.commit()
    resp = await client.get(ME, headers=w["headers"]())
    assert resp.status_code == 403
    assert "not enabled" in resp.json()["detail"].lower()


async def test_role_comes_from_the_database_not_the_token(
    client, console_world, db_session
) -> None:
    """Token says ``owner``; DB says ``analyst``. Analyst cannot manage the
    team → 403. And ``/me`` reports the DB role."""
    w = console_world["a"]
    analyst = await add_console_member(db_session, partner_id=w["partner_id"], role="analyst")
    lying = analyst["headers"](role="owner")
    me = await client.get(ME, headers=lying)
    assert me.status_code == 200
    assert me.json()["role"] == "analyst"
    assert "team:manage" not in me.json()["permissions"]

    resp = await client.post(
        "/console/team/invitations",
        headers=analyst["headers"](role="owner"),
        json={"email": "x@example.com", "role": "builder"},
    )
    assert resp.status_code == 403
    assert "lacks permission" in resp.json()["detail"]


async def test_permission_map_is_consistent(client, console_world, db_session) -> None:
    """Every role's ``/me`` permissions equal the map in ``console_auth``."""
    w = console_world["a"]
    for role in ("owner", "admin", "builder", "analyst", "billing"):
        member = await add_console_member(db_session, partner_id=w["partner_id"], role=role)
        me = await client.get(ME, headers=member["headers"]())
        assert me.status_code == 200, me.text
        assert set(me.json()["permissions"]) == console_auth.permissions_for(role)


async def test_billing_role_cannot_read_clients(client, console_world, db_session) -> None:
    w = console_world["a"]
    billing = await add_console_member(db_session, partner_id=w["partner_id"], role="billing")
    assert (await client.get("/console/clients", headers=billing["headers"]())).status_code == 403
    assert (await client.get("/console/billing", headers=billing["headers"]())).status_code == 200
    # …and admin (everything but billing) cannot read billing.
    admin = await add_console_member(db_session, partner_id=w["partner_id"], role="admin")
    assert (await client.get("/console/billing", headers=admin["headers"]())).status_code == 403


# ── token kinds are not interchangeable ────────────────────────────────


async def test_service_token_cannot_act_as_principal(client, console_world) -> None:
    svc = {
        "Authorization": f"Bearer {mint_console_token(user_id='bff', partner_id=None, service=True)}"
    }
    resp = await client.get(ME, headers=svc)
    assert resp.status_code == 403


async def test_principal_token_cannot_use_service_endpoints(client, console_world) -> None:
    w = console_world["a"]
    resp = await client.get(f"/console/invitations/{'a' * 43}", headers=w["headers"]())
    assert resp.status_code == 403


# ── master switch ──────────────────────────────────────────────────────


async def test_master_switch_off_is_503(client, console_world, monkeypatch) -> None:
    w = console_world["a"]
    monkeypatch.setattr(get_settings(), "console_enabled", False)
    resp = await client.get(ME, headers=w["headers"]())
    assert resp.status_code == 503


async def test_no_public_key_fails_closed(client, console_world, monkeypatch) -> None:
    w = console_world["a"]
    monkeypatch.setattr(get_settings(), "console_jwt_public_key", "")
    resp = await client.get(ME, headers=w["headers"]())
    assert resp.status_code == 401


# ── happy path ─────────────────────────────────────────────────────────


async def test_me_reports_partner_role_and_quota(client, console_world) -> None:
    w = console_world["a"]
    resp = await client.get(ME, headers=w["headers"]())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["partner"]["slug"] == w["slug"]
    assert body["role"] == "owner"
    assert body["membership_id"] == str(w["membership_id"])
    assert body["quota"] == {
        "max_clients": 3,
        "used_clients": 1,
        "remaining_clients": 2,
        "max_channels_per_client": 2,
    }
    # No internal ids leak.
    assert "tenant_id" not in resp.text
    assert str(w["partner_id"]) not in resp.text


async def test_membership_row_is_the_source_of_truth_for_email(
    client, console_world, db_session
) -> None:
    w = console_world["a"]
    await db_session.execute(
        sa.update(PartnerMembership)
        .where(PartnerMembership.id == w["membership_id"])
        .values(email="renamed@example.com")
    )
    await db_session.commit()
    resp = await client.get(ME, headers=w["headers"]())
    assert resp.json()["email"] == "renamed@example.com"
