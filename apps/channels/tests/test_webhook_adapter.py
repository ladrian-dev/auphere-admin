"""Tests for the YCloud inbound webhook normaliser."""

from __future__ import annotations

from typing import Any

from nexus_channels.base import InboundMessageKind
from nexus_channels.whatsapp_ycloud.webhook_adapter import (
    extract_business_phone,
    parse_inbound,
)


def _envelope(
    msg: dict[str, Any], event_type: str = "whatsapp.inbound_message.received"
) -> dict[str, Any]:
    return {
        "id": "evt_1",
        "type": event_type,
        "createTime": "2026-05-09T12:00:00Z",
        "whatsappInboundMessage": msg,
    }


def test_extract_business_phone():
    payload = _envelope({"to": "+56933334444", "from": "+56911112222"})
    assert extract_business_phone(payload) == "+56933334444"


def test_extract_business_phone_missing_returns_none():
    assert extract_business_phone({}) is None
    assert extract_business_phone({"whatsappInboundMessage": {}}) is None


def test_parse_text_message():
    payload = _envelope(
        {
            "to": "+56933334444",
            "from": "+56911112222",
            "wamid": "wamid.HBgN",
            "type": "text",
            "text": {"body": "hola"},
            "customerProfile": {"name": "Juan"},
        }
    )
    msg = parse_inbound(payload)
    assert msg is not None
    assert msg.kind is InboundMessageKind.TEXT
    assert msg.text == "hola"
    assert msg.sender_identifier == "+56911112222"
    assert msg.provider_identifier == "+56933334444"
    assert msg.sender_name == "Juan"
    assert msg.provider_message_id == "wamid.HBgN"
    assert msg.raw_event_type == "text"


def test_parse_button_reply_snake_case():
    payload = _envelope(
        {
            "to": "+5693",
            "from": "+5691",
            "wamid": "w1",
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": "btn_yes", "title": "Sí"},
            },
        }
    )
    msg = parse_inbound(payload)
    assert msg is not None
    assert msg.kind is InboundMessageKind.INTERACTIVE
    assert msg.interactive is not None
    assert msg.interactive.kind == "button"
    assert msg.interactive.payload_id == "btn_yes"
    assert msg.interactive.title == "Sí"
    assert msg.text is None


def test_parse_button_reply_camel_case():
    """YCloud has historically alternated snake/camel case for interactive."""
    payload = _envelope(
        {
            "to": "+5693",
            "from": "+5691",
            "wamid": "w1",
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "buttonReply": {"id": "btn_no", "title": "No"},
            },
        }
    )
    msg = parse_inbound(payload)
    assert msg is not None
    assert msg.interactive is not None
    assert msg.interactive.payload_id == "btn_no"


def test_parse_list_reply():
    payload = _envelope(
        {
            "to": "+5693",
            "from": "+5691",
            "wamid": "w1",
            "type": "interactive",
            "interactive": {
                "type": "list_reply",
                "list_reply": {
                    "id": "slot_15",
                    "title": "15:00",
                    "description": "Luis",
                },
            },
        }
    )
    msg = parse_inbound(payload)
    assert msg is not None
    assert msg.interactive is not None
    assert msg.interactive.kind == "list"
    assert msg.interactive.payload_id == "slot_15"
    assert msg.interactive.description == "Luis"


def test_parse_audio_message_promoted_from_unsupported():
    """Block N promoted media to first-class kinds. Audio now carries a
    ``MediaReference`` and the kind is AUDIO (was UNSUPPORTED in Block F)."""
    payload = _envelope(
        {
            "to": "+5693",
            "from": "+5691",
            "wamid": "w1",
            "type": "audio",
            "audio": {
                "id": "media_1",
                "mime_type": "audio/ogg; codecs=opus",
                "sha256": "abc",
                "voice": True,
            },
        }
    )
    msg = parse_inbound(payload)
    assert msg is not None
    assert msg.kind is InboundMessageKind.AUDIO
    assert msg.media is not None
    assert msg.media.provider_media_id == "media_1"
    assert msg.media.mime_type and msg.media.mime_type.startswith("audio/ogg")
    assert msg.media.voice is True


def test_parse_image_with_caption_surfaces_text():
    payload = _envelope(
        {
            "to": "+5693",
            "from": "+5691",
            "wamid": "w1",
            "type": "image",
            "image": {
                "id": "img_1",
                "mime_type": "image/jpeg",
                "caption": "este corte por favor",
            },
        }
    )
    msg = parse_inbound(payload)
    assert msg is not None
    assert msg.kind is InboundMessageKind.IMAGE
    assert msg.media is not None
    assert msg.media.provider_media_id == "img_1"
    # Caption is also surfaced in ``text`` so the classifier can route
    # even if the multimodal pipeline can't process the image.
    assert msg.text == "este corte por favor"


def test_parse_reaction():
    payload = _envelope(
        {
            "to": "+5693",
            "from": "+5691",
            "wamid": "w1",
            "type": "reaction",
            "reaction": {"message_id": "wamid.target", "emoji": "👍"},
        }
    )
    msg = parse_inbound(payload)
    assert msg is not None
    assert msg.kind is InboundMessageKind.REACTION
    assert msg.reaction is not None
    assert msg.reaction.target_message_id == "wamid.target"
    assert msg.reaction.emoji == "👍"


def test_parse_reaction_removal_empty_emoji():
    payload = _envelope(
        {
            "to": "+5693",
            "from": "+5691",
            "wamid": "w1",
            "type": "reaction",
            "reaction": {"message_id": "wamid.target", "emoji": ""},
        }
    )
    msg = parse_inbound(payload)
    assert msg is not None
    assert msg.reaction is not None
    assert msg.reaction.emoji == ""


def test_parse_location():
    payload = _envelope(
        {
            "to": "+5693",
            "from": "+5691",
            "wamid": "w1",
            "type": "location",
            "location": {
                "latitude": -33.45,
                "longitude": -70.66,
                "name": "Cultor",
                "address": "Av. Providencia 123",
            },
        }
    )
    msg = parse_inbound(payload)
    assert msg is not None
    assert msg.kind is InboundMessageKind.LOCATION
    assert msg.location is not None
    assert msg.location.latitude == -33.45
    assert msg.location.address == "Av. Providencia 123"


def test_parse_quoted_reply_context():
    payload = _envelope(
        {
            "to": "+5693",
            "from": "+5691",
            "wamid": "w1",
            "type": "text",
            "text": {"body": "sí ese mismo"},
            "context": {"id": "wamid.prev", "from": "+5693"},
        }
    )
    msg = parse_inbound(payload)
    assert msg is not None
    assert msg.context_message_id == "wamid.prev"


def test_status_callback_returns_none():
    """Non-message events (delivery acks, status callbacks) are dropped."""
    payload = _envelope({}, event_type="whatsapp.message.updated")
    assert parse_inbound(payload) is None


def test_missing_required_fields_returns_none():
    payload = _envelope({"to": "+5693"})  # no from / wamid
    assert parse_inbound(payload) is None


def test_default_received_at_when_no_create_time():
    msg = parse_inbound(
        {
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "to": "+5693",
                "from": "+5691",
                "wamid": "w1",
                "type": "text",
                "text": {"body": "hi"},
            },
        }
    )
    assert msg is not None
    assert msg.received_at is not None
