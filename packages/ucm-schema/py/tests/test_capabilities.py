from __future__ import annotations

import pytest

from ucm_schema import (
    CHANNELS,
    channel_supports,
    get_channel,
    infer_capabilities,
)


def test_all_channels_have_text():
    for name, channel in CHANNELS.items():
        assert "text" in channel.capabilities, f"{name} must support text"


def test_get_channel_unknown_raises():
    with pytest.raises(ValueError):
        get_channel("snail-mail")  # type: ignore[arg-type]


def test_voice_only_text():
    voice = get_channel("voice")
    assert voice.capabilities == frozenset({"text"})


def test_instagram_no_list_no_cta():
    ig = get_channel("instagram")
    assert not channel_supports(ig, "interactive.list")
    assert not channel_supports(ig, "interactive.cta_url")
    assert not channel_supports(ig, "flow")


def test_infer_capabilities_text_plain():
    assert infer_capabilities("text", {"body": "x", "format": "plain"}) == ["text"]


def test_infer_capabilities_text_markdown():
    assert infer_capabilities("text", {"body": "x", "format": "markdown"}) == [
        "text",
        "text.markdown",
    ]


def test_infer_capabilities_media():
    assert infer_capabilities("media", {"kind": "video"}) == ["media.video"]
    assert infer_capabilities("media", {"kind": "image"}) == ["media.image"]


def test_infer_capabilities_per_type():
    assert infer_capabilities("quick_replies", {}) == ["interactive.buttons"]
    assert infer_capabilities("list", {}) == ["interactive.list"]
    assert infer_capabilities("cta_url", {}) == ["interactive.cta_url"]
    assert infer_capabilities("location", {}) == ["location"]
    assert infer_capabilities("flow", {}) == ["flow"]
    assert infer_capabilities("composite", {}) == []
    assert infer_capabilities("unknown", {}) == []


def test_whatsapp_strict_limits():
    wa = get_channel("whatsapp")
    assert wa.limits.quick_replies_max_buttons == 3
    assert wa.limits.list_max_rows_total == 10
    assert wa.limits.text_body_max_chars == 1024
