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


def test_unsupported_media_kind_marked_unsupported():
    payload = _envelope(
        {
            "to": "+5693",
            "from": "+5691",
            "wamid": "w1",
            "type": "audio",
            "audio": {"id": "media_1", "link": "https://..."},
        }
    )
    msg = parse_inbound(payload)
    assert msg is not None
    assert msg.kind is InboundMessageKind.UNSUPPORTED
    assert msg.text is None
    assert msg.interactive is None


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
