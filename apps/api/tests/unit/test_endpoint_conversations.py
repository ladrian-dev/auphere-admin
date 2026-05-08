import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _seed_one(session, tid):
    from nexus_api.db.models import Channel, ChannelType, Conversation, Customer

    await session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)})
    await session.execute(text("SET LOCAL ROLE nexus_app"))
    ch = Channel(
        tenant_id=tid,
        type=ChannelType.WHATSAPP,
        provider="ycloud",
        provider_identifier=str(uuid.uuid4()),
    )
    cu = Customer(tenant_id=tid, identifier=str(uuid.uuid4()))
    session.add_all([ch, cu])
    await session.flush()
    conv = Conversation(tenant_id=tid, channel_id=ch.id, customer_id=cu.id)
    session.add(conv)
    await session.flush()


async def test_list_conversations_empty(client, admin_headers, seed_tenants):
    tid = seed_tenants["a"]
    r = await client.get(f"/admin/tenants/{tid}/conversations", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


async def test_list_conversations_with_data(client, admin_headers, seed_tenants, db_session):
    tid = seed_tenants["a"]
    async with db_session.begin():
        for _ in range(3):
            await _seed_one(db_session, tid)
    r = await client.get(f"/admin/tenants/{tid}/conversations", headers=admin_headers)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 3


async def test_list_conversations_pagination(client, admin_headers, seed_tenants, db_session):
    tid = seed_tenants["a"]
    async with db_session.begin():
        for _ in range(5):
            await _seed_one(db_session, tid)
    r1 = await client.get(
        f"/admin/tenants/{tid}/conversations?limit=2",
        headers=admin_headers,
    )
    assert len(r1.json()["items"]) == 2
    cursor = r1.json()["next_cursor"]
    assert cursor
    r2 = await client.get(
        f"/admin/tenants/{tid}/conversations?limit=2&cursor={cursor}",
        headers=admin_headers,
    )
    assert len(r2.json()["items"]) == 2


async def test_list_conversations_limit_validation(client, admin_headers, seed_tenants):
    tid = seed_tenants["a"]
    r = await client.get(
        f"/admin/tenants/{tid}/conversations?limit=0",
        headers=admin_headers,
    )
    assert r.status_code == 422
    r = await client.get(
        f"/admin/tenants/{tid}/conversations?limit=999",
        headers=admin_headers,
    )
    assert r.status_code == 422


async def test_list_conversations_unknown_tenant(client, admin_headers):
    r = await client.get(
        f"/admin/tenants/{uuid.uuid4()}/conversations",
        headers=admin_headers,
    )
    assert r.status_code == 404


async def test_list_conversations_requires_auth(client, seed_tenants):
    tid = seed_tenants["a"]
    r = await client.get(f"/admin/tenants/{tid}/conversations")
    assert r.status_code == 401
