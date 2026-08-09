"""Which number does a Meta send actually leave from, at the credential layer?

``resolve_send_credentials`` answers two questions that are scoped
differently, and conflating them was a real bug:

- the ``phone_number_id`` belongs to the NUMBER;
- the BISUAT belongs to the WABA (shared by numbers under it).

The adapter used to read both off ``tenant_credentials``, which holds exactly
one row per tenant. Connecting a second number overwrote that row, and from
that instant every outbound of the tenant — including the agent's replies on
the *first* line — went out through the second number. Nothing failed; the
wrong number simply started writing to people.

So the tests below come in two halves: the fallback path that every tenant in
production is on today and which must not move, and the two-number path with
its per-channel override.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from nexus_channels.whatsapp_meta.credentials import (
    ChannelCredentialsRepository,
    MetaCredentials,
    MetaCredentialsRepository,
    resolve_send_credentials,
)

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Tenant,
    TenantPlan,
)

pytestmark = pytest.mark.integration


def _creds(*, pnid: str, token: str, waba: str = "WABA-1") -> MetaCredentials:
    return MetaCredentials(
        bisuat=token,
        waba_id=waba,
        phone_number_id=pnid,
        business_id="BIZ-1",
        display_phone_number="+584249018017",
        verify_token="vt-" + pnid,
    )


@pytest_asyncio.fixture
async def tenant(db_session) -> uuid.UUID:
    tid = uuid.uuid4()
    db_session.add(Tenant(id=tid, name="Creds", slug=f"creds-{tid.hex[:6]}", plan=TenantPlan.PRO))
    await db_session.commit()
    return tid


@pytest_asyncio.fixture
async def as_tenant(scoped_session_factory):
    @asynccontextmanager
    async def _scoped(tenant_id: uuid.UUID) -> AsyncIterator:
        with tenant_context(tenant_id):
            session = await scoped_session_factory(tenant_id)
            try:
                yield session
            finally:
                await session.rollback()
                await session.close()

    return _scoped


async def _add_channel(
    db_session, *, tenant_id: uuid.UUID, identifier: str, pnid: str | None
) -> uuid.UUID:
    ch = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=identifier,
        config={"phone_number_id": pnid} if pnid else {},
        status=ChannelStatus.ACTIVE,
    )
    db_session.add(ch)
    await db_session.commit()
    await db_session.refresh(ch)
    return ch.id


async def _seed_tenant_credentials(as_tenant, tenant_id: uuid.UUID, creds: MetaCredentials) -> None:
    async with as_tenant(tenant_id) as s:
        await MetaCredentialsRepository(s).upsert(creds)
        await s.commit()


class TestSingleNumberFallback:
    """Everything currently in production. None of this may change."""

    async def test_channel_without_own_token_uses_the_tenant_one(
        self, db_session, tenant, as_tenant
    ) -> None:
        channel_id = await _add_channel(
            db_session, tenant_id=tenant, identifier="+56964321907", pnid="PNID-A"
        )
        await _seed_tenant_credentials(as_tenant, tenant, _creds(pnid="PNID-A", token="TOK-A"))

        async with as_tenant(tenant) as s:
            pnid, token = await resolve_send_credentials(s, channel_id=channel_id)
        assert (pnid, token) == ("PNID-A", "TOK-A")

    async def test_channel_config_without_pnid_falls_back_to_the_credential(
        self, db_session, tenant, as_tenant
    ) -> None:
        """Older channel rows may carry no ``phone_number_id`` in config."""
        channel_id = await _add_channel(
            db_session, tenant_id=tenant, identifier="+56964321908", pnid=None
        )
        await _seed_tenant_credentials(as_tenant, tenant, _creds(pnid="PNID-A", token="TOK-A"))

        async with as_tenant(tenant) as s:
            pnid, token = await resolve_send_credentials(s, channel_id=channel_id)
        assert (pnid, token) == ("PNID-A", "TOK-A")

    async def test_no_channel_id_still_resolves_the_tenant_credential(
        self, tenant, as_tenant
    ) -> None:
        """The media-download path passes no channel when it does not know one."""
        await _seed_tenant_credentials(as_tenant, tenant, _creds(pnid="PNID-A", token="TOK-A"))
        async with as_tenant(tenant) as s:
            pnid, token = await resolve_send_credentials(s)
        assert (pnid, token) == ("PNID-A", "TOK-A")

    async def test_no_credentials_anywhere_raises(self, db_session, tenant, as_tenant) -> None:
        channel_id = await _add_channel(
            db_session, tenant_id=tenant, identifier="+56964321909", pnid="PNID-A"
        )
        async with as_tenant(tenant) as s:
            with pytest.raises(LookupError):
                await resolve_send_credentials(s, channel_id=channel_id)


class TestTwoNumbers:
    async def test_each_channel_sends_from_its_own_number(
        self, db_session, tenant, as_tenant
    ) -> None:
        """The bug this module exists to prevent, stated as an assertion."""
        notif = await _add_channel(
            db_session, tenant_id=tenant, identifier="+584249018017", pnid="PNID-NOTIF"
        )
        agent = await _add_channel(
            db_session, tenant_id=tenant, identifier="+584240000001", pnid="PNID-AGENT"
        )
        # Tenant row points at the notifications number (it was connected first).
        await _seed_tenant_credentials(
            as_tenant, tenant, _creds(pnid="PNID-NOTIF", token="TOK-SHARED")
        )

        async with as_tenant(tenant) as s:
            notif_pnid, notif_token = await resolve_send_credentials(s, channel_id=notif)
            agent_pnid, agent_token = await resolve_send_credentials(s, channel_id=agent)

        assert notif_pnid == "PNID-NOTIF"
        assert agent_pnid == "PNID-AGENT", (
            "the agent line must send from its own number, not from whichever "
            "one the tenant credential points at"
        )
        # Same WABA → one token serves both.
        assert notif_token == agent_token == "TOK-SHARED"

    async def test_channel_token_overrides_the_tenant_one(
        self, db_session, tenant, as_tenant
    ) -> None:
        """Separate WABAs: each number carries its own BISUAT."""
        agent = await _add_channel(
            db_session, tenant_id=tenant, identifier="+584240000002", pnid="PNID-AGENT"
        )
        await _seed_tenant_credentials(
            as_tenant, tenant, _creds(pnid="PNID-NOTIF", token="TOK-NOTIF")
        )
        async with as_tenant(tenant) as s:
            await ChannelCredentialsRepository(s).upsert(
                agent, _creds(pnid="PNID-AGENT", token="TOK-AGENT", waba="WABA-2")
            )
            await s.commit()

        async with as_tenant(tenant) as s:
            pnid, token = await resolve_send_credentials(s, channel_id=agent)
        assert (pnid, token) == ("PNID-AGENT", "TOK-AGENT")

    async def test_channel_token_does_not_leak_to_the_other_channel(
        self, db_session, tenant, as_tenant
    ) -> None:
        notif = await _add_channel(
            db_session, tenant_id=tenant, identifier="+584240000003", pnid="PNID-NOTIF"
        )
        agent = await _add_channel(
            db_session, tenant_id=tenant, identifier="+584240000004", pnid="PNID-AGENT"
        )
        await _seed_tenant_credentials(
            as_tenant, tenant, _creds(pnid="PNID-NOTIF", token="TOK-NOTIF")
        )
        async with as_tenant(tenant) as s:
            await ChannelCredentialsRepository(s).upsert(
                agent, _creds(pnid="PNID-AGENT", token="TOK-AGENT", waba="WABA-2")
            )
            await s.commit()

        async with as_tenant(tenant) as s:
            notif_creds = await resolve_send_credentials(s, channel_id=notif)
        assert notif_creds == ("PNID-NOTIF", "TOK-NOTIF")


class TestIsolation:
    async def test_another_tenants_channel_reads_as_absent(self, db_session, as_tenant) -> None:
        """``channel_id`` reaches this function from a message row. RLS must
        make a foreign one fall back to the caller's own credential rather
        than decrypt somebody else's token."""
        a, b = uuid.uuid4(), uuid.uuid4()
        db_session.add_all(
            [
                Tenant(id=a, name="A", slug=f"ca-{a.hex[:6]}", plan=TenantPlan.PRO),
                Tenant(id=b, name="B", slug=f"cb-{b.hex[:6]}", plan=TenantPlan.PRO),
            ]
        )
        await db_session.commit()
        b_channel = await _add_channel(
            db_session, tenant_id=b, identifier="+560000000091", pnid="PNID-B"
        )
        await _seed_tenant_credentials(as_tenant, b, _creds(pnid="PNID-B", token="TOK-B"))
        await _seed_tenant_credentials(as_tenant, a, _creds(pnid="PNID-A", token="TOK-A"))
        async with as_tenant(b) as s:
            await ChannelCredentialsRepository(s).upsert(
                b_channel, _creds(pnid="PNID-B", token="TOK-B-CHANNEL", waba="WABA-B")
            )
            await s.commit()

        async with as_tenant(a) as s:
            pnid, token = await resolve_send_credentials(s, channel_id=b_channel)
        assert (pnid, token) == ("PNID-A", "TOK-A")
        assert token != "TOK-B-CHANNEL"

    async def test_unscoped_session_raises(self, db_session, tenant) -> None:
        with pytest.raises(Exception) as err:
            await resolve_send_credentials(db_session)
        assert "tenant" in str(err.value).lower()
