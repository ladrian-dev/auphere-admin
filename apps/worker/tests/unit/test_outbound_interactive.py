"""Unit tests for the ``_to_meta_interactive`` converter in the
outbound dispatcher.

The converter is the bridge between our ``response.send_interactive``
tool payload (validated by Pydantic in ``nexus_mcp.servers.notification.
schemas``) and the Meta WhatsApp Cloud API ``interactive`` block the
adapter sends. Bugs here surface as Cloud API 4xx errors at send time
— much better to catch the shape regressions in a 0.01s unit test.
"""

from __future__ import annotations

import pytest

from nexus_worker.streams.outbound import _to_meta_interactive


class TestButtons:
    def test_minimum_buttons_block_shape(self) -> None:
        payload = {
            "body": "¿Confirmás?",
            "buttons": [
                {"id": "yes", "title": "Sí"},
                {"id": "no", "title": "No"},
            ],
        }
        block = _to_meta_interactive(payload)
        assert block["type"] == "button"
        assert block["body"] == {"text": "¿Confirmás?"}
        assert block["action"] == {
            "buttons": [
                {"type": "reply", "reply": {"id": "yes", "title": "Sí"}},
                {"type": "reply", "reply": {"id": "no", "title": "No"}},
            ]
        }
        # Optional sections absent when not provided.
        assert "header" not in block
        assert "footer" not in block

    def test_header_and_footer_attached(self) -> None:
        payload = {
            "body": "?",
            "header": "Reserva",
            "footer": "Vence en 5 min",
            "buttons": [{"id": "a", "title": "Sí"}],
        }
        block = _to_meta_interactive(payload)
        assert block["header"] == {"type": "text", "text": "Reserva"}
        assert block["footer"] == {"text": "Vence en 5 min"}


class TestList:
    def test_list_wraps_items_in_single_section(self) -> None:
        payload = {
            "body": "Elige una opción:",
            "list": {
                "button": "Ver opciones",
                "items": [
                    {"id": "x", "title": "Uno", "description": "primero"},
                    {"id": "y", "title": "Dos"},
                ],
            },
        }
        block = _to_meta_interactive(payload)
        assert block["type"] == "list"
        action = block["action"]
        assert action["button"] == "Ver opciones"
        assert len(action["sections"]) == 1
        rows = action["sections"][0]["rows"]
        assert rows[0] == {
            "id": "x",
            "title": "Uno",
            "description": "primero",
        }
        # Description omitted when absent — Cloud API doesn't tolerate
        # the key with an empty value.
        assert rows[1] == {"id": "y", "title": "Dos"}


class TestCtaUrl:
    def test_cta_url_uses_meta_action_shape(self) -> None:
        payload = {
            "body": "Tu link:",
            "cta_url": {"text": "Ir al sitio", "url": "https://x.com/c/abc"},
        }
        block = _to_meta_interactive(payload)
        assert block["type"] == "cta_url"
        assert block["action"] == {
            "name": "cta_url",
            "parameters": {
                "display_text": "Ir al sitio",
                "url": "https://x.com/c/abc",
            },
        }


class TestProducts:
    def test_single_product_message(self) -> None:
        block = _to_meta_interactive(
            {"body": "Mira esta máquina 👇", "products": ["2291"]},
            catalog_id="CAT_123",
        )
        assert block["type"] == "product"
        assert block["body"] == {"text": "Mira esta máquina 👇"}
        assert "header" not in block  # single product messages have no header
        assert block["action"] == {
            "catalog_id": "CAT_123",
            "product_retailer_id": "2291",
        }

    def test_multi_product_list(self) -> None:
        block = _to_meta_interactive(
            {"body": "Opciones", "header": "Máquinas", "products": ["2291", "2363", "2388"]},
            catalog_id="CAT_123",
        )
        assert block["type"] == "product_list"
        assert block["header"] == {"type": "text", "text": "Máquinas"}
        assert block["action"] == {
            "catalog_id": "CAT_123",
            "sections": [
                {
                    "title": "Máquinas",
                    "product_items": [
                        {"product_retailer_id": "2291"},
                        {"product_retailer_id": "2363"},
                        {"product_retailer_id": "2388"},
                    ],
                }
            ],
        }

    def test_products_without_catalog_id_raises(self) -> None:
        with pytest.raises(ValueError, match="catalog_id"):
            _to_meta_interactive({"body": "x", "products": ["2291"]}, catalog_id=None)


class TestMalformed:
    def test_no_component_raises(self) -> None:
        with pytest.raises(ValueError, match="missing buttons / list / cta_url"):
            _to_meta_interactive({"body": "?"})

    def test_context_message_id_not_in_block(self) -> None:
        """``context_message_id`` is metadata for the dispatcher — it
        becomes a sibling ``context`` arg on adapter.send_interactive,
        NOT a field inside the interactive block. The converter must
        strip it so Cloud API doesn't reject the call."""
        payload = {
            "body": "?",
            "buttons": [{"id": "a", "title": "Sí"}],
            "context_message_id": "wamid.HBgL...",
        }
        block = _to_meta_interactive(payload)
        assert "context_message_id" not in block
        assert "context" not in block
