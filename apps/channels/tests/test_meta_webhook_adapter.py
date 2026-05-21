"""Tests for the Meta WhatsApp webhook payload parser."""

from __future__ import annotations

from nexus_channels.base import InboundMessageKind
from nexus_channels.whatsapp_meta.webhook_adapter import (
    extract_business_phone,
    extract_phone_number_id,
    extract_waba_id,
    parse_inbound,
    parse_status_callback,
    parse_template_status,
)


def _envelope(value: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WABA_1", "changes": [{"field": "messages", "value": value}]}],
    }


def _text_payload(text: str = "hola", *, waba: str = "WABA_1") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": waba,
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "56933334444",
                                "phone_number_id": "PN_1",
                            },
                            "contacts": [
                                {"profile": {"name": "Juan"}, "wa_id": "56911112222"}
                            ],
                            "messages": [
                                {
                                    "from": "56911112222",
                                    "id": "wamid.ABC",
                                    "timestamp": "1716220800",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def test_extract_business_phone_normalises_to_e164() -> None:
    payload = _text_payload()
    assert extract_business_phone(payload) == "+56933334444"


def test_extract_business_phone_returns_none_for_non_whatsapp() -> None:
    assert extract_business_phone({"object": "instagram", "entry": []}) is None


def test_extract_waba_id_and_phone_number_id() -> None:
    payload = _text_payload()
    assert extract_waba_id(payload) == "WABA_1"
    assert extract_phone_number_id(payload) == "PN_1"


def test_parse_inbound_text() -> None:
    payload = _text_payload("hola mundo")
    msg = parse_inbound(payload)
    assert msg is not None
    assert msg.kind == InboundMessageKind.TEXT
    assert msg.text == "hola mundo"
    assert msg.provider == "meta"
    assert msg.provider_message_id == "wamid.ABC"
    assert msg.provider_identifier == "+56933334444"
    assert msg.sender_identifier == "56911112222"
    assert msg.sender_name == "Juan"


def test_parse_inbound_interactive_button() -> None:
    payload = _envelope(
        {
            "messaging_product": "whatsapp",
            "metadata": {
                "display_phone_number": "56933334444",
                "phone_number_id": "PN_1",
            },
            "messages": [
                {
                    "from": "56911",
                    "id": "wamid.X",
                    "timestamp": "1716220800",
                    "type": "interactive",
                    "interactive": {
                        "type": "button_reply",
                        "button_reply": {"id": "yes", "title": "Sí"},
                    },
                }
            ],
        }
    )
    msg = parse_inbound(payload)
    assert msg is not None
    assert msg.kind == InboundMessageKind.INTERACTIVE
    assert msg.interactive is not None
    assert msg.interactive.kind == "button"
    assert msg.interactive.payload_id == "yes"
    assert msg.interactive.title == "Sí"


def test_parse_inbound_image_media() -> None:
    payload = _envelope(
        {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "56933334444"},
            "messages": [
                {
                    "from": "56911",
                    "id": "wamid.M",
                    "timestamp": "1716220800",
                    "type": "image",
                    "image": {
                        "id": "media-1",
                        "mime_type": "image/jpeg",
                        "sha256": "abc123",
                        "caption": "mira",
                    },
                }
            ],
        }
    )
    msg = parse_inbound(payload)
    assert msg is not None
    assert msg.kind == InboundMessageKind.IMAGE
    assert msg.media is not None
    assert msg.media.provider_media_id == "media-1"
    assert msg.media.mime_type == "image/jpeg"
    assert msg.media.caption == "mira"


def test_parse_inbound_reaction() -> None:
    payload = _envelope(
        {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "56933"},
            "messages": [
                {
                    "from": "56911",
                    "id": "wamid.R",
                    "timestamp": "1716220800",
                    "type": "reaction",
                    "reaction": {"message_id": "wamid.PREV", "emoji": "👍"},
                }
            ],
        }
    )
    msg = parse_inbound(payload)
    assert msg is not None
    assert msg.kind == InboundMessageKind.REACTION
    assert msg.reaction is not None
    assert msg.reaction.target_message_id == "wamid.PREV"
    assert msg.reaction.emoji == "👍"


def test_parse_inbound_unknown_type_becomes_unsupported() -> None:
    payload = _envelope(
        {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "56933"},
            "messages": [
                {
                    "from": "56911",
                    "id": "wamid.U",
                    "timestamp": "1716220800",
                    "type": "future_type_meta_invents",
                }
            ],
        }
    )
    msg = parse_inbound(payload)
    assert msg is not None
    assert msg.kind == InboundMessageKind.UNSUPPORTED


def test_parse_inbound_ignores_non_whatsapp_object() -> None:
    assert parse_inbound({"object": "instagram", "entry": []}) is None


def test_parse_inbound_returns_none_when_no_messages() -> None:
    payload = _envelope({"messaging_product": "whatsapp", "metadata": {}})
    assert parse_inbound(payload) is None


