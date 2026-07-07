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


class TestInteractivePayload:
    """The formatter recognises the ``response.send_interactive`` payload
    shape: a body plus exactly one of buttons / list / cta_url, plus
    optional header / footer / context_message_id metadata. When the
    agent ALSO emits text in the same turn, the result is a composite
    UCM with [text, interactive] children."""

    def _buttons_payload(self) -> dict[str, object]:
        return {
            "body": "¿Confirmas la reserva?",
            "buttons": [
                {"id": "yes", "title": "Sí, confirmo"},
                {"id": "no", "title": "Cancelar"},
            ],
        }

    def _list_payload(self) -> dict[str, object]:
        return {
            "body": "Estos matchean tu búsqueda:",
            "list": {
                "button": "Ver opciones",
                "items": [
                    {"id": "p1", "title": "Sábana queen", "description": "$29.990"},
                    {"id": "p2", "title": "Sábana king", "description": "$39.990"},
                ],
            },
        }

    def _cta_url_payload(self) -> dict[str, object]:
        return {
            "body": "Listo, pagas aquí:",
            "cta_url": {"text": "Pagar pedido", "url": "https://vedhome.cl/c/abc"},
        }

    def test_buttons_only_no_text_produces_quick_replies_ucm(self) -> None:
        ucm = format_response_as_ucm(
            response_text="",
            interactive_payload=self._buttons_payload(),
        )
        assert ucm.type == "quick_replies"
        assert ucm.content.body == "¿Confirmas la reserva?"
        assert [b.title for b in ucm.content.buttons] == [
            "Sí, confirmo",
            "Cancelar",
        ]

    def test_list_only_no_text_produces_list_ucm(self) -> None:
        ucm = format_response_as_ucm(
            response_text="",
            interactive_payload=self._list_payload(),
        )
        assert ucm.type == "list"
        assert ucm.content.body == "Estos matchean tu búsqueda:"
        assert ucm.content.button_text == "Ver opciones"
        assert len(ucm.content.sections) == 1
        assert [r.title for r in ucm.content.sections[0].rows] == [
            "Sábana queen",
            "Sábana king",
        ]

    def test_cta_url_only_no_text_produces_cta_url_ucm(self) -> None:
        ucm = format_response_as_ucm(
            response_text="",
            interactive_payload=self._cta_url_payload(),
        )
        assert ucm.type == "cta_url"
        assert ucm.content.button_title == "Pagar pedido"
        assert str(ucm.content.url) == "https://vedhome.cl/c/abc"

    def test_text_plus_buttons_produces_composite(self) -> None:
        ucm = format_response_as_ucm(
            response_text="Encontré tu cita disponible.",
            interactive_payload=self._buttons_payload(),
            message_id="msg_42",
        )
        assert ucm.type == "composite"
        assert len(ucm.content.children) == 2
        # Text child first, interactive second (the dispatcher
        # serialises them in this order so the customer reads the
        # explanation before the choice).
        assert ucm.content.children[0].type == "text"
        assert ucm.content.children[0].content.body == ("Encontré tu cita disponible.")
        assert ucm.content.children[1].type == "quick_replies"
        assert ucm.content.children[1].content.body == "¿Confirmas la reserva?"
        # Children inherit a stable id derived from the parent so
        # traces stay joinable.
        assert ucm.content.children[0].message_id == "msg_42::text"
        assert ucm.content.children[1].message_id == "msg_42::interactive"

    def test_header_and_footer_travel_in_list_content(self) -> None:
        payload: dict[str, object] = {
            **self._list_payload(),
            "header": "Tu búsqueda",
            "footer": "Precios CLP",
        }
        ucm = format_response_as_ucm(response_text="", interactive_payload=payload)
        assert ucm.content.header == "Tu búsqueda"
        assert ucm.content.footer == "Precios CLP"

    def test_missing_component_raises(self) -> None:
        """Defence in depth: even if the tool's validator was bypassed,
        the formatter refuses to fabricate a UCM."""
        with pytest.raises(ValueError, match="no buttons / list / cta_url"):
            format_response_as_ucm(
                response_text="hola",
                interactive_payload={"body": "?", "header": "x"},
            )


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
