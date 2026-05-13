"""Unit tests for the registry — pure-Python, no DB."""

from __future__ import annotations

import pytest

from nexus_mcp import build_default_registry
from nexus_mcp.registry import reset_default_registry

pytestmark = [pytest.mark.unit]


def test_default_registry_has_all_block_d_tools():
    """21 Block-D + ``operator.consult_owner`` (ADR-018) + 6 native-output
    notification tools (migration 0020) = 28. The ``agendapro.*`` internal
    tools were dropped in migration 0021 (ADR-017)."""
    reset_default_registry()
    reg = build_default_registry()
    names = set(reg.names())
    assert len(names) == 28
    assert "operator.consult_owner" in names
    # The admin browser MCP is gone; no internal tools registered.
    assert reg.internal_names() == ()

    # Spot check namespaces.
    assert any(n.startswith("booking.") for n in names)
    assert any(n.startswith("queue.") for n in names)
    assert any(n.startswith("client.") for n in names)
    assert any(n.startswith("notification.") for n in names)
    assert any(n.startswith("commission.") for n in names)
    assert any(n.startswith("escalate.") for n in names)
    assert any(n.startswith("operator.") for n in names)


def test_get_tool_definitions_filters_to_whitelist():
    reset_default_registry()
    reg = build_default_registry()
    defs = reg.get_tool_definitions(["booking.check_availability", "queue.join_queue"])
    names = {d.name for d in defs}
    assert names == {"booking.check_availability", "queue.join_queue"}


def test_get_tool_definitions_drops_unknown_names():
    reset_default_registry()
    reg = build_default_registry()
    defs = reg.get_tool_definitions(["does.not.exist", "booking.check_availability"])
    names = {d.name for d in defs}
    assert names == {"booking.check_availability"}


def test_tool_def_renders_openai_function_shape():
    reset_default_registry()
    reg = build_default_registry()
    defs = reg.get_openai_tools(["client.get_history"])
    assert len(defs) == 1
    spec = defs[0]
    assert spec["type"] == "function"
    assert spec["function"]["name"] == "client.get_history"
    assert "parameters" in spec["function"]
    assert spec["function"]["parameters"]["type"] == "object"