def test_parse_status_callback_delivered() -> None:
    payload = _envelope(
        {
            "messaging_product": "whatsapp",
            "metadata": {
                "display_phone_number": "56933",
                "phone_number_id": "PN_1",
            },
            "statuses": [
                {
                    "id": "wamid.OUT",
                    "recipient_id": "56911",
                    "status": "delivered",
                    "timestamp": "1716220900",
                    "conversation": {"id": "conv-1"},
                    "pricing": {"category": "MARKETING", "pricing_model": "CBP"},
                }
            ],
        }
    )
    update = parse_status_callback(payload)
    assert update is not None
    assert update.wamid == "wamid.OUT"
    assert update.status == "delivered"
    assert update.recipient == "56911"
    assert update.conversation_id == "conv-1"
    assert update.pricing_category == "MARKETING"
    assert update.waba_id == "WABA_1"
    assert update.phone_number_id == "PN_1"


def test_parse_status_callback_failed_carries_error() -> None:
    payload = _envelope(
        {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "56933", "phone_number_id": "PN_1"},
            "statuses": [
                {
                    "id": "wamid.OUT",
                    "recipient_id": "56911",
                    "status": "failed",
                    "timestamp": "1716220900",
                    "errors": [
                        {
                            "code": 131047,
                            "title": "Re-engagement message",
                            "message": "outside the 24h window",
                        }
                    ],
                }
            ],
        }
    )
    update = parse_status_callback(payload)
    assert update is not None
    assert update.status == "failed"
    assert update.error_code == 131047
    assert update.error_title == "Re-engagement message"


def test_parse_template_status_event() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_1",
                "changes": [
                    {
                        "field": "message_template_status_update",
                        "value": {
                            "message_template_id": "tpl-1",
                            "message_template_name": "reminder_24h",
                            "message_template_language": "es_CL",
                            "event": "APPROVED",
                            "reason": None,
                        },
                    }
                ],
            }
        ],
    }
    update = parse_template_status(payload)
    assert update is not None
    assert update.template_name == "reminder_24h"
    assert update.language == "es_CL"
    assert update.new_status == "APPROVED"
    assert update.waba_id == "WABA_1"


# ── Coexistence-only events ────────────────────────────────────────────────


from nexus_channels.whatsapp_meta.webhook_adapter import (  # noqa: E402
    parse_app_state_sync,
    parse_history_sync,
    parse_message_echo,
)


def test_parse_message_echo_extracts_outbound_from_app():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_COEX",
                "changes": [
                    {
                        "field": "smb_message_echoes",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "56999998888",
                                "phone_number_id": "PN_COEX",
                            },
                            "messages": [
                                {
                                    "id": "wamid.echo-1",
                                    "from": "56999998888",
                                    "to": "56911112222",
                                    "timestamp": "1716300000",
                                    "type": "text",
                                    "text": {"body": "respondido desde el movil"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    echo = parse_message_echo(payload)
    assert echo is not None
    assert echo.waba_id == "WABA_COEX"
    assert echo.phone_number_id == "PN_COEX"
    assert echo.provider_message_id == "wamid.echo-1"
    assert echo.sender_identifier == "56999998888"
    assert echo.recipient_identifier == "56911112222"
    assert echo.text == "respondido desde el movil"


def test_parse_message_echo_returns_none_when_field_missing():
    # Plain inbound payload — wrong field, parser must not synthesize an echo.
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "W", "changes": [{"field": "messages", "value": {}}]}],
    }
    assert parse_message_echo(payload) is None


def test_parse_app_state_sync_counts_contacts_and_has_more():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_COEX",
                "changes": [
                    {
                        "field": "smb_app_state_sync",
                        "value": {
                            "metadata": {"phone_number_id": "PN_COEX"},
                            "contacts": [
                                {"wa_id": "56911110001", "name": "A"},
                                {"wa_id": "56911110002", "name": "B"},
                                {"wa_id": "56911110003", "name": "C"},
                            ],
                            "has_more": True,
                        },
                    }
                ],
            }
        ],
    }
    sync = parse_app_state_sync(payload)
    assert sync is not None
    assert sync.contact_count == 3
    assert sync.has_more is True
    assert sync.phone_number_id == "PN_COEX"


def test_parse_history_sync_counts_messages_across_threads():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_COEX",
                "changes": [
                    {
                        "field": "history",
                        "value": {
                            "metadata": {"phone_number_id": "PN_COEX"},
                            "history": [
                                {
                                    "messages": [
                                        {"id": "h1"},
                                        {"id": "h2"},
                                    ]
                                },
                                {"messages": [{"id": "h3"}]},
                            ],
                        },
                    }
                ],
            }
        ],
    }
    hist = parse_history_sync(payload)
    assert hist is not None
    assert hist.message_count == 3
    assert hist.error_code is None


def test_parse_history_sync_surfaces_opt_out_error_code():
    """error_code 2593109 = business opted out of sharing history."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_COEX",
                "changes": [
                    {
                        "field": "history",
                        "value": {
                            "metadata": {"phone_number_id": "PN_COEX"},
                            "error_code": 2593109,
                            "history": [],
                        },
                    }
                ],
            }
        ],
    }
    hist = parse_history_sync(payload)
    assert hist is not None
    assert hist.message_count == 0
    assert hist.error_code == 2593109
