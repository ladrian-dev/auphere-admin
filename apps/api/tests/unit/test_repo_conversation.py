import uuid

import pytest
from sqlalchemy import text

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import Channel, ChannelType, Conversation, Customer
from nexus_api.repositories import ConversationRepository

pytestmark = pytest.mark.asyncio


async def _seed_conversations(session, tid, n):
    await session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)})
    await session.execute(text("SET LOCAL ROLE nexus_app"))
    channel = Channel(
        tenant_id=tid,
        type=ChannelType.WHATSAPP,
        provider="ycloud",
        provider_identifier=f"pid-{uuid.uuid4()}",
    )
    customer = Customer(tenant_id=tid, identifier=f"cust-{uuid.uuid4()}")
    session.add_all([channel, customer])
    await session.flush()
    convs = []
    for _ in range(n):
        c = Conversation(tenant_id=tid, channel_id=channel.id, customer_id=customer.id)
        session.add(c)
        convs.append(c)
    await session.flush()
    return convs


async def test_list_paginated_returns_all_when_under_limit(db_session, seed_tenants):
    tid = seed_tenants["a"]
    with tenant_context(tid):
        async with db_session.begin():
            await _seed_conversations(db_session, tid, 3)
            page = await ConversationRepository(db_session).list_paginated(limit=10)
            assert len(page.items) == 3
            assert page.next_cursor is None


async def test_list_paginated_cursors_when_more(db_session, seed_tenants):
    tid = seed_tenants["a"]
    with tenant_context(tid):
        async with db_session.begin():
            await _seed_conversations(db_session, tid, 5)
            repo = ConversationRepository(db_session)
            page1 = await repo.list_paginated(limit=2)
            assert len(page1.items) == 2
            assert page1.next_cursor is not None
            page2 = await repo.list_paginated(limit=2, cursor=page1.next_cursor)
            assert len(page2.items) == 2
            assert page2.next_cursor is not None
            page3 = await repo.list_paginated(limit=2, cursor=page2.next_cursor)
            assert len(page3.items) == 1
            assert page3.next_cursor is None


async def test_list_paginated_does_not_repeat(db_session, seed_tenants):
    tid = seed_tenants["a"]
    with tenant_context(tid):
        async with db_session.begin():
            await _seed_conversations(db_session, tid, 5)
            repo = ConversationRepository(db_session)
            page1 = await repo.list_paginated(limit=2)
            page2 = await repo.list_paginated(limit=2, cursor=page1.next_cursor)
            ids_seen = {c.id for c in page1.items} | {c.id for c in page2.items}
            assert len(ids_seen) == 4


async def test_get_returns_conversation(db_session, seed_tenants):
    tid = seed_tenants["a"]
    with tenant_context(tid):
        async with db_session.begin():
            convs = await _seed_conversations(db_session, tid, 1)
            cid = convs[0].id
            repo = ConversationRepository(db_session)
            fetched = await repo.get(cid)
            assert fetched is not None
            assert fetched.id == cid


async def test_get_returns_none_when_not_in_tenant(db_session, seed_tenants):
    tid = seed_tenants["a"]
    with tenant_context(tid):
        async with db_session.begin():
            repo = ConversationRepository(db_session)
            assert await repo.get(uuid.uuid4()) is None
