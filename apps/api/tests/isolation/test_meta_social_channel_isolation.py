"""Spec 049: Instagram and Messenger channel isolation.

Two new channels route on identifiers anyone can see in a webhook — the
professional account id and the Page id — and keep their token on the
channel row instead of in ``tenant_credentials``. Re-verified here rather
than assumed to inherit the WhatsApp guarantees:

1. ``resolve_channel_tenant(provider, id)`` maps to exactly the owner, a
   near-miss maps to nothing, and the two providers never cross (an IG id
   is not a Page id).
2. The same account or Page cannot be live under two tenants.
3. A disconnected channel stops resolving at once (requirement 5.3: no
   more receiving the moment it is disconnected).
4. The channel credential is invisible from another tenant, even by id.
"""

from __future__ import annotations

import uuid

import pytest
from nexus_channels.meta_social.credentials import SocialCredentials, SocialCredentialsRepository
from sqlalchemy import select, text, update

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import Channel, ChannelStatus, ChannelType

from .conftest import set_tenant

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

IG_A = "17841400000000a01"
IG_B = "17841400000000b01"


async def _add(
    db_session, tenant_id: uuid.UUID, identifier: str, *, provider: str = "meta_instagram"
) -> uuid.UUID:
    channel_id = uuid.uuid4()
    async with db_session.begin():
        await set_tenant(db_session, tenant_id)
        db_session.add(
            Channel(
                id=channel_id,
                tenant_id=tenant_id,
                type=ChannelType.INSTAGRAM
                if provider == "meta_instagram"
                else ChannelType.MESSENGER,
                provider=provider,
                provider_identifier=identifier,
                status=ChannelStatus.ACTIVE,
                config={"account_id": identifier},
                config_encrypted=SocialCredentials(token=f"token-of-{identifier}").to_payload(),
            )
        )
    return channel_id


async def _resolve(db_session, provider: str, identifier: str) -> str | None:
    async with db_session.begin():
        value = await db_session.scalar(
            text("SELECT resolve_channel_tenant(:p, :i)"), {"p": provider, "i": identifier}
        )
    return None if value is None else str(value)


async def test_account_resolves_only_to_its_owner(db_session, tenants_ab):
    a, b = tenants_ab["a"], tenants_ab["b"]
    await _add(db_session, a, IG_A)
    await _add(db_session, b, IG_B)

    assert await _resolve(db_session, "meta_instagram", IG_A) == str(a)
    assert await _resolve(db_session, "meta_instagram", IG_B) == str(b)
    assert await _resolve(db_session, "meta_instagram", "17841400000000a02") is None
    # Same id under the other provider is nobody's.
    assert await _resolve(db_session, "meta_messenger", IG_A) is None


async def test_an_account_cannot_be_live_under_two_tenants(db_session, tenants_ab):
    from sqlalchemy.exc import IntegrityError

    a, b = tenants_ab["a"], tenants_ab["b"]
    await _add(db_session, a, IG_A)
    with pytest.raises(IntegrityError):
        await _add(db_session, b, IG_A)


async def test_a_disconnected_channel_stops_resolving(db_session, tenants_ab):
    a = tenants_ab["a"]
    channel_id = await _add(db_session, a, IG_A)
    async with db_session.begin():
        await set_tenant(db_session, a)
        await db_session.execute(
            update(Channel)
            .where(Channel.id == channel_id)
            .values(status=ChannelStatus.DISCONNECTED)
        )
    assert await _resolve(db_session, "meta_instagram", IG_A) is None


async def test_channel_credentials_are_invisible_across_tenants(db_session, tenants_ab):
    a, b = tenants_ab["a"], tenants_ab["b"]
    channel_a = await _add(db_session, a, IG_A)
    await _add(db_session, b, IG_B)

    async with db_session.begin():
        await set_tenant(db_session, b)
        with tenant_context(b):
            assert await SocialCredentialsRepository(db_session).get(channel_a) is None
        rows = (await db_session.execute(select(Channel.provider_identifier))).scalars().all()
        assert IG_A not in rows

    async with db_session.begin():
        await set_tenant(db_session, a)
        with tenant_context(a):
            creds = await SocialCredentialsRepository(db_session).get(channel_a)
    assert creds is not None and creds.token == f"token-of-{IG_A}"
