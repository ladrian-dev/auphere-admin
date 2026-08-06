"""Unit tests for the duplicate-send guard in the checkpoint node.

The model routinely paraphrases the same sentence into both the free
text AND the interactive component's ``body``; without this guard the
customer receives two near-identical WhatsApp messages back-to-back
(barbersupply "Pagar ahora" incident). ``_text_duplicates_body`` is the
pure decision the checkpoint node uses to suppress the redundant text
row, tested here DB-free.
"""

from __future__ import annotations

import pytest

from nexus_worker.runtime.pipeline import (
    _checkout_url_from_interactive,
    _normalise_for_dup,
    _text_duplicates_body,
)


class TestNormalise:
    def test_strips_emojis_punctuation_and_case(self) -> None:
        # Accents are preserved (kept on both sides of the comparison); only
        # emojis, punctuation and case are normalised away.
        assert _normalise_for_dup("¡Listo! Completa acá 👉") == "listo completa acá"

    def test_keeps_accents_and_digits(self) -> None:
        assert _normalise_for_dup("Total: $36.990 — Máquina") == "total 36 990 máquina"


class TestDuplicateDetection:
    def test_exact_paraphrase_is_duplicate(self) -> None:
        # The real failure: same message as text and as button body.
        text = "Completa tu compra acá 👉 Ahí eliges retiro en tienda y pagas de forma segura."
        body = (
            "¡Listo! Completa tu compra en el siguiente enlace. Ahí seleccionas "
            "retiro en tienda y pagas de forma segura 🔒"
        )
        assert _text_duplicates_body(text, body) is True

    def test_substring_is_duplicate(self) -> None:
        assert _text_duplicates_body("Completa tu pedido acá", "Completa tu pedido acá 👉") is True

    def test_distinct_explanation_is_not_duplicate(self) -> None:
        # A genuine product summary before an actionable button must survive.
        text = "Tenemos la Wahl Magic Clip a $39.990 y la Andis a $34.990, ambas con stock."
        body = "¿Confirmas el pedido?"
        assert _text_duplicates_body(text, body) is False

    @pytest.mark.parametrize("empty", ["", "   ", "👉🔒"])
    def test_empty_or_decoration_only_is_never_duplicate(self, empty: str) -> None:
        assert _text_duplicates_body(empty, "Completa tu compra acá") is False
        assert _text_duplicates_body("Completa tu compra acá", empty) is False


class TestCheckoutUrlExtraction:
    def test_extracts_cta_url(self) -> None:
        payload = {
            "body": "Listo, acá completas tu pedido.",
            "cta_url": {"text": "Completar pedido", "url": "https://shop.cl/finalizar-compra/?x=1"},
        }
        assert _checkout_url_from_interactive(payload) == "https://shop.cl/finalizar-compra/?x=1"

    def test_buttons_have_no_checkout_url(self) -> None:
        # Confirm buttons are not payment links — never guarded.
        payload = {"body": "¿Confirmas?", "buttons": [{"id": "yes", "title": "Sí"}]}
        assert _checkout_url_from_interactive(payload) is None

    @pytest.mark.parametrize("payload", [None, {}, {"cta_url": {}}, {"cta_url": {"url": "  "}}])
    def test_missing_or_blank_url_returns_none(self, payload: object) -> None:
        assert _checkout_url_from_interactive(payload) is None  # type: ignore[arg-type]
