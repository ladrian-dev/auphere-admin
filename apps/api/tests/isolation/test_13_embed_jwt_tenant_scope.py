"""Isolation guarantee — embed JWT tenant scoping (ADR-028).

Every ``/v1/embed/*`` request derives its tenant EXCLUSIVELY from the
signed widget JWT and runs under RLS. A token for tenant X must never
observe tenant Y, and the fail-closed re-checks (key revoked, mapping
removed) must kill live tokens immediately.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.core.embed_jwt import mint_widget_token
from nexus_api.core.partner_keys import generate_api_key
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Partner,
    PartnerApiKey,
    PartnerTenant,
    Tenant,
    TenantPlan,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


@pytest.fixture
async def embed_world(db_session):
    """Two partners, two tenants, one active WhatsApp channel each."""
    world: dict = {}
    for label in ("a", "b"):
        tenant_id = uuid.uuid4()
        partner_id = uuid.uuid4()
        key_id = uuid.uuid4()
        generated = generate_api_key()
        db_session.add(
            Tenant(
                id=tenant_id,
                name=f"Embed {label}",
                slug=f"embed-{label}-{tenant_id.hex[:6]}",
                plan=TenantPlan.PRO,
            )
        )
        # channels.tenant_id has no ORM relationship to Tenant, so
        # SQLAlchemy can't topo-sort the inserts — flush the tenant first.
        await db_session.flush()
        db_session.add(
            Partner(id=partner_id, name=f"P{label}", slug=f"p{label}-{partner_id.hex[:6]}")
        )
        db_session.add(
            PartnerApiKey(
                id=key_id,
                partner_id=partner_id,
                prefix_snippet=generated.prefix_snippet,
                key_hash=generated.key_hash,
                scopes=["provision", "widget_sessions"],
                allowed_origins=[f"https://{label}.example"],
            )
        )
        db_session.add(
            PartnerTenant(
                partner_id=partner_id,
                external_client_ref=f"client-{label}",
                tenant_id=tenant_id,
            )
        )
        db_session.add(
            Channel(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=f"+5699{label * 7}1",
                status=ChannelStatus.ACTIVE,
            )
        )
        world[label] = {
            "tenant_id": tenant_id,
            "partner_id": partner_id,
            "key_id": key_id,
        }
    await db_session.commit()
    return world


def _token_for(world_entry: dict, *, scope: list[str] | None = None) -> str:
    token, _jti, _exp = mint_widget_token(
        tenant_id=world_entry["tenant_id"],
        partner_id=world_entry["partner_id"],
        key_id=world_entry["key_id"],
        scope=scope if scope is not None else ["widget:send", "widget:connect"],
        allowed_origins=["https://partner.example"],
    )
    return token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_status_reads_own_tenant_channel(client, embed_world) -> None:
    resp = await client.get("/v1/embed/status", headers=_auth(_token_for(embed_world["a"])))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "connected"
    # The RLS-scoped query resolved tenant A's channel, not B's.
    assert body["display_phone_number"] == "+5699aaaaaaa1"


async def test_tokens_do_not_cross_tenants(client, embed_world) -> None:
    ra = await client.get("/v1/embed/status", headers=_auth(_token_for(embed_world["a"])))
    rb = await client.get("/v1/embed/status", headers=_auth(_token_for(embed_world["b"])))
    assert ra.json()["display_phone_number"] != rb.json()["display_phone_number"]


async def test_garbage_token_is_401(client, embed_world) -> None:
    resp = await client.get("/v1/embed/status", headers=_auth("not-a-jwt"))
    assert resp.status_code == 401


async def test_missing_token_is_401(client, embed_world) -> None:
    resp = await client.get("/v1/embed/status")
    assert resp.status_code == 401


async def test_revoking_key_kills_live_token(client, embed_world, db_session) -> None:
    """The JWT is still cryptographically valid — but the per-request
    fail-closed re-check sees the revoked key and rejects."""
    token = _token_for(embed_world["a"])
    ok = await client.get("/v1/embed/status", headers=_auth(token))
    assert ok.status_code == 200

    await db_session.execute(
        sa.update(PartnerApiKey)
        .where(PartnerApiKey.id == embed_world["a"]["key_id"])
        .values(revoked_at=datetime.now(UTC) - timedelta(seconds=1), grace_expires_at=None)
    )
    await db_session.commit()

    dead = await client.get("/v1/embed/status", headers=_auth(token))
    assert dead.status_code == 401


async def test_removing_mapping_kills_live_token(client, embed_world, db_session) -> None:
    token = _token_for(embed_world["a"])
    await db_session.execute(
        sa.delete(PartnerTenant).where(PartnerTenant.partner_id == embed_world["a"]["partner_id"])
    )
    await db_session.commit()
    resp = await client.get("/v1/embed/status", headers=_auth(token))
    assert resp.status_code == 403


async def test_suspending_partner_kills_live_token(client, embed_world, db_session) -> None:
    token = _token_for(embed_world["a"])
    await db_session.execute(
        sa.update(Partner)
        .where(Partner.id == embed_world["a"]["partner_id"])
        .values(status="suspended")
    )
    await db_session.commit()
    resp = await client.get("/v1/embed/status", headers=_auth(token))
    assert resp.status_code == 403


async def test_templates_requires_send_scope(client, embed_world) -> None:
    token = _token_for(embed_world["a"], scope=["widget:connect"])
    resp = await client.get("/v1/embed/templates", headers=_auth(token))
    assert resp.status_code == 403


async def test_partner_config_lists_active_key_origins(client, embed_world, db_session) -> None:
    partner = await db_session.get(Partner, embed_world["a"]["partner_id"])
    resp = await client.get(f"/v1/embed/partner-config?p={partner.slug}")
    assert resp.status_code == 200
    assert resp.json()["allowed_origins"] == ["https://a.example"]
    assert "s-maxage" in resp.headers.get("cache-control", "")


async def test_partner_config_unknown_slug_is_empty(client) -> None:
    resp = await client.get("/v1/embed/partner-config?p=nope-nothing")
    assert resp.status_code == 200
    assert resp.json()["allowed_origins"] == []


async def test_rls_blocks_direct_cross_tenant_channel_read(client, embed_world, db_session) -> None:
    """Belt-and-braces: assert directly in the DB that a session scoped
    to tenant A sees zero channels of tenant B."""
    from .conftest import set_tenant

    async with db_session.begin():
        await set_tenant(db_session, embed_world["a"]["tenant_id"])
        rows = (
            (
                await db_session.execute(
                    sa.select(Channel.provider_identifier).where(
                        Channel.tenant_id == embed_world["b"]["tenant_id"]
                    )
                )
            )
            .scalars()
            .all()
        )
        assert rows == []
