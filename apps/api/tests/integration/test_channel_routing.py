"""Which number does a business-initiated send leave from?

The whole point of this suite is the first class: **a tenant with one active
WhatsApp channel must behave exactly as it did before roles existed.** Every
production tenant is in that shape today (New Air, Barber Supply, Mouna), so a
regression here is a regression for real customers sending real messages.

The second class is the new behaviour, and its most important test is the one
that asserts a *refusal*: two numbers, neither tagged, and the resolver
declines rather than guessing. Guessing means a debt reminder leaving from the
line the owner administers on, to somebody else's customer. That is not a
retryable mistake.

Every read goes through ``scoped_session_factory`` — a session under
``SET LOCAL ROLE nexus_app`` with ``app.tenant_id`` set — because the resolver
carries no tenant filter of its own by design. Reading through the plain
superuser fixture would make these tests pass even if the query leaked across
tenants, which is the one bug they most need to catch.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Tenant,
    TenantPlan,
)
from nexus_api.services.channel_routing import (
    CHANNEL_ROLE_AGENT,
    CHANNEL_ROLE_NOTIFICATIONS,
    ChannelResolutionError,
    active_whatsapp_channels,
    channel_agent_enabled,
    channel_role,
    resolve_whatsapp_channel,
)

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def tenant(db_session) -> uuid.UUID:
    tid = uuid.uuid4()
    db_session.add(
        Tenant(id=tid, name="Routing", slug=f"routing-{tid.hex[:6]}", plan=TenantPlan.PRO)
    )
    await db_session.commit()
    return tid


@pytest_asyncio.fixture
async def as_tenant(scoped_session_factory):
    """Read the way production reads: RLS-scoped session + tenant contextvar."""

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
    db_session,
    *,
    tenant_id: uuid.UUID,
    identifier: str,
    status: ChannelStatus = ChannelStatus.ACTIVE,
    role: str | None = None,
    agent_enabled: bool | None = None,
    channel_type: ChannelType = ChannelType.WHATSAPP,
    provider: str = "meta",
    age_minutes: int = 0,
) -> Channel:
    config: dict[str, object] = {"phone_number_id": f"pnid-{identifier}"}
    if role is not None:
        config["role"] = role
    if agent_enabled is not None:
        config["agent_enabled"] = agent_enabled
    ch = Channel(
        tenant_id=tenant_id,
        type=channel_type,
        provider=provider,
        provider_identifier=identifier,
        config=config,
        status=status,
        # Explicit creation time: "oldest wins" is the documented fallback and
        # a test that relied on insertion order would pass for the wrong
        # reason.
        created_at=datetime.now(UTC) - timedelta(minutes=age_minutes),
    )
    db_session.add(ch)
    await db_session.commit()
    await db_session.refresh(ch)
    return ch


class TestSingleChannelIsUnchanged:
    """The no-op guarantee. These are the production tenants of today."""

    async def test_untagged_single_channel_is_chosen_for_any_role(
        self, db_session, tenant, as_tenant
    ) -> None:
        ch = await _add_channel(db_session, tenant_id=tenant, identifier="+56964321907")
        async with as_tenant(tenant) as s:
            for role in (None, CHANNEL_ROLE_NOTIFICATIONS, CHANNEL_ROLE_AGENT):
                chosen = await resolve_whatsapp_channel(s, role=role)
                assert chosen.id == ch.id, f"role={role} diverged from the single-channel default"

    async def test_paused_channel_is_not_used(self, db_session, tenant, as_tenant) -> None:
        await _add_channel(
            db_session, tenant_id=tenant, identifier="+56900000001", status=ChannelStatus.PAUSED
        )
        async with as_tenant(tenant) as s:
            with pytest.raises(ChannelResolutionError) as err:
                await resolve_whatsapp_channel(s)
        assert err.value.reason == "whatsapp_not_connected"

    async def test_disconnected_sibling_does_not_create_ambiguity(
        self, db_session, tenant, as_tenant
    ) -> None:
        """New Air's exact shape: one live number plus a disconnected leftover.

        The dead row must not make the tenant look multi-channel, or New Air
        would start getting refusals on a setup that works today.
        """
        live = await _add_channel(db_session, tenant_id=tenant, identifier="+56964321907")
        await _add_channel(
            db_session,
            tenant_id=tenant,
            identifier="+56900000000",
            status=ChannelStatus.DISCONNECTED,
        )
        async with as_tenant(tenant) as s:
            chosen_id = (await resolve_whatsapp_channel(s, role=CHANNEL_ROLE_NOTIFICATIONS)).id
        assert chosen_id == live.id

    async def test_web_channels_are_ignored(self, db_session, tenant, as_tenant) -> None:
        """Barber Supply's shape: a WhatsApp line plus qa_playground/web_widget
        rows. Those are not sendable and must never be picked."""
        wa = await _add_channel(db_session, tenant_id=tenant, identifier="+56986183177")
        await _add_channel(
            db_session,
            tenant_id=tenant,
            identifier="web_widget:x",
            channel_type=ChannelType.WEB,
            provider="web_widget",
        )
        async with as_tenant(tenant) as s:
            chosen_id = (await resolve_whatsapp_channel(s)).id
            visible_ids = [c.id for c in await active_whatsapp_channels(s)]
        assert chosen_id == wa.id
        assert visible_ids == [wa.id]

    async def test_no_channel_at_all_refuses(self, tenant, as_tenant) -> None:
        async with as_tenant(tenant) as s:
            with pytest.raises(ChannelResolutionError) as err:
                await resolve_whatsapp_channel(s)
        assert err.value.reason == "whatsapp_not_connected"


class TestTwoChannels:
    """Mouna's target shape: one agent line, one notifications line."""

    async def test_role_selects_the_right_line(self, db_session, tenant, as_tenant) -> None:
        notif = await _add_channel(
            db_session,
            tenant_id=tenant,
            identifier="+584249018017",
            role=CHANNEL_ROLE_NOTIFICATIONS,
            age_minutes=60,
        )
        agent = await _add_channel(
            db_session,
            tenant_id=tenant,
            identifier="+584240000001",
            role=CHANNEL_ROLE_AGENT,
            age_minutes=1,
        )
        async with as_tenant(tenant) as s:
            assert (
                await resolve_whatsapp_channel(s, role=CHANNEL_ROLE_NOTIFICATIONS)
            ).id == notif.id
            assert (await resolve_whatsapp_channel(s, role=CHANNEL_ROLE_AGENT)).id == agent.id

    async def test_role_wins_over_creation_order(self, db_session, tenant, as_tenant) -> None:
        """The notifications line being the NEWER row must still win.

        Mouna is the opposite (the old number becomes notifications), but the
        resolver must not encode either arrangement — otherwise the next
        client to do it the other way gets silently wrong routing.
        """
        await _add_channel(
            db_session,
            tenant_id=tenant,
            identifier="+584240000002",
            role=CHANNEL_ROLE_AGENT,
            age_minutes=90,
        )
        newer_notif = await _add_channel(
            db_session,
            tenant_id=tenant,
            identifier="+584240000003",
            role=CHANNEL_ROLE_NOTIFICATIONS,
            age_minutes=1,
        )
        async with as_tenant(tenant) as s:
            chosen_id = (await resolve_whatsapp_channel(s, role=CHANNEL_ROLE_NOTIFICATIONS)).id
        assert chosen_id == newer_notif.id

    async def test_untagged_pair_refuses_instead_of_guessing(
        self, db_session, tenant, as_tenant
    ) -> None:
        """The safety property this whole module exists for."""
        await _add_channel(db_session, tenant_id=tenant, identifier="+584240000004", age_minutes=90)
        await _add_channel(db_session, tenant_id=tenant, identifier="+584240000005", age_minutes=1)
        async with as_tenant(tenant) as s:
            with pytest.raises(ChannelResolutionError) as err:
                await resolve_whatsapp_channel(s, role=CHANNEL_ROLE_NOTIFICATIONS)
        assert err.value.reason == "channel_role_unassigned"
        assert "notifications" in str(err.value)

    async def test_untagged_pair_still_resolves_when_no_role_is_asked(
        self, db_session, tenant, as_tenant
    ) -> None:
        """Callers that genuinely do not care (health checks, listings) keep
        the oldest-wins fallback — the refusal is scoped to role requests."""
        oldest = await _add_channel(
            db_session, tenant_id=tenant, identifier="+584240000006", age_minutes=90
        )
        await _add_channel(db_session, tenant_id=tenant, identifier="+584240000007", age_minutes=1)
        async with as_tenant(tenant) as s:
            chosen_id = (await resolve_whatsapp_channel(s, role=None)).id
        assert chosen_id == oldest.id

    async def test_partial_tagging_resolves_the_tagged_role(
        self, db_session, tenant, as_tenant
    ) -> None:
        """Only one of the two tagged: the tagged role resolves, the untagged
        one refuses. Half-configured must not silently half-work."""
        notif = await _add_channel(
            db_session,
            tenant_id=tenant,
            identifier="+584240000008",
            role=CHANNEL_ROLE_NOTIFICATIONS,
        )
        await _add_channel(db_session, tenant_id=tenant, identifier="+584240000009")
        async with as_tenant(tenant) as s:
            assert (
                await resolve_whatsapp_channel(s, role=CHANNEL_ROLE_NOTIFICATIONS)
            ).id == notif.id
            with pytest.raises(ChannelResolutionError):
                await resolve_whatsapp_channel(s, role=CHANNEL_ROLE_AGENT)


