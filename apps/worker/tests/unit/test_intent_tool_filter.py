"""Unit tests for the pre-LLM tool filter and the channel-format note.

Covers bug #11 (connector tools were dropped by the barbershop-era intent
map) and bug #12 (channel-aware output formatting). Both targets are pure
functions — no DB, no LLM — so they live in the worker unit suite.

The garantía-2 property asserted here: ``_filter_tools_for_intent_with_composio``
never returns a name that is not already in ``bundle.tools`` (the whitelist
stays the hard ceiling; the filter only ever narrows).
"""

from __future__ import annotations

import uuid

from nexus_worker.runtime.agent_loader import AgentBundle
from nexus_worker.runtime.pipeline import (
    _channel_format_note,
    _filter_tools_for_intent_with_composio,
)

# A native vertical tool (lives in the ``info`` intent category) and a
# WooCommerce-style connector tool (un-namespaced, in no intent category).
_NATIVE_INFO_TOOL = "client.get_history"
_CONNECTOR_TOOL = "list_products"
_CONNECTOR_TOOL_2 = "get_product"
_COMPOSIO_TOOL = "notion.create_page"


def _bundle(tools: set[str]) -> AgentBundle:
    return AgentBundle(
        tenant_id=uuid.uuid4(),
        version=1,
        version_id=uuid.uuid4(),
        system_prompt="test",
        tools=frozenset(tools),
        policies={},
    )


class TestIntentToolFilter:
    def test_connector_tool_surfaces_on_info(self) -> None:
        """Bug #11: a whitelisted connector tool reaches the LLM on ``info``."""
        bundle = _bundle({_CONNECTOR_TOOL, _CONNECTOR_TOOL_2, _NATIVE_INFO_TOOL})
        result = _filter_tools_for_intent_with_composio(bundle, "info")
        assert _CONNECTOR_TOOL in result
        assert _CONNECTOR_TOOL_2 in result
        # The native tool still routes via its intent category.
        assert _NATIVE_INFO_TOOL in result

    def test_connector_tool_surfaces_on_book_queue_fallback(self) -> None:
        bundle = _bundle({_CONNECTOR_TOOL})
        for intent in ("book", "queue", "fallback"):
            result = _filter_tools_for_intent_with_composio(bundle, intent)
            assert _CONNECTOR_TOOL in result, f"missing on intent={intent}"

    def test_connector_tool_excluded_on_escalate(self) -> None:
        """``escalate`` hands off to a human — no catalog browsing."""
        bundle = _bundle({_CONNECTOR_TOOL})
        result = _filter_tools_for_intent_with_composio(bundle, "escalate")
        assert _CONNECTOR_TOOL not in result

    def test_namespaced_composio_tool_surfaces_on_info(self) -> None:
        bundle = _bundle({_COMPOSIO_TOOL})
        result = _filter_tools_for_intent_with_composio(bundle, "info")
        assert _COMPOSIO_TOOL in result

    def test_result_is_always_a_subset_of_the_whitelist(self) -> None:
        """Garantía 2 at the filter plane: the filter only narrows — it can
        never surface a tool the operator did not whitelist."""
        whitelist = {_CONNECTOR_TOOL, _NATIVE_INFO_TOOL, _COMPOSIO_TOOL}
        bundle = _bundle(whitelist)
        for intent in ("book", "queue", "info", "escalate", "fallback"):
            result = _filter_tools_for_intent_with_composio(bundle, intent)
            assert set(result) <= whitelist, f"leak on intent={intent}: {result}"

    def test_non_whitelisted_connector_tool_never_appears(self) -> None:
        """A connector tool the operator did NOT whitelist stays invisible."""
        bundle = _bundle({_CONNECTOR_TOOL})  # get_product NOT whitelisted
        for intent in ("book", "queue", "info", "escalate", "fallback"):
            result = _filter_tools_for_intent_with_composio(bundle, intent)
            assert _CONNECTOR_TOOL_2 not in result


class TestChannelFormatNote:
    def test_whatsapp_note_mentions_whatsapp_formatting(self) -> None:
        note = _channel_format_note("whatsapp")
        assert "WhatsApp" in note
        assert "*bold*" in note

    def test_web_note_warns_against_whatsapp_markdown(self) -> None:
        note = _channel_format_note("web")
        assert "Markdown" in note
        assert "**bold**" in note

    def test_unknown_channel_defaults_to_web(self) -> None:
        # Any non-whatsapp channel gets the standard-Markdown note.
        assert _channel_format_note("instagram") == _channel_format_note("web")
