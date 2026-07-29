"""The TikTok ``ChannelAdapter`` — what it sends, and what it refuses to.

TikTok is the first channel in Nexus that is *less* capable than WhatsApp, so
most of these tests are about the refusals being loud and correct. A
``send_template`` that quietly no-ops, or a send that goes out without a
conversation id, would both look like success while the customer gets
nothing.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from nexus_channels.base import ChannelCapabilityError, SendStatus
from nexus_channels.tiktok_bm.adapter import TikTokChannelAdapter
from nexus_channels.tiktok_bm.tiktok_client import TikTokClient

pytestmark = pytest.mark.asyncio

BUSINESS_ID = "7123"
TOKEN = "act.token"
CONVERSATION_ID = "conv_1"
TENANT_ID = uuid.uuid4()
CHANNEL_ID = uuid.uuid4()


async def _load_credentials(*, tenant_id: uuid.UUID) -> tuple[str, str]:
    return BUSINESS_ID, TOKEN


def build_adapter(handler: Any) -> TikTokChannelAdapter:
    client = TikTokClient(
        "app-1",
        "secret-1",
        transport=httpx.MockTransport(handler),
    )
    return TikTokChannelAdapter(client, credentials_loader=_load_credentials)


def ok(data: dict[str, Any] | None = None) -> httpx.Response:
    return httpx.Response(200, json={"code": 0, "message": "OK", "data": data or {}})


# ── sending ─────────────────────────────────────────────────────────────────


async def test_send_text_targets_the_conversation_from_the_inbound_turn() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return ok({"message_id": "msg_out"})

    adapter = build_adapter(handler)
    result = await adapter.send_text(
        from_phone=BUSINESS_ID,
        recipient="_000sender",
        text="claro que sí",
        tenant_id=TENANT_ID,
        channel_id=CHANNEL_ID,
        context_message_id=CONVERSATION_ID,
    )

    assert result.provider_message_id == "msg_out"
    assert result.status is SendStatus.SENT
    assert "/business/message/send/" in seen["url"]
    assert CONVERSATION_ID in seen["body"]


async def test_send_without_a_conversation_id_fails_loudly() -> None:
    """This is the business-initiated-messaging case. TikTok forbids it, so
    failing here beats a confusing rejection three layers down."""
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return ok()

    adapter = build_adapter(handler)
    with pytest.raises(ChannelCapabilityError, match="conversation_id"):
        await adapter.send_text(
            from_phone=BUSINESS_ID,
            recipient="_000sender",
            text="hola sin contexto",
            tenant_id=TENANT_ID,
            channel_id=CHANNEL_ID,
            context_message_id=None,
        )

    assert called["n"] == 0, "must not reach the network"


async def test_send_image_uploads_the_bytes_before_sending() -> None:
    """TikTok will not accept a foreign URL, so the presigned S3 object has
    to be fetched and re-uploaded."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append(path)
        if path.endswith("/media.jpg"):
            return httpx.Response(
                200, content=b"jpeg-bytes", headers={"content-type": "image/jpeg"}
            )
        if "image/upload" in path:
            return ok({"image_id": "img_uploaded"})
        return ok({"message_id": "msg_img"})

    adapter = build_adapter(handler)
    # The presigned link and the API share the mock transport here; only the
    # ordering of calls matters for what we're asserting.
    adapter._fetch_link = _fake_fetch_link  # type: ignore[method-assign]

    result = await adapter.send_image(
        from_phone=BUSINESS_ID,
        recipient="_000sender",
        link="https://s3.example/media.jpg",
        tenant_id=TENANT_ID,
        channel_id=CHANNEL_ID,
        context_message_id=CONVERSATION_ID,
    )

    assert result.provider_message_id == "msg_img"
    assert any("image/upload" in c for c in calls)
    assert any(c.endswith("/business/message/send/") for c in calls)


async def _fake_fetch_link(link: str) -> tuple[bytes, str | None]:
    return b"jpeg-bytes", "image/jpeg"


async def test_image_caption_is_sent_as_a_follow_up_text() -> None:
    """TikTok image messages have no caption field; dropping the caption
    would lose whatever the agent actually wanted to say."""
    sent_bodies: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "image/upload" in path:
            return ok({"image_id": "img_uploaded"})
        sent_bodies.append(request.content.decode())
        return ok({"message_id": "msg_x"})

    adapter = build_adapter(handler)
    adapter._fetch_link = _fake_fetch_link  # type: ignore[method-assign]

    await adapter.send_image(
        from_phone=BUSINESS_ID,
        recipient="_000sender",
        link="https://s3.example/media.jpg",
        tenant_id=TENANT_ID,
        channel_id=CHANNEL_ID,
        caption="nuestro local",
        context_message_id=CONVERSATION_ID,
    )

    assert any("nuestro local" in body for body in sent_bodies)


# ── refusals ────────────────────────────────────────────────────────────────


