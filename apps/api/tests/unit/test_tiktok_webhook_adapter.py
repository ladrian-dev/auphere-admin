"""Parsing TikTok Business Messaging webhook payloads into ``InboundMessage``.

The payloads here are built from the documented envelope shape. Two
behaviours get the most attention because they are the ones that would fail
quietly in production:

- ``conversation_id`` must survive onto the parsed message, because it is the
  only handle the outbound path has for replying.
- unknown message types must become ``UNSUPPORTED``, never ``None`` — the
  adapter Protocol forbids silent drops, and an agent that sees "something
  arrived I can't read" degrades better than one that sees nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from nexus_channels.base import InboundMessageKind
from nexus_channels.tiktok_bm import webhook_adapter as tt

BUSINESS_ID = "7123456789012345678"
SENDER_OPEN_ID = "_000AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCDEF"
CONVERSATION_ID = "conv_abc123"
TS = 1_800_000_000


def envelope(*, message_type: str = "text", content: dict[str, Any] | None = None) -> dict:
    return {
        "event": "message_received",
        "business_id": BUSINESS_ID,
        "timestamp": TS,
        "data": {
            "conversation_id": CONVERSATION_ID,
            "message_id": "msg_123",
            "sender": {"open_id": SENDER_OPEN_ID, "nickname": "Ana"},
            "message_type": message_type,
            "content": content if content is not None else {"text": "hola"},
        },
    }


def test_parses_a_text_message() -> None:
    msg = tt.parse_inbound(envelope())

    assert msg is not None
    assert msg.kind is InboundMessageKind.TEXT
    assert msg.provider == "tiktok"
    assert msg.provider_message_id == "msg_123"
    assert msg.provider_identifier == BUSINESS_ID
    assert msg.sender_identifier == SENDER_OPEN_ID
    assert msg.sender_name == "Ana"
    assert msg.text == "hola"
    assert msg.received_at == datetime.fromtimestamp(TS, tz=UTC)


def test_carries_the_conversation_id_so_a_reply_is_possible() -> None:
    """Without this the agent can compose a perfect answer and have nowhere
    to send it — TikTok has no send-to-user call."""
    msg = tt.parse_inbound(envelope())

    assert msg is not None
    assert msg.context_message_id == CONVERSATION_ID


def test_long_tiktok_identifiers_are_accepted() -> None:
    """``open_id`` blows past the 40-char bound the canonical shape used to
    carry for E.164 phone numbers."""
    assert len(SENDER_OPEN_ID) > 40
    assert tt.parse_inbound(envelope()) is not None


def test_parses_an_image_message_into_a_media_reference() -> None:
    msg = tt.parse_inbound(
        envelope(
            message_type="image",
            content={"image_id": "img_789", "mime_type": "image/png", "caption": "mira"},
        )
    )

    assert msg is not None
    assert msg.kind is InboundMessageKind.IMAGE
    assert msg.media is not None
    assert msg.media.provider_media_id == "img_789"
    assert msg.media.mime_type == "image/png"
    assert msg.text == "mira"


def test_image_without_a_fetchable_id_degrades_to_unsupported() -> None:
    """An image we cannot download is not an image; saying so beats emitting
    a media message the pipeline will fail to resolve."""
    msg = tt.parse_inbound(envelope(message_type="image", content={"caption": "mira"}))

    assert msg is not None
    assert msg.kind is InboundMessageKind.UNSUPPORTED
    assert msg.media is None


def test_shared_post_degrades_to_text_with_a_usable_reference() -> None:
    msg = tt.parse_inbound(
        envelope(message_type="post", content={"share_url": "https://tiktok.com/@x/video/1"})
    )

    assert msg is not None
    assert msg.kind is InboundMessageKind.TEXT
    assert msg.text is not None
    assert "https://tiktok.com/@x/video/1" in msg.text


def test_unknown_message_type_becomes_unsupported_not_none() -> None:
    msg = tt.parse_inbound(envelope(message_type="sticker_pack_v3", content={}))

    assert msg is not None
    assert msg.kind is InboundMessageKind.UNSUPPORTED
    assert msg.raw_event_type == "sticker_pack_v3"


def test_read_receipts_are_not_inbound_messages() -> None:
    payload = {
        "event": "message_read",
        "business_id": BUSINESS_ID,
        "timestamp": TS,
        "data": {"conversation_id": CONVERSATION_ID, "message_id": "msg_123"},
    }

    assert tt.parse_inbound(payload) is None

    event = tt.parse_conversation_event(payload)
    assert event is not None
    assert event.event == "message_read"
    assert event.conversation_id == CONVERSATION_ID
    assert tt.is_known_event(payload) is True


def test_message_without_a_stable_id_is_dropped() -> None:
    """TikTok redrives aggressively; without an id we cannot dedupe, and
    answering the same customer turn twice is worse than dropping it."""
    payload = envelope()
    del payload["data"]["message_id"]

    assert tt.parse_inbound(payload) is None


def test_message_without_a_sender_is_dropped() -> None:
    payload = envelope()
    del payload["data"]["sender"]

    assert tt.parse_inbound(payload) is None


def test_extract_business_id_reads_the_envelope_without_full_parsing() -> None:
    assert tt.extract_business_id(envelope()) == BUSINESS_ID
    assert tt.extract_business_id({"business_id": 7123}) == "7123"
    assert tt.extract_business_id({"data": {"business_id": "999"}}) == "999"
    assert tt.extract_business_id({"event": "message_received"}) is None


def test_unattributable_payload_yields_nothing() -> None:
    payload = envelope()
    del payload["business_id"]

    assert tt.parse_inbound(payload) is None


def test_millisecond_timestamps_are_not_read_as_the_year_58000() -> None:
    payload = envelope()
    payload["timestamp"] = TS * 1000

    msg = tt.parse_inbound(payload)
    assert msg is not None
    assert msg.received_at == datetime.fromtimestamp(TS, tz=UTC)


@pytest.mark.parametrize("field", ["event_type", "eventType"])
def test_accepts_event_name_key_drift(field: str) -> None:
    payload = envelope()
    payload[field] = payload.pop("event")

    assert tt.parse_inbound(payload) is not None


def test_iterates_a_batched_delivery() -> None:
    payload = envelope()
    payload["data"]["messages"] = [
        {
            "message_id": "msg_1",
            "sender": {"open_id": SENDER_OPEN_ID},
            "message_type": "text",
            "content": {"text": "uno"},
        },
        {
            "message_id": "msg_2",
            "sender": {"open_id": SENDER_OPEN_ID},
            "message_type": "text",
            "content": {"text": "dos"},
        },
    ]

    parsed = list(tt.iter_inbound_messages(payload))
    assert [m.text for m in parsed] == ["uno", "dos"]
    assert all(m.context_message_id == CONVERSATION_ID for m in parsed)