class TestExplicitChannelId:
    async def test_explicit_id_wins_over_role(self, db_session, tenant, as_tenant) -> None:
        await _add_channel(
            db_session,
            tenant_id=tenant,
            identifier="+584240000010",
            role=CHANNEL_ROLE_NOTIFICATIONS,
        )
        agent = await _add_channel(
            db_session, tenant_id=tenant, identifier="+584240000011", role=CHANNEL_ROLE_AGENT
        )
        async with as_tenant(tenant) as s:
            chosen_id = (
                await resolve_whatsapp_channel(
                    s, role=CHANNEL_ROLE_NOTIFICATIONS, channel_id=agent.id
                )
            ).id
        assert chosen_id == agent.id

    async def test_unknown_id_refuses(self, db_session, tenant, as_tenant) -> None:
        await _add_channel(db_session, tenant_id=tenant, identifier="+584240000012")
        async with as_tenant(tenant) as s:
            with pytest.raises(ChannelResolutionError) as err:
                await resolve_whatsapp_channel(s, channel_id=uuid.uuid4())
        assert err.value.reason == "channel_not_available"

    async def test_paused_id_refuses(self, db_session, tenant, as_tenant) -> None:
        paused = await _add_channel(
            db_session,
            tenant_id=tenant,
            identifier="+584240000013",
            status=ChannelStatus.PAUSED,
        )
        await _add_channel(db_session, tenant_id=tenant, identifier="+584240000014")
        async with as_tenant(tenant) as s:
            with pytest.raises(ChannelResolutionError) as err:
                await resolve_whatsapp_channel(s, channel_id=paused.id)
        assert err.value.reason == "channel_not_available"


