from __future__ import annotations

import pytest

from ucm_schema import validate


@pytest.mark.parametrize("key", [
    "text_plain", "quick_replies_3", "list_small", "cta_url",
    "media_image", "location", "flow",
])
def test_valid_passes_on_whatsapp(valid_fixtures, key):
    r = validate(valid_fixtures[key], "whatsapp")
    assert r.ok, [i.message for i in r.issues]


def test_quick_replies_5_fails_whatsapp(valid_fixtures):
    r = validate(valid_fixtures["quick_replies_5"], "whatsapp")
    assert not r.ok
    assert any("5 buttons" in i.message and i.kind == "limit" for i in r.issues)


def test_quick_replies_5_passes_instagram(valid_fixtures):
    r = validate(valid_fixtures["quick_replies_5"], "instagram")
    assert r.ok


def test_list_unsupported_in_instagram(valid_fixtures):
    r = validate(valid_fixtures["list_small"], "instagram")
    assert not r.ok
    assert any(i.kind == "capability" for i in r.issues)


def test_flow_unsupported_in_voice(valid_fixtures):
    r = validate(valid_fixtures["flow"], "voice")
    assert not r.ok
    assert any(i.kind == "capability" for i in r.issues)


def test_markdown_unsupported_in_whatsapp(valid_fixtures):
    r = validate(valid_fixtures["text_markdown"], "whatsapp")
    assert not r.ok
    assert any("text.markdown" in i.message for i in r.issues)


def test_quick_replies_title_too_long_whatsapp():
    payload = {
        "ucm_version": "1.0.0",
        "message_id": "x",
        "type": "quick_replies",
        "capabilities_required": ["interactive.buttons"],
        "fallback_text": "fallback",
        "metadata": {},
        "content": {
            "body": "Elige",
            "buttons": [{"id": "a", "title": "Yes"}, {"id": "b", "title": "Yo"}],
        },
    }
    r = validate(payload, "whatsapp")
    assert r.ok  # within limits


def test_shape_error_returns_shape_issue(invalid_fixtures):
    r = validate(invalid_fixtures["missing_fallback"], "whatsapp")
    assert not r.ok
    assert all(i.kind == "shape" for i in r.issues)


def test_composite_depth_limit_whatsapp():
    nested = {
        "ucm_version": "1.0.0",
        "message_id": "x",
        "type": "composite",
        "capabilities_required": [],
        "fallback_text": "f",
        "metadata": {},
        "content": {
            "children": [
                {
                    "ucm_version": "1.0.0",
                    "message_id": "y",
                    "type": "composite",
                    "capabilities_required": [],
                    "fallback_text": "f",
                    "metadata": {},
                    "content": {
                        "children": [
                            {
                                "ucm_version": "1.0.0",
                                "message_id": "z",
                                "type": "text",
                                "capabilities_required": ["text"],
                                "fallback_text": "f",
                                "metadata": {},
                                "content": {"body": "deep", "format": "plain"},
                            }
                        ]
                    },
                }
            ]
        },
    }
    r = validate(nested, "whatsapp")
    assert not r.ok
    assert any("composite depth" in i.message for i in r.issues)


def test_list_too_many_rows_whatsapp():
    rows = [{"id": f"r{i}", "title": f"R{i}"} for i in range(15)]
    payload = {
        "ucm_version": "1.0.0",
        "message_id": "x",
        "type": "list",
        "capabilities_required": ["interactive.list"],
        "fallback_text": "f",
        "metadata": {},
        "content": {
            "body": "Elige",
            "button_text": "Ver",
            "sections": [{"title": "Sección", "rows": rows[:10]}],
        },
    }
    # 10 rows = limit exactly → ok
    r = validate(payload, "whatsapp")
    assert r.ok

    # 11 rows → fail (need to split into 2 sections to bypass per-section limit of 10)
    payload2 = {
        **payload,
        "content": {
            **payload["content"],
            "sections": [
                {"title": "S1", "rows": rows[:8]},
                {"title": "S2", "rows": rows[8:11]},
            ],
        },
    }
    r2 = validate(payload2, "whatsapp")
    assert not r2.ok
    assert any("rows total" in i.message for i in r2.issues)


def test_text_body_too_long_voice():
    payload = {
        "ucm_version": "1.0.0",
        "message_id": "x",
        "type": "text",
        "capabilities_required": ["text"],
        "fallback_text": "f",
        "metadata": {},
        "content": {"body": "x" * 700, "format": "plain"},
    }
    r = validate(payload, "voice")
    assert not r.ok
    assert any("text body" in i.message for i in r.issues)


def test_text_body_within_limit_passes():
    payload = {
        "ucm_version": "1.0.0",
        "message_id": "x",
        "type": "text",
        "capabilities_required": ["text"],
        "fallback_text": "fb",
        "metadata": {},
        "content": {"body": "y" * 599, "format": "plain"},
    }
    r = validate(payload, "voice")
    assert r.ok


def test_quick_replies_body_too_long_voice_unsupported():
    # Even though body would exceed voice's 600-char limit, the capability
    # check fires first (voice has no interactive.buttons).
    payload = {
        "ucm_version": "1.0.0",
        "message_id": "x",
        "type": "quick_replies",
        "capabilities_required": ["interactive.buttons"],
        "fallback_text": "f",
        "metadata": {},
        "content": {
            "body": "y" * 700,
            "buttons": [{"id": "a", "title": "yes"}],
        },
    }
    r = validate(payload, "voice")
    assert not r.ok
    kinds = {i.kind for i in r.issues}
    assert "capability" in kinds
    assert "limit" in kinds  # both issues are reported
