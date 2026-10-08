"""Spec 030 — la lista de la Bandeja (Requisitos 6.1, 6.3, 7.1 a 7.4 y 7.6).

``GET /console/lite/inbox/conversations`` y ``GET …/inbox/counts``. Lo que
fija este archivo:

- el orden es la última actividad (``last_message_at desc, id``) y el cursor
  recorre la lista sin repetir;
- las resueltas no salen por defecto y el Playground no sale nunca;
- los filtros ``unread``, ``waiting`` y ``resolved`` y la búsqueda por nombre,
  teléfono y texto;
- «sin leer» es **de cada persona**: lo que lee una no lo lee la otra;
- la vista previa se corta a 140 caracteres y dice quién escribió, y «tú»
  solo para quien lo escribió;
- el estado se deriva sin columna nueva (D12);
- sin módulo Bandeja no se entra, y una persona del partner tampoco.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import (
    Conversation,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageStatus,
)
from tests.conftest import add_client_member, make_client_access, make_inbox

pytestmark = pytest.mark.asyncio

LIST = "/console/lite/inbox/conversations"
COUNTS = "/console/lite/inbox/counts"


async def _set(db_session, conversation_id: uuid.UUID, **values: Any) -> None:
    await db_session.execute(
        sa.update(Conversation).where(Conversation.id == conversation_id).values(**values)
    )
    await db_session.commit()


async def _ids(client, headers, **params: str) -> list[str]:
    """``headers`` es la fábrica: cada token de la consola vale una vez."""
    r = await client.get(LIST, headers=headers(), params=params)
    assert r.status_code == 200, r.text
    return [i["id"] for i in r.json()["items"]]


async def test_order_hides_playground_and_resolved(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], conversations=3
    )
    c0, c1, c2 = (str(c) for c in inbox["conversations"])
    await _set(db_session, inbox["conversations"][2], status=ConversationStatus.CLOSED)

    r = await client.get(LIST, headers=inbox["headers"]())
    assert r.status_code == 200, r.text
    body = r.json()
    assert [i["id"] for i in body["items"]] == [c0, c1]
    assert str(inbox["playground_conversation"]) not in [i["id"] for i in body["items"]]
    assert body["has_any"] is True
    assert body["channel_kinds"] == ["whatsapp"]

    first = body["items"][0]
    assert first["contact"]["name"] == "Contacto 0"
    assert first["channel"] == {"kind": "whatsapp"}
    assert first["state"] == "agent"
    assert first["assignee"] is None
    assert first["unread"] is True
    assert first["last_message"]["author"]["kind"] == "agent"
    assert first["last_message"]["preview"] == "Hola contacto 0, ¿en qué te ayudo?"

    assert await _ids(client, inbox["headers"], filter="resolved") == [c2]


async def test_filters_and_counts_are_per_person(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0, c1 = inbox["conversations"]
    other = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )
    await _set(db_session, c1, status=ConversationStatus.ESCALATED, agent_active=False)

    me = inbox["headers"]
    assert await _ids(client, me, filter="waiting") == [str(c1)]
    assert (await client.get(COUNTS, headers=me())).json() == {"unread": 2, "waiting": 1}

    assert (await client.post(f"{LIST}/{c0}/read", headers=me())).status_code == 204
    assert await _ids(client, me, filter="unread") == [str(c1)]
    assert (await client.get(COUNTS, headers=me())).json() == {"unread": 1, "waiting": 1}
    # Lo que leyó una persona sigue sin leer para la otra.
    assert (await client.get(COUNTS, headers=other["headers"]())).json()["unread"] == 2

    assert (await client.post(f"{LIST}/{c0}/unread", headers=me())).status_code == 204
    assert (await client.get(COUNTS, headers=me())).json()["unread"] == 2

    # Un entrante nuevo después de leer vuelve a contar.
    assert (await client.post(f"{LIST}/{c0}/read", headers=me())).status_code == 204
    await _set(db_session, c0, last_inbound_at=datetime.now(UTC))
    assert (await client.get(COUNTS, headers=me())).json()["unread"] == 2


async def test_search_by_name_phone_and_text(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0, c1 = (str(c) for c in inbox["conversations"])
    phone = (
        await db_session.execute(
            sa.text("SELECT identifier FROM customers WHERE id = :id"),
            {"id": inbox["customers"][0]},
        )
    ).scalar_one()

    me = inbox["headers"]
    assert await _ids(client, me, q="Contacto 1") == [c1]
    assert await _ids(client, me, q=phone[-6:]) == [c0]
    assert await _ids(client, me, q="soy el contacto 0") == [c0]
    assert await _ids(client, me, q="nadie escribió esto") == []


async def test_cursor_walks_the_list_once(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], conversations=3
    )
    me = inbox["headers"]
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(4):
        params = {"limit": "1", **({"cursor": cursor} if cursor else {})}
        body = (await client.get(LIST, headers=me(), params=params)).json()
        seen += [i["id"] for i in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert seen == [str(c) for c in inbox["conversations"]]

    bad = await client.get(LIST, headers=me(), params={"cursor": "no-es-un-cursor"})
    assert bad.status_code == 422


async def test_preview_is_cut_and_says_who_wrote(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    other = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )
    c0 = inbox["conversations"][0]
    now = datetime.now(UTC)
    db_session.add(
        Message(
            tenant_id=w["tenant_id"],
            conversation_id=c0,
            direction=MessageDirection.OUTBOUND,
            status=MessageStatus.SENT,
            content="Te confirmo la cita. " * 20,
            actor_kind="member",
            actor_id=inbox["member"]["membership_id"],
            created_at=now,
        )
    )
    await _set(db_session, c0, last_message_at=now)

    mine = (await client.get(LIST, headers=inbox["headers"]())).json()["items"][0]
    last = mine["last_message"]
    assert len(last["preview"]) <= 140
    assert last["preview"].endswith("…")
    assert last["author"] == {"kind": "member", "name": "Valeria Ríos", "is_me": True}

    theirs = (await client.get(LIST, headers=other["headers"]())).json()["items"][0]
    assert theirs["last_message"]["author"]["is_me"] is False


async def test_state_is_derived(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], conversations=3
    )
    c0, c1, c2 = inbox["conversations"]
    await _set(db_session, c0, agent_active=False, assigned_user_id=inbox["member"]["user_id"])
    await _set(db_session, c1, status=ConversationStatus.ESCALATED, agent_active=False)

    items = (await client.get(LIST, headers=inbox["headers"]())).json()["items"]
    states = {i["id"]: i["state"] for i in items}
    assert states == {str(c0): "person", str(c1): "waiting", str(c2): "agent"}
    person = next(i for i in items if i["id"] == str(c0))
    assert person["assignee"] == {"kind": "member", "name": "Valeria Ríos", "is_me": True}


async def test_an_empty_inbox_says_so(client, db_session, console_world) -> None:
    w = console_world["a"]
    await make_client_access(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    member = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )
    body = (await client.get(LIST, headers=member["headers"]())).json()
    assert body["items"] == []
    assert body["has_any"] is False
    assert body["next_cursor"] is None
    assert body["counts"] == {"unread": 0, "waiting": 0}


async def test_without_the_inbox_module_there_is_no_inbox(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    await make_client_access(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], modules=("panel",)
    )
    member = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )
    assert (await client.get(LIST, headers=member["headers"]())).status_code == 403
    assert (await client.get(COUNTS, headers=member["headers"]())).status_code == 403
    # Una persona del partner no alcanza la Bandeja de nadie.
    assert (await client.get(LIST, headers=w["headers"]())).status_code == 403
