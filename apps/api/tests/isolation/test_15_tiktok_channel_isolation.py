"""Extra: TikTok channel isolation.

A new channel is new isolation surface. TikTok routes on an opaque
``business_id`` rather than a phone number, and its OAuth callback carries
the tenant inside a query parameter instead of a URL path, so both the
resolution path and the authorisation path are re-verified here rather than
assumed to inherit the WhatsApp guarantees.

Three properties:

1. ``resolve_channel_tenant('tiktok', <business_id>)`` maps to exactly the
   owning tenant, and a channel belonging to tenant B is invisible to A.
2. TikTok credentials live under the same RLS as every other integration.
3. The OAuth ``state`` cannot be repointed at another tenant — the only
   thing standing between an unauthenticated callback and a cross-tenant
   write.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from nexus_api.db.models import Channel, ChannelStatus, ChannelType, TenantCredentials

from .conftest import set_tenant

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

BUSINESS_A = "7100000000000000001"
BUSINESS_B = "7100000000000000002"


async def _add_tiktok_channel(db_session, tenant_id: uuid.UUID, business_id: str) -> None:
    async with db_session.begin():
        await set_tenant(db_session, tenant_id)
        db_session.add(
            Channel(
                tenant_id=tenant_id,
                type=ChannelType.TIKTOK,
                provider="tiktok",
                provider_identifier=business_id,
                status=ChannelStatus.ACTIVE,
                config={"business_id": business_id},
            )
        )


async def test_tiktok_channels_are_invisible_across_tenants(db_session, tenants_ab):
    a, b = tenants_ab["a"], tenants_ab["b"]
    await _add_tiktok_channel(db_session, a, BUSINESS_A)
    await _add_tiktok_channel(db_session, b, BUSINESS_B)

    async with db_session.begin():
        await set_tenant(db_session, a)
        rows = (
            (await db_session.execute(select(Channel).where(Channel.provider == "tiktok")))
            .scalars()
            .all()
        )
        assert [r.provider_identifier for r in rows] == [BUSINESS_A]


async def test_business_id_resolves_only_to_its_owning_tenant(db_session, tenants_ab):
    """The webhook resolves a tenant from an attacker-visible identifier, so
    the mapping has to be exact — a near-miss must resolve to nothing, not to
    a neighbouring tenant."""
    a, b = tenants_ab["a"], tenants_ab["b"]
    await _add_tiktok_channel(db_session, a, BUSINESS_A)
    await _add_tiktok_channel(db_session, b, BUSINESS_B)

    async with db_session.begin():
        resolved_a = await db_session.scalar(
            text("SELECT resolve_channel_tenant('tiktok', :i)"), {"i": BUSINESS_A}
        )
        resolved_b = await db_session.scalar(
            text("SELECT resolve_channel_tenant('tiktok', :i)"), {"i": BUSINESS_B}
        )
        unknown = await db_session.scalar(
            text("SELECT resolve_channel_tenant('tiktok', :i)"), {"i": "7100000000000000999"}
        )

    assert str(resolved_a) == str(a)
    assert str(resolved_b) == str(b)
    assert unknown is None


async def test_the_same_business_id_cannot_be_claimed_by_two_tenants(db_session, tenants_ab):
    """``uq_channels_type_provider_id`` is what stops a second tenant from
    hijacking inbound traffic by registering the same Business Account."""
    from sqlalchemy.exc import IntegrityError

    a, b = tenants_ab["a"], tenants_ab["b"]
    await _add_tiktok_channel(db_session, a, BUSINESS_A)

    with pytest.raises(IntegrityError):
        await _add_tiktok_channel(db_session, b, BUSINESS_A)


async def test_tiktok_credentials_are_scoped_like_every_other_integration(db_session, tenants_ab):
    a, b = tenants_ab["a"], tenants_ab["b"]

    async with db_session.begin():
        await set_tenant(db_session, a)
        db_session.add(
            TenantCredentials(
                tenant_id=a,
                integration="tiktok_bm",
                encrypted_payload=b"A-tiktok-token",
            )
        )
    async with db_session.begin():
        await set_tenant(db_session, b)
        db_session.add(
            TenantCredentials(
                tenant_id=b,
                integration="tiktok_bm",
                encrypted_payload=b"B-tiktok-token",
            )
        )

    async with db_session.begin():
        await set_tenant(db_session, b)
        rows = (
            (
                await db_session.execute(
                    select(TenantCredentials).where(TenantCredentials.integration == "tiktok_bm")
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].encrypted_payload == b"B-tiktok-token"


async def test_oauth_state_cannot_be_repointed_at_another_tenant(tenants_ab):
    """TikTok's callback arrives with no admin token, so the signed state is
    the only thing naming the tenant. Forging it would be a cross-tenant
    write."""
    from nexus_api.services.tiktok_oauth_state import (
        OAuthStateInvalid,
        sign_oauth_state,
        verify_oauth_state,
    )

    a, b = tenants_ab["a"], tenants_ab["b"]
    secret = "isolation-test-secret-at-least-32-chars"

    state_for_a, _ = sign_oauth_state(tenant_id=a, secret=secret)
    assert verify_oauth_state(state=state_for_a, secret=secret).tenant_id == a

    # Tenant B mints its own state; it can never verify as tenant A.
    state_for_b, _ = sign_oauth_state(tenant_id=b, secret=secret)
    assert verify_oauth_state(state=state_for_b, secret=secret).tenant_id == b

    # And a state signed under a different secret is refused outright.
    forged, _ = sign_oauth_state(tenant_id=a, secret="attacker-controlled-secret-value")
    with pytest.raises(OAuthStateInvalid):
        verify_oauth_state(state=forged, secret=secret)