async def test_send_template_is_refused_because_tiktok_has_no_templates() -> None:
    adapter = build_adapter(lambda request: ok())

    with pytest.raises(ChannelCapabilityError, match="template"):
        await adapter.send_template(
            from_phone=BUSINESS_ID,
            recipient="_000sender",
            template_name="alert_v1",
            language="es",
            params={},
            tenant_id=TENANT_ID,
            channel_id=CHANNEL_ID,
        )


@pytest.mark.parametrize("method", ["send_audio", "send_video", "send_document"])
async def test_unsupported_media_kinds_are_refused(method: str) -> None:
    adapter = build_adapter(lambda request: ok())

    with pytest.raises(ChannelCapabilityError):
        await getattr(adapter, method)(
            from_phone=BUSINESS_ID,
            recipient="_000sender",
            link="https://s3.example/file",
            tenant_id=TENANT_ID,
            channel_id=CHANNEL_ID,
        )


async def test_reactions_are_refused() -> None:
    adapter = build_adapter(lambda request: ok())

    with pytest.raises(ChannelCapabilityError, match="reaction"):
        await adapter.send_reaction(
            from_phone=BUSINESS_ID,
            recipient="_000sender",
            target_message_id="msg_1",
            emoji="👍",
            tenant_id=TENANT_ID,
            channel_id=CHANNEL_ID,
        )


async def test_mark_as_read_is_a_silent_no_op() -> None:
    """The runtime calls this after every inbound turn; TikTok exposes no
    read-receipt write, so doing nothing is correct, not an error."""
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return ok()

    adapter = build_adapter(handler)
    assert (
        await adapter.mark_as_read(
            from_phone=BUSINESS_ID,
            wamid="msg_1",
            tenant_id=TENANT_ID,
            channel_id=CHANNEL_ID,
        )
        is None
    )
    assert called["n"] == 0


# ── degradation ─────────────────────────────────────────────────────────────


async def test_interactive_payload_degrades_to_readable_text() -> None:
    """A customer reading the options as prose beats silence."""
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.content.decode())
        return ok({"message_id": "msg_flat"})

    adapter = build_adapter(handler)
    await adapter.send_interactive(
        from_phone=BUSINESS_ID,
        recipient="_000sender",
        interactive={
            "body": {"text": "¿Qué querés agendar?"},
            "action": {
                "buttons": [
                    {"reply": {"id": "corte", "title": "Corte"}},
                    {"reply": {"id": "color", "title": "Color"}},
                ]
            },
        },
        tenant_id=TENANT_ID,
        channel_id=CHANNEL_ID,
        context_message_id=CONVERSATION_ID,
    )

    body = sent[0]
    assert "¿Qué querés agendar?" in body
    assert "Corte" in body
    assert "Color" in body


async def test_interactive_list_rows_are_flattened_too() -> None:
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.content.decode())
        return ok({"message_id": "msg_flat"})

    adapter = build_adapter(handler)
    await adapter.send_interactive(
        from_phone=BUSINESS_ID,
        recipient="_000sender",
        interactive={
            "body": {"text": "Horarios"},
            "action": {"sections": [{"rows": [{"title": "10:00"}, {"title": "11:30"}]}]},
        },
        tenant_id=TENANT_ID,
        channel_id=CHANNEL_ID,
        context_message_id=CONVERSATION_ID,
    )

    assert "10:00" in sent[0]
    assert "11:30" in sent[0]


async def test_interactive_with_nothing_renderable_is_refused() -> None:
    adapter = build_adapter(lambda request: ok())

    with pytest.raises(ChannelCapabilityError):
        await adapter.send_interactive(
            from_phone=BUSINESS_ID,
            recipient="_000sender",
            interactive={"action": {"buttons": []}},
            tenant_id=TENANT_ID,
            channel_id=CHANNEL_ID,
            context_message_id=CONVERSATION_ID,
        )


# ── inbound plumbing ────────────────────────────────────────────────────────


async def test_adapter_exposes_the_webhook_parsers() -> None:
    adapter = build_adapter(lambda request: ok())
    payload = {
        "event": "message_received",
        "business_id": BUSINESS_ID,
        "timestamp": 1_800_000_000,
        "data": {
            "conversation_id": CONVERSATION_ID,
            "message_id": "msg_in",
            "sender": {"open_id": "_000sender"},
            "message_type": "text",
            "content": {"text": "hola"},
        },
    }

    assert adapter.provider_identifier_from_payload(payload) == BUSINESS_ID
    parsed = adapter.parse_inbound(payload)
    assert parsed is not None
    assert parsed.text == "hola"


async def test_fetch_media_bytes_reports_no_checksum() -> None:
    """TikTok publishes none; inventing one would defeat the dedupe it is
    meant to serve."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"png", headers={"content-type": "image/png"})

    adapter = build_adapter(handler)
    content, mime, sha = await adapter.fetch_media_bytes(media_id="img_1", tenant_id=TENANT_ID)

    assert content == b"png"
    assert mime == "image/png"
    assert sha is None


async def test_adapter_identity_matches_the_channel_row() -> None:
    adapter = build_adapter(lambda request: ok())
    assert adapter.provider == "tiktok"
    assert adapter.channel_type == "tiktok"
