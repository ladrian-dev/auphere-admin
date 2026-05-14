"""Tests for the Block N webhook parsers — status callbacks, template
approval events, and opt-out keyword detection."""

from __future__ import annotations

from nexus_channels.whatsapp_ycloud.webhook_adapter import (
    is_opt_out_text,
    parse_status_callback,
    parse_template_status,
)

# ── status callback parser ──────────────────────────────────────────────────


def test_status_callback_delivered():
    payload = {
        "type": "whatsapp.message.updated",
        "whatsappMessage": {
            "wamid": "wamid.out_1",
            "from": "+56933334444",
            "to": "+56911112222",
            "status": "delivered",
            "timestamp": "1715567890",
            "pricing": {"category": "service"},
            "conversation": {"id": "conv-abc"},
        },
    }
    cb = parse_status_callback(payload)
    assert cb is not None
    assert cb.wamid == "wamid.out_1"
    assert cb.business_phone == "+56933334444"
    assert cb.recipient_phone == "+56911112222"
    assert cb.status == "delivered"
    assert cb.pricing_category == "service"
    assert cb.conversation_provider_id == "conv-abc"
    assert cb.failure_code is None


def test_status_callback_failed_with_error_code():
    payload = {
        "type": "whatsapp.message.updated",
        "whatsappMessage": {
            "wamid": "wamid.out_2",
            "from": "+56933334444",
            "status": "failed",
            "timestamp": "1715567890",
            "errors": [
                {"code": 131026, "title": "Receiver unavailable", "detail": "blocked"}
            ],
        },
    }
    cb = parse_status_callback(payload)
    assert cb is not None
    assert cb.status == "failed"
    assert cb.failure_code == "131026"
    assert cb.failure_title == "Receiver unavailable"
    assert cb.failure_detail == "blocked"


def test_status_callback_wrong_event_type_returns_none():
    payload = {"type": "whatsapp.inbound_message.received"}
    assert parse_status_callback(payload) is None


def test_status_callback_legacy_event_type():
    """YCloud's older event name still arrives in some accounts."""
    payload = {
        "type": "whatsapp.message_status_update",
        "whatsappMessage": {
            "wamid": "wamid.out_legacy",
            "from": "+56933334444",
            "status": "read",
            "timestamp": "1715567890",
        },
    }
    cb = parse_status_callback(payload)
    assert cb is not None
    assert cb.status == "read"


# ── template approval parser ────────────────────────────────────────────────


def test_template_status_approved():
    payload = {
        "type": "whatsapp.template.updated",
        "whatsappTemplate": {
            "wabaId": "1234567890",
            "name": "appointment_reminder_24h",
            "language": "es",
            "category": "UTILITY",
            "status": "APPROVED",
        },
    }
    event = parse_template_status(payload)
    assert event is not None
    assert event.waba_id == "1234567890"
    assert event.template_name == "appointment_reminder_24h"
    assert event.status == "approved"
    assert event.category == "UTILITY"


def test_template_status_rejected_with_reason():
    payload = {
        "type": "whatsapp.template_status_update",  # legacy alias
        "whatsappMessageTemplate": {
            "waba_id": "abc",
            "template_name": "promo_1",
            "language": "es",
            "status": "REJECTED",
            "reason": "policy_violation",
        },
    }
    event = parse_template_status(payload)
    assert event is not None
    assert event.template_name == "promo_1"
    assert event.status == "rejected"
    assert event.reason == "policy_violation"


def test_template_status_wrong_type_returns_none():
    assert parse_template_status({"type": "whatsapp.inbound_message.received"}) is None


# ── opt-out keyword detection ───────────────────────────────────────────────


def test_opt_out_stop_keyword():
    matched, kw = is_opt_out_text("STOP")
    assert matched is True
    assert kw == "stop"


def test_opt_out_spanish_keywords():
    for body in ("baja", "BAJA", "Baja!", "cancelar", "  unsubscribe  "):
        matched, _ = is_opt_out_text(body)
        assert matched is True, f"expected opt-out for {body!r}"


def test_opt_out_multi_word():
    matched, kw = is_opt_out_text("darme de baja")
    assert matched is True
    assert kw == "darme de baja"


def test_opt_out_negative_in_sentence():
    # "no me molesten más" is a paragraph; the webhook leaves it to the LLM
    # rather than auto-opting out. Conservative on purpose.
    matched, _ = is_opt_out_text("ya no me molesten más por favor")
    assert matched is False


def test_opt_out_empty():
    assert is_opt_out_text(None) == (False, None)
    assert is_opt_out_text("") == (False, None)
