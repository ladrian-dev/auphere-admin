"""Spec 024 (Requisito 3.2): Conversaciones counts the inbounds the allowed
list left without an answer, per conversation and in the period stats,
from ``messages.skipped_reason``.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from nexus_api.db.models import (
    Channel,
    ChannelType,
    Conversation,
    Customer,
    Message,
    MessageDirection,
)

pytestmark = pytest.mark.asyncio


async def _seed(session, tenant_id: uuid.UUID, *, unanswered: int, answered: int) -> uuid.UUID:
    await session.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
    )
    await session.execute(text("SET LOCAL ROLE nexus_app"))
    ch = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=str(uuid.uuid4()),
    )
    cu = Customer(tenant_id=tenant_id, identifier=str(uuid.uuid4()))
    session.add_all([ch, cu])
    await session.flush()
    conv = Conversation(tenant_id=tenant_id, channel_id=ch.id, customer_id=cu.id)
    session.add(conv)
    await session.flush()
    for _ in range(unanswered):
        session.add(
            Message(
                tenant_id=tenant_id,
                conversation_id=conv.id,
                direction=MessageDirection.INBOUND,
                content="hola",
                skipped_reason="not_admin",
            )
        )
    for _ in range(answered):
        session.add(
            Message(
                tenant_id=tenant_id,
                conversation_id=conv.id,
                direction=MessageDirection.INBOUND,
                content="hola",
            )
        )
        session.add(
            Message(
                tenant_id=tenant_id,
                conversation_id=conv.id,
                direction=MessageDirection.OUTBOUND,
                content="buenas",
            )
        )
    await session.flush()
    await session.commit()
    return conv.id


async def test_each_conversation_says_how_many_went_unanswered_and_why(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    silent = await _seed(db_session, a["tenant_id"], unanswered=3, answered=0)
    normal = await _seed(db_session, a["tenant_id"], unanswered=0, answered=2)

    page = await client.get(f"/console/clients/{a['ref']}/conversations", headers=a["headers"]())
    assert page.status_code == 200, page.text
    rows = {r["id"]: r for r in page.json()["items"]}
    assert rows[str(silent)]["unanswered"] == {"count": 3, "reason": "not_admin"}
    assert rows[str(silent)]["inbound_messages"] == 3
    assert rows[str(normal)]["unanswered"] is None


async def test_the_period_stats_count_them_too(client, console_world, db_session) -> None:
    a = console_world["a"]
    await _seed(db_session, a["tenant_id"], unanswered=2, answered=1)
    await _seed(db_session, a["tenant_id"], unanswered=1, answered=0)

    stats = await client.get(
        f"/console/clients/{a['ref']}/conversations/stats", headers=a["headers"]()
    )
    assert stats.status_code == 200, stats.text
    assert stats.json()["unanswered_messages"] == 3
    assert stats.json()["failed_messages"] == 0