class TestCrossTenantIsolation:
    async def test_another_tenants_channel_id_is_not_reachable(
        self, db_session, as_tenant
    ) -> None:
        """An explicit channel_id is caller-supplied input. RLS must make a
        foreign id indistinguishable from a nonexistent one — never a send
        through somebody else's WABA."""
        a, b = uuid.uuid4(), uuid.uuid4()
        db_session.add_all(
            [
                Tenant(id=a, name="A", slug=f"iso-a-{a.hex[:6]}", plan=TenantPlan.PRO),
                Tenant(id=b, name="B", slug=f"iso-b-{b.hex[:6]}", plan=TenantPlan.PRO),
            ]
        )
        await db_session.commit()
        b_channel = await _add_channel(db_session, tenant_id=b, identifier="+560000000099")
        await _add_channel(db_session, tenant_id=a, identifier="+560000000098")

        async with as_tenant(a) as s:
            with pytest.raises(ChannelResolutionError) as err:
                await resolve_whatsapp_channel(s, channel_id=b_channel.id)
            visible_ids = {c.id for c in await active_whatsapp_channels(s)}
        assert err.value.reason == "channel_not_available"
        assert b_channel.id not in visible_ids

    async def test_unscoped_session_raises_instead_of_listing_everyone(
        self, db_session, tenant
    ) -> None:
        """A caller that forgets ``tenant_scoped_session`` must fail loudly.

        Without the tripwire this query has no tenant predicate of its own, so
        an unscoped call would return every tenant's channels and the resolver
        would happily send from the first one.
        """
        await _add_channel(db_session, tenant_id=tenant, identifier="+560000000097")
        with pytest.raises(Exception) as err:
            await active_whatsapp_channels(db_session)
        assert "tenant" in str(err.value).lower()


class TestConfigFlags:
    def _fake(self, config: dict[str, object] | None) -> Channel:
        return Channel(
            tenant_id=uuid.uuid4(),
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier="+1",
            config=config,
            status=ChannelStatus.ACTIVE,
        )

    def test_agent_enabled_defaults_to_true(self) -> None:
        """Absent config means "behave as always". Every channel in production
        predates these flags."""
        assert channel_agent_enabled(self._fake({})) is True
        assert channel_agent_enabled(self._fake(None)) is True
        assert channel_agent_enabled(self._fake({"role": CHANNEL_ROLE_NOTIFICATIONS})) is True

    def test_only_explicit_false_disables_the_agent(self) -> None:
        assert channel_agent_enabled(self._fake({"agent_enabled": False})) is False
        assert channel_agent_enabled(self._fake({"agent_enabled": True})) is True

    def test_unknown_role_reads_as_untagged(self) -> None:
        """Config is operator-editable. A typo must not take a live channel
        out of service — it degrades to the pre-roles behaviour."""
        assert channel_role(self._fake({"role": "notificaciones"})) is None
        assert channel_role(self._fake({"role": ""})) is None
        assert channel_role(self._fake({})) is None
        assert channel_role(self._fake({"role": CHANNEL_ROLE_AGENT})) == CHANNEL_ROLE_AGENT
