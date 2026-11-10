"""La publicación de un comentario en la Bandeja (owner, 2026-11-02)."""

from __future__ import annotations

import uuid

import httpx
import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Channel, ChannelStatus, ChannelType, Conversation, Message
from tests.conftest import make_inbox

pytestmark = pytest.mark.asyncio

BASE = "/console/lite/inbox/conversations"


async def _comment_world(db_session, world, *, kind: ChannelType, ref: str):
    from nexus_channels.meta_social.credentials import SocialCredentials

    inbox = await make_inbox(
        db_session, partner_id=world["partner_id"], tenant_id=world["tenant_id"]
    )
    conv_id = inbox["conversations"][0]
    async with tenant_scoped_session(db_session, world["tenant_id"]):
        channel = Channel(
            tenant_id=world["tenant_id"],
            type=kind,
            provider="meta_instagram" if kind == ChannelType.INSTAGRAM else "meta_messenger",
            provider_identifier="PAGE1",
            status=ChannelStatus.ACTIVE,
            config={},
            config_encrypted=SocialCredentials(token="SU", page_token="PAGE_TOKEN").to_payload(),
        )
        db_session.add(channel)
        await db_session.flush()
        await db_session.execute(
            sa.update(Conversation).where(Conversation.id == conv_id).values(channel_id=channel.id)
        )
        message_id = await db_session.scalar(
            sa.select(Message.id)
            .where(Message.conversation_id == conv_id, Message.direction == "inbound")
            .limit(1)
        )
        await db_session.execute(
            sa.update(Message).where(Message.id == message_id).values(provider_message_id=ref)
        )
    await db_session.commit()
    return inbox, conv_id, message_id


def _graph(monkeypatch, handler) -> list[str]:
    from nexus_channels.meta_social import MetaSocialClient

    from nexus_api.services import meta_social_service

    seen: list[str] = []

    def spy(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.url.path}?{request.url.params.get('fields')}")
        return handler(request)

    monkeypatch.setattr(
        meta_social_service, "_client", MetaSocialClient("s", transport=httpx.MockTransport(spy))
    )
    return seen


async def test_instagram_reads_the_media_of_the_comment(
    client, db_session, console_world, monkeypatch
) -> None:
    inbox, conv, msg = await _comment_world(
        db_session, console_world["a"], kind=ChannelType.INSTAGRAM, ref="comment:C1"
    )
    seen = _graph(
        monkeypatch,
        lambda _r: httpx.Response(
            200,
            json={
                "media": {
                    "caption": "Three tasks",
                    "media_url": "https://x.cdninstagram.com/a.jpg",
                    "permalink": "https://instagram.com/p/1",
                    "media_type": "IMAGE",
                }
            },
        ),
    )
    r = await client.get(f"{BASE}/{conv}/messages/{msg}/post", headers=inbox["headers"]())
    assert r.status_code == 200, r.text
    assert r.json() == {
        "text": "Three tasks",
        "image_url": "https://x.cdninstagram.com/a.jpg",
        "permalink": "https://instagram.com/p/1",
    }
    assert "media{" in seen[0]
    # La segunda lectura sale de la caché.
    again = await client.get(f"{BASE}/{conv}/messages/{msg}/post", headers=inbox["headers"]())
    assert again.json()["text"] == "Three tasks"
    assert len(seen) == 1


async def test_a_page_comment_reads_the_post_and_falls_back_to_the_object(
    client, db_session, console_world, monkeypatch
) -> None:
    inbox, conv, msg = await _comment_world(
        db_session, console_world["a"], kind=ChannelType.MESSENGER, ref="comment:OBJ_C2"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/PAGE1_OBJ"):
            return httpx.Response(400, json={"error": {"code": 100, "message": "no"}})
        return httpx.Response(
            200,
            json={
                "description": "A reel",
                "picture": "https://x.fbcdn.net/r.jpg",
                "permalink_url": "/reel/1",
            },
        )

    seen = _graph(monkeypatch, handler)
    r = await client.get(f"{BASE}/{conv}/messages/{msg}/post", headers=inbox["headers"]())
    assert r.json() == {
        "text": "A reel",
        "image_url": "https://x.fbcdn.net/r.jpg",
        "permalink": "/reel/1",
    }
    assert seen[0].split("?")[0].endswith("/PAGE1_OBJ")
    assert seen[1].split("?")[0].endswith("/OBJ")


async def test_when_meta_gives_nothing_the_answer_is_null(
    client, db_session, console_world, monkeypatch
) -> None:
    inbox, conv, msg = await _comment_world(
        db_session, console_world["a"], kind=ChannelType.INSTAGRAM, ref="comment:C3"
    )
    _graph(
        monkeypatch, lambda _r: httpx.Response(400, json={"error": {"code": 100, "message": "no"}})
    )
    r = await client.get(f"{BASE}/{conv}/messages/{msg}/post", headers=inbox["headers"]())
    assert r.status_code == 200
    assert r.json() is None


async def test_a_message_that_is_not_a_comment_or_not_of_this_conversation_has_no_post(
    client, db_session, console_world, monkeypatch
) -> None:
    inbox, conv, msg = await _comment_world(
        db_session, console_world["a"], kind=ChannelType.INSTAGRAM, ref="mid.plain"
    )
    seen = _graph(monkeypatch, lambda _r: httpx.Response(200, json={}))
    assert (
        await client.get(f"{BASE}/{conv}/messages/{msg}/post", headers=inbox["headers"]())
    ).json() is None
    other = inbox["conversations"][1]
    assert (
        await client.get(f"{BASE}/{other}/messages/{msg}/post", headers=inbox["headers"]())
    ).json() is None
    assert (
        await client.get(f"{BASE}/{conv}/messages/{uuid.uuid4()}/post", headers=inbox["headers"]())
    ).json() is None
    assert seen == []


async def test_the_thread_says_which_messages_are_comments_and_which_were_unsent(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    inbox, conv, msg = await _comment_world(
        db_session, w, kind=ChannelType.INSTAGRAM, ref="comment:C4"
    )
    async with tenant_scoped_session(db_session, w["tenant_id"]):
        await db_session.execute(
            sa.update(Message)
            .where(Message.id == msg)
            .values(content="", interactive_payload={"unsent": True})
        )
    await db_session.commit()
    items = (await client.get(f"{BASE}/{conv}/messages", headers=inbox["headers"]())).json()[
        "items"
    ]
    item = next(i for i in items if i["id"] == str(msg))
    assert item["comment"] is True
    assert item["unsent"] is True
    assert item["text"] is None
