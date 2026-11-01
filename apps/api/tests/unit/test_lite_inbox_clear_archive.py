"""«Vaciar» y «Eliminar» un chat, y el filtro por canal de la Bandeja (owner,
2026-11-01). Lo que fija este archivo:

- vaciar deja el chat sin nada que leer y no mueve la ventana de Meta;
- eliminar lo saca de la Bandeja y su id deja de existir para ella;
- nada se borra de verdad (constitución §IV): las filas siguen ahí;
- las dos acciones quedan auditadas, sin contenido;
- otro cliente no alcanza la conversación;
- la lista se filtra por tipo de canal.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Message,
)
from nexus_api.services.inbox_view import _preview, _readable
from tests.conftest import make_inbox

pytestmark = pytest.mark.asyncio

BASE = "/console/lite/inbox/conversations"


async def _rows(db_session, tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> int:
    async with tenant_scoped_session(db_session, tenant_id):
        count = await db_session.scalar(
            sa.select(sa.func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation_id)
        )
    await db_session.commit()
    return int(count or 0)


async def test_clear_empties_the_chat_and_keeps_the_rows(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0, c1 = inbox["conversations"]
    window = datetime.now(UTC) - timedelta(hours=3)
    await db_session.execute(
        sa.update(Conversation).where(Conversation.id == c0).values(last_inbound_at=window)
    )
    await db_session.commit()
    before = await _rows(db_session, w["tenant_id"], c0)
    assert before > 0

    r = await client.post(f"{BASE}/{c0}/clear", headers=inbox["headers"]())
    assert r.status_code == 200, r.text
    assert r.json()["id"] == str(c0)

    thread = (await client.get(f"{BASE}/{c0}/messages", headers=inbox["headers"]())).json()
    assert thread["items"] == []
    listed = (await client.get(BASE, headers=inbox["headers"]())).json()["items"]
    row = next(i for i in listed if i["id"] == str(c0))
    assert row["last_message"] is None
    # La otra conversación no se entera.
    other = (await client.get(f"{BASE}/{c1}/messages", headers=inbox["headers"]())).json()
    assert other["items"] != []

    assert await _rows(db_session, w["tenant_id"], c0) == before
    db_session.expire_all()
    async with tenant_scoped_session(db_session, w["tenant_id"]):
        conv = await db_session.get(Conversation, c0)
        assert conv is not None
        assert conv.last_inbound_at == window
        audit = await db_session.scalar(
            sa.select(AuditLog).where(
                AuditLog.action == "inbox.cleared", AuditLog.target == f"conversation:{c0}"
            )
        )
        assert audit is not None
        assert audit.after_json == {}
    await db_session.commit()


async def test_archive_takes_it_out_of_the_inbox(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0, c1 = inbox["conversations"]
    await db_session.execute(
        sa.update(Conversation)
        .where(Conversation.id == c0)
        .values(status=ConversationStatus.ESCALATED, agent_active=False)
    )
    await db_session.commit()
    before = await _rows(db_session, w["tenant_id"], c0)

    r = await client.post(f"{BASE}/{c0}/archive", headers=inbox["headers"]())
    assert r.status_code == 204, r.text

    assert (await client.get(f"{BASE}/{c0}", headers=inbox["headers"]())).status_code == 404
    for params in ({}, {"filter": "resolved"}, {"filter": "waiting"}):
        listed = await client.get(BASE, headers=inbox["headers"](), params=params)
        assert str(c0) not in [i["id"] for i in listed.json()["items"]]
    counts = (await client.get("/console/lite/inbox/counts", headers=inbox["headers"]())).json()
    assert counts["waiting"] == 0
    assert str(c1) in [
        i["id"] for i in (await client.get(BASE, headers=inbox["headers"]())).json()["items"]
    ]

    assert await _rows(db_session, w["tenant_id"], c0) == before
    db_session.expire_all()
    async with tenant_scoped_session(db_session, w["tenant_id"]):
        conv = await db_session.get(Conversation, c0)
        assert conv is not None
        assert conv.attended_at is None
        # Si vuelve a escribir, responde el agente.
        assert conv.status == ConversationStatus.CLOSED
        assert conv.agent_active is True
        assert await db_session.scalar(
            sa.select(AuditLog).where(
                AuditLog.action == "inbox.archived", AuditLog.target == f"conversation:{c0}"
            )
        )
    await db_session.commit()


async def test_another_clients_conversation_does_not_exist(
    client, db_session, console_world
) -> None:
    a, b = console_world["a"], console_world["b"]
    mine = await make_inbox(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    theirs = await make_inbox(db_session, partner_id=b["partner_id"], tenant_id=b["tenant_id"])
    target = theirs["conversations"][0]
    assert (
        await client.post(f"{BASE}/{target}/clear", headers=mine["headers"]())
    ).status_code == 404
    assert (
        await client.post(f"{BASE}/{target}/archive", headers=mine["headers"]())
    ).status_code == 404


async def test_the_list_filters_by_channel(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0, c1 = inbox["conversations"]
    async with tenant_scoped_session(db_session, w["tenant_id"]):
        conv = await db_session.get(Conversation, c1)
        assert conv is not None
        ig = Channel(
            tenant_id=w["tenant_id"],
            type=ChannelType.INSTAGRAM,
            provider="meta_instagram",
            provider_identifier=f"ig-{uuid.uuid4().hex[:8]}",
            status=ChannelStatus.ACTIVE,
            config={},
        )
        db_session.add(ig)
        await db_session.flush()
        conv.channel_id = ig.id
    await db_session.commit()

    async def ids(**params: str) -> list[str]:
        r = await client.get(BASE, headers=inbox["headers"](), params=params)
        assert r.status_code == 200, r.text
        return [i["id"] for i in r.json()["items"]]

    assert await ids(channel="instagram") == [str(c1)]
    assert await ids(channel="whatsapp") == [str(c0)]
    assert await ids(channel="messenger") == []
    assert sorted(await ids()) == sorted([str(c0), str(c1)])
    body = (await client.get(BASE, headers=inbox["headers"]())).json()
    assert body["channel_kinds"] == ["instagram", "whatsapp"]
    assert (
        await client.get(BASE, headers=inbox["headers"](), params={"channel": "paloma"})
    ).status_code == 422


async def test_a_reaction_reads_as_its_emoji() -> None:
    raw = "[reaction:❤:on=bmV3X2lnX2RtX2l0ZW06MTpJR01lc3NhZA]"
    assert _readable(raw) == "❤"
    assert _preview(raw) == "❤"
    assert _readable("[reaction:(removed):on=abc]") == "✕"
    assert _readable("hello [reaction:x:on=y]") == "hello [reaction:x:on=y]"
    assert _readable(None) is None


async def test_the_agent_forgets_what_the_inbox_stopped_showing(
    client, db_session, console_world
) -> None:
    from nexus_worker.runtime.pipeline import _load_recent_history

    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    cleared, archived = inbox["conversations"]
    assert await _load_recent_history(w["tenant_id"], str(cleared)) != []
    assert await _load_recent_history(w["tenant_id"], str(archived)) != []

    r = await client.post(f"{BASE}/{cleared}/clear", headers=inbox["headers"]())
    assert r.status_code == 200, r.text
    assert await _load_recent_history(w["tenant_id"], str(cleared)) == []

    # Eliminada, el siguiente mensaje marca desde dónde se lee (``_mark_attended``).
    r = await client.post(f"{BASE}/{archived}/archive", headers=inbox["headers"]())
    assert r.status_code == 204, r.text
    now = datetime.now(UTC)
    await db_session.execute(
        sa.update(Conversation).where(Conversation.id == archived).values(attended_at=now)
    )
    await db_session.commit()
    assert await _load_recent_history(w["tenant_id"], str(archived)) == []
