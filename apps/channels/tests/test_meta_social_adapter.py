"""Spec 049 — Instagram / Messenger outbound and message splitting."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest

from nexus_channels.base import ChannelCapabilityError
from nexus_channels.meta_social.adapter import MetaSocialChannelAdapter, SendContext
from nexus_channels.meta_social.graph import MetaSocialClient
from nexus_channels.meta_social.text import split_message
from nexus_channels.meta_social.webhook_adapter import PROVIDER_INSTAGRAM, PROVIDER_MESSENGER

TENANT = uuid.uuid4()
CHANNEL = uuid.uuid4()


# ── splitting ───────────────────────────────────────────────────────────────


def test_short_text_is_one_message() -> None:
    assert split_message("hola", max_bytes=1000) == ["hola"]


def test_split_respects_bytes_and_words() -> None:
    text = ("ñandú " * 400).strip()  # 2 bytes per ñ/ú → well over 1000 bytes
    chunks = split_message(text, max_bytes=1000)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.encode()) <= 1000
        assert not chunk.startswith(" ") and not chunk.endswith(" ")
        assert all(word == "ñandú" for word in chunk.split())
    assert " ".join(chunks) == text


def test_split_prefers_paragraphs() -> None:
    first = "a" * 900
    text = f"{first}\n\n{'b' * 500}"
    assert split_message(text, max_bytes=1000) == [first, "b" * 500]


def test_split_by_characters_for_messenger() -> None:
    chunks = split_message("x " * 1500, max_chars=2000)
    assert all(len(c) <= 2000 for c in chunks)
    assert len(chunks) == 2


# ── adapter ─────────────────────────────────────────────────────────────────


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any], Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, dict(request.url.params), body))
        if request.url.path.endswith("/replies"):
            return httpx.Response(200, json={"id": "R_1"})
        return httpx.Response(
            200, json={"recipient_id": "U", "message_id": f"mid.{len(self.calls)}"}
        )


def _adapter(
    provider: str, rec: Recorder, *, public_reply: str | None = None
) -> MetaSocialChannelAdapter:
    client = MetaSocialClient("secret", transport=httpx.MockTransport(rec.handler))

    async def loader(*, tenant_id: uuid.UUID, channel_id: uuid.UUID) -> SendContext:
        return SendContext(account_id="ACC", token="TOKEN", public_comment_reply=public_reply)

    return MetaSocialChannelAdapter(client, provider=provider, context_loader=loader)


async def test_send_text_is_a_response_from_the_account() -> None:
    rec = Recorder()
    result = await _adapter(PROVIDER_INSTAGRAM, rec).send_text(
        from_phone="ACC", recipient="IGSID", text="hello", tenant_id=TENANT, channel_id=CHANNEL
    )
    method, path, params, body = rec.calls[0]
    assert method == "POST" and path == "/v26.0/ACC/messages"
    assert body == {
        "recipient": {"id": "IGSID"},
        "message": {"text": "hello"},
        "messaging_type": "RESPONSE",
    }
    assert "appsecret_proof" in params
    assert "access_token" not in params  # header only, never the URL
    assert result.provider_message_id == "mid.1"


async def test_human_agent_tag_only_when_asked() -> None:
    rec = Recorder()
    await _adapter(PROVIDER_MESSENGER, rec).send_text(
        from_phone="ACC",
        recipient="PSID",
        text="hi",
        tenant_id=TENANT,
        channel_id=CHANNEL,
        human_agent=True,
    )
    body = rec.calls[0][3]
    assert body["messaging_type"] == "MESSAGE_TAG"
    assert body["tag"] == "HUMAN_AGENT"


async def test_long_instagram_reply_is_split() -> None:
    rec = Recorder()
    await _adapter(PROVIDER_INSTAGRAM, rec).send_text(
        from_phone="ACC",
        recipient="IGSID",
        text="palabra " * 300,
        tenant_id=TENANT,
        channel_id=CHANNEL,
    )
    assert len(rec.calls) == 3
    assert all(len(c[3]["message"]["text"].encode()) <= 1000 for c in rec.calls)


async def test_private_reply_goes_to_the_comment_once_then_public_line() -> None:
    rec = Recorder()
    await _adapter(PROVIDER_INSTAGRAM, rec, public_reply="We sent you a DM").send_text(
        from_phone="ACC",
        recipient="IGSID",
        text="palabra " * 300,
        tenant_id=TENANT,
        channel_id=CHANNEL,
        context_message_id="comment:C_1",
    )
    assert len(rec.calls) == 2
    _, path, _, body = rec.calls[0]
    assert path == "/v26.0/ACC/messages"
    assert body["recipient"] == {"comment_id": "C_1"}
    assert len(body["message"]["text"].encode()) <= 1000
    _, path, params, _ = rec.calls[1]
    assert path == "/v26.0/C_1/replies" and params["message"] == "We sent you a DM"


async def test_interactive_becomes_quick_replies() -> None:
    rec = Recorder()
    block = {
        "type": "button",
        "body": {"text": "Pick one"},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": "a", "title": "Morning appointment slot"}}
            ]
        },
    }
    await _adapter(PROVIDER_INSTAGRAM, rec).send_interactive(
        from_phone="ACC", recipient="IGSID", interactive=block, tenant_id=TENANT, channel_id=CHANNEL
    )
    message = rec.calls[0][3]["message"]
    assert message["text"] == "Pick one"
    assert message["quick_replies"] == [
        {"content_type": "text", "title": "Morning appointment", "payload": "a"}
    ]


async def test_in_a_comment_turn_buttons_and_media_become_the_one_private_reply() -> None:
    """QA 2026-10-30 (INC-21): quick replies and attachments ignored the
    comment context and went as a DM by ``recipient.id``, which Meta refuses."""
    rec = Recorder()
    adapter = _adapter(PROVIDER_INSTAGRAM, rec)
    block = {
        "type": "button",
        "body": {"text": "Pick one"},
        "action": {"buttons": [{"type": "reply", "reply": {"id": "a", "title": "Morning"}}]},
    }
    await adapter.send_interactive(
        from_phone="ACC",
        recipient="IGSID",
        interactive=block,
        tenant_id=TENANT,
        channel_id=CHANNEL,
        context_message_id="comment:C_9",
    )
    body = rec.calls[-1][3]
    assert body["recipient"] == {"comment_id": "C_9"}
    assert body["message"] == {"text": "Pick one\n• Morning"}

    await adapter.send_image(
        from_phone="ACC",
        recipient="IGSID",
        link="https://s3/x.jpg",
        caption="Our menu",
        tenant_id=TENANT,
        channel_id=CHANNEL,
        context_message_id="comment:C_10",
    )
    body = rec.calls[-1][3]
    assert body["recipient"] == {"comment_id": "C_10"}
    assert body["message"] == {"text": "Our menu"}

    with pytest.raises(ChannelCapabilityError):
        await adapter.send_audio(
            from_phone="ACC",
            recipient="IGSID",
            link="https://s3/x.ogg",
            tenant_id=TENANT,
            channel_id=CHANNEL,
            context_message_id="comment:C_11",
        )


async def test_templates_do_not_exist_here() -> None:
    with pytest.raises(ChannelCapabilityError):
        await _adapter(PROVIDER_INSTAGRAM, Recorder()).send_template()


async def test_media_by_url_with_caption_after() -> None:
    rec = Recorder()
    await _adapter(PROVIDER_MESSENGER, rec).send_image(
        from_phone="ACC",
        recipient="P",
        link="https://s3/x.jpg",
        caption="Menu",
        tenant_id=TENANT,
        channel_id=CHANNEL,
    )
    assert rec.calls[0][3]["message"]["attachment"]["type"] == "image"
    assert rec.calls[1][3]["message"] == {"text": "Menu"}


async def test_attachment_download_refuses_foreign_hosts() -> None:
    adapter = _adapter(PROVIDER_INSTAGRAM, Recorder())
    with pytest.raises(ValueError):
        await adapter.fetch_media_bytes(media_id="url:https://evil.example.com/x", tenant_id=TENANT)
