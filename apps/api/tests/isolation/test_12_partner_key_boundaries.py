"""Isolation guarantee — partner key boundaries (ADR-028).

The ``partner_tenants`` mapping is the isolation frontier of the embed
platform: a partner's API key must never mint a session for another
partner's client, and key lifecycle (revoke / grace / scope) must fail
closed on the public surface.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.core.partner_keys import generate_api_key
from nexus_api.db.models import (
    EmbedAuditLog,
    Partner,
    PartnerApiKey,
    PartnerTenant,
    Tenant,
    TenantPlan,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def _seed_partner(
    db_session,
    *,
    slug: str,
    tenant_id: uuid.UUID,
    external_client_ref: str = "client-1",
    scopes: list[str] | None = None,
) -> tuple[uuid.UUID, str, uuid.UUID]:
    """Creates partner + key + tenant mapping. Returns (partner_id,
    plaintext_key, key_id)."""
    partner_id = uuid.uuid4()
    generated = generate_api_key()
    key_id = uuid.uuid4()
    db_session.add(Partner(id=partner_id, name=f"Partner {slug}", slug=slug))
    db_session.add(
        PartnerApiKey(
            id=key_id,
            partner_id=partner_id,
            prefix_snippet=generated.prefix_snippet,
            key_hash=generated.key_hash,
            scopes=scopes if scopes is not None else ["provision", "widget_sessions"],
            allowed_origins=["https://partner.example"],
        )
    )
    db_session.add(
        PartnerTenant(
            partner_id=partner_id,
            external_client_ref=external_client_ref,
            tenant_id=tenant_id,
        )
    )
    await db_session.commit()
    return partner_id, generated.plaintext, key_id


@pytest.fixture
async def two_partners(db_session):
    """Partner A → tenant A (ref 'client-1'); Partner B → tenant B
    (ref 'client-b')."""
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    db_session.add_all(
        [
            Tenant(
                id=tenant_a,
                name="Embed A",
                slug=f"embed-a-{tenant_a.hex[:6]}",
                plan=TenantPlan.PRO,
            ),
            Tenant(
                id=tenant_b,
                name="Embed B",
                slug=f"embed-b-{tenant_b.hex[:6]}",
                plan=TenantPlan.PRO,
            ),
        ]
    )
    await db_session.commit()
    a_partner, a_key, a_key_id = await _seed_partner(
        db_session, slug=f"pa-{tenant_a.hex[:6]}", tenant_id=tenant_a
    )
    b_partner, b_key, b_key_id = await _seed_partner(
        db_session,
        slug=f"pb-{tenant_b.hex[:6]}",
        tenant_id=tenant_b,
        external_client_ref="client-b",
    )
    return {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "a": {"partner_id": a_partner, "key": a_key, "key_id": a_key_id},
        "b": {"partner_id": b_partner, "key": b_key, "key_id": b_key_id},
    }


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def test_partner_cannot_mint_other_partners_client(client, two_partners) -> None:
    """Partner A's key + Partner B's client ref → opaque 404. The mapping
    lookup is keyed by the authenticated partner, so B's refs simply do
    not exist in A's namespace."""
    resp = await client.post(
        "/v1/widget-sessions",
        json={"external_client_ref": "client-b"},
        headers=_auth(two_partners["a"]["key"]),
    )
    assert resp.status_code == 404


