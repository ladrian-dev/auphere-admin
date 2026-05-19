"""Coverage of defensive paths in `degrade.py`.

Some degradation branches handle channels whose structural limits are TIGHTER
than the schema's own caps. None of the current channels (web/whatsapp/
instagram/messenger/voice) exercise these branches because schema limits and
channel limits coincide. To cover them, we monkey-patch a temporary channel
profile with tighter caps. This guards against silent regressions if a future
channel (e.g. Telegram with a 12-char button limit) is added.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from ucm_schema import degrade, parse_ucm
from ucm_schema.channels import capabilities as caps_mod


@pytest.fixture
def tight_channel(monkeypatch):
    """Inject a channel `tight` with very narrow limits."""
    from ucm_schema.channels.capabilities import (
        ChannelLimits,
        ChannelProfile,
        CHANNELS,
    )
    tight = ChannelProfile(
        name="whatsapp",  # reuse a known ChannelName literal
        capabilities=frozenset(
            {
                "text",
                "interactive.buttons",
                "interactive.list",
                "interactive.cta_url",
                "media.image",
                "location",
                "flow",
            }
        ),
        limits=ChannelLimits(
            quick_replies_max_buttons=2,
            quick_replies_title_max_chars=5,
            list_max_rows_total=4,
            list_row_title_max_chars=5,
            list_row_description_max_chars=10,
            list_button_text_max_chars=5,
            cta_url_button_title_max_chars=5,
            text_body_max_chars=20,
            composite_max_depth=1,
        ),
    )
    new_channels = {**CHANNELS, "whatsapp": tight}
    monkeypatch.setattr(caps_mod, "CHANNELS", new_channels)
    monkeypatch.setattr(caps_mod, "WHATSAPP", tight)
    return tight


def test_quick_replies_title_truncation_defensive(tight_channel):
    payload = {
        "ucm_version": "1.0.0",
        "message_id": "x",
        "type": "quick_replies",
        "capabilities_required": ["interactive.buttons"],
        "fallback_text": "fb",
        "metadata": {},
        "content": {
            "body": "Pick",
            "buttons": [
                {"id": "a", "title": "Twelve chars"},
                {"id": "b", "title": "Six!!"},
            ],
        },
    }
    ucm = parse_ucm(payload)
    r = degrade(ucm, "whatsapp")
    assert r.changed
    assert r.ucm.type == "quick_replies"
    # truncated to 5 chars (with ellipsis on overflow)
    assert all(len(b.title) <= 5 for b in r.ucm.content.buttons)


def test_quick_replies_no_list_fallback_to_text(monkeypatch):
    """Inject a channel with buttons but no list, then over-fill."""
    from ucm_schema.channels.capabilities import (
        ChannelLimits,
        ChannelProfile,
        CHANNELS,
    )
    narrow = ChannelProfile(
        name="instagram",
        capabilities=frozenset({"text", "interactive.buttons"}),
        limits=ChannelLimits(
            quick_replies_max_buttons=2,
            text_body_max_chars=200,
            composite_max_depth=1,
        ),
    )
    monkeypatch.setattr(caps_mod, "CHANNELS", {**CHANNELS, "instagram": narrow})
    monkeypatch.setattr(caps_mod, "INSTAGRAM", narrow)

    payload = {
        "ucm_version": "1.0.0",
        "message_id": "x",
        "type": "quick_replies",
        "capabilities_required": ["interactive.buttons"],
        "fallback_text": "Choose: a/b/c",
        "metadata": {},
        "content": {
            "body": "Pick",
            "buttons": [
                {"id": "a", "title": "A"},
                {"id": "b", "title": "B"},
                {"id": "c", "title": "C"},
            ],
        },
    }
    ucm = parse_ucm(payload)
    r = degrade(ucm, "instagram")
    assert r.changed
    assert r.ucm.type == "text"
    assert r.ucm.content.body == "Choose: a/b/c"


def test_list_button_text_truncation_defensive(tight_channel):
    payload = {
        "ucm_version": "1.0.0",
        "message_id": "x",
        "type": "list",
        "capabilities_required": ["interactive.list"],
        "fallback_text": "fb",
        "metadata": {},
        "content": {
            "body": "Pick",
            "button_text": "Ver más opciones",
            "sections": [
                {"title": "S1", "rows": [{"id": "a", "title": "Row"}]},
            ],
        },
    }
    ucm = parse_ucm(payload)
    r = degrade(ucm, "whatsapp")
    assert r.changed
    assert len(r.ucm.content.button_text) <= 5


def test_cta_url_button_title_truncation_defensive(tight_channel):
    payload = {
        "ucm_version": "1.0.0",
        "message_id": "x",
        "type": "cta_url",
        "capabilities_required": ["interactive.cta_url"],
        "fallback_text": "fb",
        "metadata": {},
        "content": {
            "body": "Reserva",
            "button_title": "Reservar ahora",
            "url": "https://x.com/r",
        },
    }
    ucm = parse_ucm(payload)
    r = degrade(ucm, "whatsapp")
    assert r.changed
    assert len(r.ucm.content.button_title) <= 5


def test_media_caption_truncation_defensive(tight_channel):
    payload = {
        "ucm_version": "1.0.0",
        "message_id": "x",
        "type": "media",
        "capabilities_required": ["media.image"],
        "fallback_text": "fb",
        "metadata": {},
        "content": {
            "kind": "image",
            "url": "https://x.com/i.jpg",
            "caption": "This caption is much longer than twenty chars",
        },
    }
    ucm = parse_ucm(payload)
    r = degrade(ucm, "whatsapp")
    assert r.changed
    assert r.ucm.type == "media"
    assert len(r.ucm.content.caption) <= 20


def test_text_truncation_defensive(tight_channel):
    payload = {
        "ucm_version": "1.0.0",
        "message_id": "x",
        "type": "text",
        "capabilities_required": ["text"],
        "fallback_text": "fb",
        "metadata": {},
        "content": {"body": "y" * 100, "format": "plain"},
    }
    ucm = parse_ucm(payload)
    r = degrade(ucm, "whatsapp")
    assert r.changed
    assert len(r.ucm.content.body) == 20


def test_truncate_edge_cases():
    """Exercise the _truncate helper for max_len <= 1 corner."""
    from ucm_schema.degrade import _truncate

    assert _truncate("abc", 5) == "abc"
    assert _truncate("abcdef", 1) == "a"
    assert _truncate("abcdef", 0) == ""
    assert _truncate("abcdef", 3) == "ab…"
