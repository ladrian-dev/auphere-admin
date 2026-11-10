"""INC-71: an agent with the catalog skills searches before denying a product."""

from __future__ import annotations

from nexus_worker.runtime.pipeline import _CATALOG_NOTE, _catalog_note_applies

BOTH = ("catalog.search_products", "response.send_interactive")


def test_the_note_names_the_tools_it_asks_for() -> None:
    for tool in BOTH:
        assert tool in _CATALOG_NOTE


def test_whatsapp_with_both_tools_gets_the_note() -> None:
    assert _catalog_note_applies("whatsapp", BOTH)
    assert _catalog_note_applies(None, BOTH)


def test_product_cards_do_not_exist_outside_whatsapp() -> None:
    assert not _catalog_note_applies("instagram", BOTH)
    assert not _catalog_note_applies("messenger", BOTH)


def test_without_either_tool_the_note_would_promise_what_it_cannot_do() -> None:
    assert not _catalog_note_applies("whatsapp", BOTH[:1])
    assert not _catalog_note_applies("whatsapp", BOTH[1:])
