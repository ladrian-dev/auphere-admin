"""Unit tests for the Phase 2 (ADR-020) UCM formatter helpers."""

from __future__ import annotations

import pytest

from nexus_worker.runtime.ucm_formatter import (
    _crude_diff_ratio,
    format_response_as_ucm,
    shadow_diff_against_legacy,
)


class TestFormatResponseAsUcm:
    def test_plain_text_wraps_into_text_ucm(self) -> None:
        ucm = format_response_as_ucm(response_text="Hola, ¿en qué te ayudo?")
        assert ucm.type == "text"
        assert ucm.content.body == "Hola, ¿en qué te ayudo?"
        assert ucm.content.format == "plain"
        assert ucm.fallback_text == "Hola, ¿en qué te ayudo?"
        assert ucm.ucm_version == "1.0.0"

    def test_stable_message_id_when_provided(self) -> None:
        ucm = format_response_as_ucm(response_text="hi", message_id="msg_stable_42")
        assert ucm.message_id == "msg_stable_42"

    def test_metadata_passthrough(self) -> None:
        ucm = format_response_as_ucm(
            response_text="hi",
            metadata={"tenant_id": "tnt_x", "intent": "info"},
        )
        assert ucm.metadata["tenant_id"] == "tnt_x"
        assert ucm.metadata["intent"] == "info"

    def test_empty_response_text_rejected_by_schema(self) -> None:
        # UCM requires text content.body to be at least 1 char. The
        # contract makes it explicit that ``format_response_as_ucm`` is
        # only valid for non-empty responses; the caller (the node) is
        # responsible for short-circuiting before this point if the agent
        # produced no reply.
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            format_response_as_ucm(response_text="")


class TestShadowDiff:
    def test_equivalent_for_plain_text(self) -> None:
        ucm = format_response_as_ucm(response_text="same text")
        diff = shadow_diff_against_legacy(ucm, "same text")
        assert diff["equivalent"] is True
        assert diff["diff_ratio"] == 0.0
        assert diff["degraded_type"] == "text"
        assert diff["steps"] == []

    def test_diverges_when_legacy_differs(self) -> None:
        ucm = format_response_as_ucm(response_text="hola")
        diff = shadow_diff_against_legacy(ucm, "completely different reply")
        assert diff["equivalent"] is False
        assert diff["diff_ratio"] > 0.0
        assert diff["degraded_text"] == "hola"

    def test_channel_default_is_whatsapp(self) -> None:
        ucm = format_response_as_ucm(response_text="hi")
        diff = shadow_diff_against_legacy(ucm, "hi")
        assert diff["channel"] == "whatsapp"

    def test_truncated_body_for_voice_channel_reports_steps(self) -> None:
        # Voice caps body at 600 chars. A long body forces a truncation
        # step; the diff still records both halves so the gate can decide
        # whether the truncation is acceptable.
        body = "y" * 700
        ucm = format_response_as_ucm(response_text=body)
        diff = shadow_diff_against_legacy(ucm, body, channel="voice")
        assert diff["equivalent"] is False
        assert any(s["from"] == "text" for s in diff["steps"])
        assert len(diff["degraded_text"]) == 600


class TestCrudeDiffRatio:
    @pytest.mark.parametrize(
        "a,b,expected",
        [
            ("abc", "abc", 0.0),
            ("", "", 0.0),
            ("abc", "", 1.0),
            ("", "abc", 1.0),
        ],
    )
    def test_edge_cases(self, a: str, b: str, expected: float) -> None:
        assert _crude_diff_ratio(a, b) == expected

    def test_partial_overlap_is_strictly_between(self) -> None:
        r = _crude_diff_ratio("hello", "world")
        assert 0.0 < r < 1.0
