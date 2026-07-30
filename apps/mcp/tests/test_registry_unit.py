"""Unit tests for the registry — pure-Python, no DB."""

from __future__ import annotations

import pytest

from nexus_mcp import build_default_registry
from nexus_mcp.registry import reset_default_registry

pytestmark = [pytest.mark.unit]


def test_default_registry_has_all_block_d_tools():
    """21 Block-D + ``operator.consult_owner`` (ADR-018) + 6 native-output
    notification tools (migration 0020) + 12 woocommerce.* tools
    (migration 0024) + ``response.send_interactive`` (migration 0036)
    + 12 billing.* Amigable Cobro tools (5 reads + 6 admin writes + the
    on-demand ``billing.send_reminders`` from migration 0058) = 54 LLM-facing.

    Block O (ADR-017) registers 2 INTERNAL tools (``agendapro_public.
    check_availability`` and ``.create_appointment``) that the booking
    facade and async cron reach via ``dispatch_internal``; the LLM
    never sees them.
    """
    reset_default_registry()
    reg = build_default_registry()
    names = set(reg.names())
    assert len(names) == 54
    assert "operator.consult_owner" in names
    assert "response.send_interactive" in names
    # Block O internal tools — not LLM-facing.
    internal = set(reg.internal_names())
    assert internal == {
        "agendapro_public.check_availability",
        "agendapro_public.create_appointment",
    }

    # Spot check namespaces.
    assert any(n.startswith("booking.") for n in names)
    assert any(n.startswith("queue.") for n in names)
    assert any(n.startswith("client.") for n in names)
    assert any(n.startswith("notification.") for n in names)
    assert any(n.startswith("commission.") for n in names)
    assert any(n.startswith("escalate.") for n in names)
    assert any(n.startswith("operator.") for n in names)
    assert any(n.startswith("woocommerce.") for n in names)
    # Pin the destructive 4 woocommerce tools exist, not just the namespace.
    assert {
        "woocommerce.create_order",
        "woocommerce.update_order",
        "woocommerce.update_order_status",
        "woocommerce.add_order_note",
    }.issubset(names)
    # Amigable Cobro (billing.*) — reads + admin writes (cobranza_v1 v2).
    assert {
        "billing.get_my_debt",
        "billing.get_debtor_by_phone",
        "billing.list_overdue",
        "billing.get_account",
        "billing.register_payment",
        "billing.update_status",
        "billing.apply_discount",
        "billing.create_account",
        "billing.update_account",
        "billing.send_reminders",
    }.issubset(names)


def test_is_side_effecting_reads_vs_writes():
    """The read-only-admin gate depends on this split: writes are side-
    effecting, reads are not, unknown names are False (safe default)."""
    reset_default_registry()
    reg = build_default_registry()
    for write in ("billing.register_payment", "billing.add_charge", "billing.send_reminders"):
        assert reg.is_side_effecting(write) is True, write
    for read in ("billing.list_overdue", "billing.get_account", "billing.find_client"):
        assert reg.is_side_effecting(read) is False, read
    assert reg.is_side_effecting("does.not.exist") is False


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