async def test_mint_own_client_succeeds_and_is_tenant_scoped(
    client, two_partners, db_session
) -> None:
    resp = await client.post(
        "/v1/widget-sessions",
        json={"external_client_ref": "client-1"},
        headers=_auth(two_partners["a"]["key"]),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["session_token"]
    assert body["expires_in"] > 0
    # No internal tenant id anywhere in the partner-facing response.
    assert "tenant_id" not in resp.text

    from nexus_api.core.embed_jwt import verify_widget_token

    claims = verify_widget_token(body["session_token"])
    assert claims.tenant_id == two_partners["tenant_a"]
    assert claims.partner_id == two_partners["a"]["partner_id"]

    # Mint is audited with the token's jti.
    audit = (
        await db_session.execute(
            sa.select(EmbedAuditLog).where(EmbedAuditLog.event == "session.minted")
        )
    ).scalars().all()
    assert any(row.jti == claims.jti for row in audit)


async def test_revoked_key_is_rejected_immediately(client, two_partners, db_session) -> None:
    await db_session.execute(
        sa.update(PartnerApiKey)
        .where(PartnerApiKey.id == two_partners["a"]["key_id"])
        .values(revoked_at=datetime.now(UTC), grace_expires_at=None)
    )
    await db_session.commit()
    resp = await client.post(
        "/v1/widget-sessions",
        json={"external_client_ref": "client-1"},
        headers=_auth(two_partners["a"]["key"]),
    )
    assert resp.status_code == 401


async def test_rotated_key_in_grace_still_works(client, two_partners, db_session) -> None:
    now = datetime.now(UTC)
    await db_session.execute(
        sa.update(PartnerApiKey)
        .where(PartnerApiKey.id == two_partners["a"]["key_id"])
        .values(revoked_at=now, grace_expires_at=now + timedelta(hours=1))
    )
    await db_session.commit()
    resp = await client.post(
        "/v1/widget-sessions",
        json={"external_client_ref": "client-1"},
        headers=_auth(two_partners["a"]["key"]),
    )
    assert resp.status_code == 201


async def test_expired_grace_is_rejected(client, two_partners, db_session) -> None:
    now = datetime.now(UTC)
    await db_session.execute(
        sa.update(PartnerApiKey)
        .where(PartnerApiKey.id == two_partners["a"]["key_id"])
        .values(revoked_at=now - timedelta(hours=2), grace_expires_at=now - timedelta(hours=1))
    )
    await db_session.commit()
    resp = await client.post(
        "/v1/widget-sessions",
        json={"external_client_ref": "client-1"},
        headers=_auth(two_partners["a"]["key"]),
    )
    assert resp.status_code == 401


async def test_insufficient_scope_is_403(client, db_session) -> None:
    tenant = uuid.uuid4()
    db_session.add(
        Tenant(id=tenant, name="Scoped", slug=f"scoped-{tenant.hex[:6]}", plan=TenantPlan.PRO)
    )
    await db_session.commit()
    _, key, _ = await _seed_partner(
        db_session, slug=f"ps-{tenant.hex[:6]}", tenant_id=tenant, scopes=["provision"]
    )
    resp = await client.post(
        "/v1/widget-sessions",
        json={"external_client_ref": "client-1"},
        headers=_auth(key),
    )
    assert resp.status_code == 403


async def test_suspended_partner_is_403(client, two_partners, db_session) -> None:
    await db_session.execute(
        sa.update(Partner)
        .where(Partner.id == two_partners["a"]["partner_id"])
        .values(status="suspended")
    )
    await db_session.commit()
    resp = await client.post(
        "/v1/widget-sessions",
        json={"external_client_ref": "client-1"},
        headers=_auth(two_partners["a"]["key"]),
    )
    assert resp.status_code == 403


async def test_bad_checksum_rejected_offline(client, two_partners) -> None:
    """A tampered key fails the CRC check → 401 without a DB lookup."""
    good = two_partners["a"]["key"]
    tampered = good[:-1] + ("A" if good[-1] != "A" else "B")
    resp = await client.post(
        "/v1/widget-sessions",
        json={"external_client_ref": "client-1"},
        headers=_auth(tampered),
    )
    assert resp.status_code == 401


async def test_missing_bearer_rejected(client) -> None:
    resp = await client.post(
        "/v1/widget-sessions",
        json={"external_client_ref": "client-1"},
    )
    assert resp.status_code == 401


async def test_provision_is_idempotent_and_hides_tenant_id(client, two_partners) -> None:
    headers = _auth(two_partners["a"]["key"])
    first = await client.post(
        "/v1/partners/clients",
        json={"external_client_ref": "new-client", "name": "Tienda X"},
        headers=headers,
    )
    assert first.status_code == 200
    assert first.json()["whatsapp"]["status"] == "not_connected"
    assert "tenant_id" not in first.text

    second = await client.post(
        "/v1/partners/clients",
        json={"external_client_ref": "new-client", "name": "Tienda X"},
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json() == first.json()


async def test_provisioned_clients_are_partner_scoped(client, two_partners) -> None:
    """Same external ref provisioned by A and B lands on two DIFFERENT
    tenants — the ref namespace is per-partner."""
    ref = {"external_client_ref": "shared-ref", "name": "Same Name"}
    ra = await client.post("/v1/partners/clients", json=ref, headers=_auth(two_partners["a"]["key"]))
    rb = await client.post("/v1/partners/clients", json=ref, headers=_auth(two_partners["b"]["key"]))
    assert ra.status_code == rb.status_code == 200

    ta = await client.post(
        "/v1/widget-sessions", json={"external_client_ref": "shared-ref"},
        headers=_auth(two_partners["a"]["key"]),
    )
    tb = await client.post(
        "/v1/widget-sessions", json={"external_client_ref": "shared-ref"},
        headers=_auth(two_partners["b"]["key"]),
    )
    from nexus_api.core.embed_jwt import verify_widget_token

    claims_a = verify_widget_token(ta.json()["session_token"])
    claims_b = verify_widget_token(tb.json()["session_token"])
    assert claims_a.tenant_id != claims_b.tenant_id
