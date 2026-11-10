import uuid

import pytest
from sqlalchemy import text

from nexus_api.core.errors import TenantNotFound
from nexus_api.core.tenant_resolver import (
    invalidate_tenant_cache,
    resolve_tenant,
)
from nexus_api.db.models import Channel, ChannelStatus, ChannelType

pytestmark = pytest.mark.asyncio


async def _add_channel(session, tid, identifier, status=ChannelStatus.ACTIVE):
    await session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)})
    await session.execute(text("SET LOCAL ROLE nexus_app"))
    ch = Channel(
        tenant_id=tid,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=identifier,
        status=status,
    )
    session.add(ch)
    await session.flush()
    return ch


async def test_resolves_via_postgres_when_cache_empty(db_session, fake_redis, seed_tenants):
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _add_channel(db_session, tid, "phone-1")
    # Rollback releases SET LOCAL — fine, the resolver bypasses RLS via
    # SECURITY DEFINER.

    resolved = await resolve_tenant(db_session, fake_redis, "meta", "phone-1")
    assert resolved == tid


async def test_resolves_via_cache_on_second_call(db_session, fake_redis, seed_tenants, monkeypatch):
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _add_channel(db_session, tid, "phone-2")
    await resolve_tenant(db_session, fake_redis, "meta", "phone-2")

    # On second call we shouldn't need DB; mock the Postgres path to crash
    # if hit.
    async def boom(*a, **kw):
        raise AssertionError("DB should not be hit on cache hit")

    monkeypatch.setattr(db_session, "execute", boom)
    resolved = await resolve_tenant(db_session, fake_redis, "meta", "phone-2")
    assert resolved == tid


async def test_unknown_identifier_raises(db_session, fake_redis):
    with pytest.raises(TenantNotFound):
        await resolve_tenant(db_session, fake_redis, "meta", "ghost-xyz")


@pytest.mark.parametrize("status", [ChannelStatus.PAUSED, ChannelStatus.DEGRADED])
async def test_a_paused_or_degraded_channel_still_resolves(
    db_session, fake_redis, seed_tenants, status
):
    """Spec 047, requisito 2.2: un número en pausa o con problemas sigue siendo
    del cliente. Su mensaje se guarda y va a la Bandeja con su motivo; antes se
    descartaba en el webhook y no quedaba ni rastro (migración 0176)."""
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _add_channel(db_session, tid, f"{status.value}-1", status=status)
    assert await resolve_tenant(db_session, fake_redis, "meta", f"{status.value}-1") == tid


async def test_a_disconnected_channel_does_not_resolve(db_session, fake_redis, seed_tenants):
    """Desvinculado ya no es del cliente: el número puede ser de otro (spec 021)."""
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _add_channel(db_session, tid, "gone-1", status=ChannelStatus.DISCONNECTED)
    with pytest.raises(TenantNotFound):
        await resolve_tenant(db_session, fake_redis, "meta", "gone-1")


async def test_invalidate_cache(db_session, fake_redis, seed_tenants):
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _add_channel(db_session, tid, "phone-3")
    await resolve_tenant(db_session, fake_redis, "meta", "phone-3")
    assert await fake_redis.get("nexus:tenant_resolve:meta:phone-3") is not None
    await invalidate_tenant_cache(fake_redis, "meta", "phone-3")
    assert await fake_redis.get("nexus:tenant_resolve:meta:phone-3") is None


async def test_corrupt_cache_falls_back_to_db(db_session, fake_redis, seed_tenants):
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _add_channel(db_session, tid, "phone-4")
    await fake_redis.setex("nexus:tenant_resolve:meta:phone-4", 60, "not-a-uuid")
    resolved = await resolve_tenant(db_session, fake_redis, "meta", "phone-4")
    assert resolved == tid


async def test_resolve_returns_uuid_type(db_session, fake_redis, seed_tenants):
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _add_channel(db_session, tid, "phone-5")
    resolved = await resolve_tenant(db_session, fake_redis, "meta", "phone-5")
    assert isinstance(resolved, uuid.UUID)
