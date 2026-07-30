"""The read-only-admin tool gate (cobranza).

Mirrors exactly what the handler node does: for a ``readonly`` admin it drops
every side-effecting tool from the turn's whitelist, so a read-only admin can
query debts but the write tools are neither offered to the model NOR accepted
by ``registry.dispatch`` (they're off the whitelist). A ``full`` admin is
untouched.
"""

from __future__ import annotations

import pytest
from nexus_api.core.admin_gate import ROLE_FULL, ROLE_READONLY, sender_role
from nexus_mcp import build_default_registry
from nexus_mcp.registry import reset_default_registry

pytestmark = [pytest.mark.unit]

_POLICIES = {
    "admin_access": {
        "admin_only": True,
        "admin_phones": ["+584249398142", "+584249693698"],
        "admins": [
            {"phone": "+584249398142", "role": "full"},
            {"phone": "+584249693698", "role": "readonly"},
        ],
    }
}

# The cobranza whitelist: reads + writes + the interactive UI tool.
_WHITELIST = (
    "billing.get_debtor_by_phone",
    "billing.find_client",
    "billing.list_overdue",
    "billing.get_account",
    "billing.register_payment",
    "billing.add_charge",
    "billing.update_status",
    "billing.apply_discount",
    "billing.create_account",
    "billing.update_account",
    "billing.send_reminders",
    "response.send_interactive",
)

_WRITES = {
    "billing.register_payment",
    "billing.add_charge",
    "billing.update_status",
    "billing.apply_discount",
    "billing.create_account",
    "billing.update_account",
    "billing.send_reminders",
}
_READS = {
    "billing.get_debtor_by_phone",
    "billing.find_client",
    "billing.list_overdue",
    "billing.get_account",
}


def _apply_role_filter(names: tuple[str, ...], policies: dict, sender: str) -> tuple[str, ...]:
    """The exact filter the handler applies."""
    reset_default_registry()
    reg = build_default_registry()
    role = sender_role(policies, sender)
    if role == ROLE_READONLY:
        return tuple(n for n in names if not reg.is_side_effecting(n))
    return names


def test_readonly_admin_loses_every_write_tool() -> None:
    filtered = _apply_role_filter(_WHITELIST, _POLICIES, "0424-969-3698")
    assert _WRITES.isdisjoint(filtered), "a readonly admin must not see any write tool"
    assert _READS.issubset(filtered), "reads stay available"


def test_full_admin_keeps_everything() -> None:
    assert sender_role(_POLICIES, "584249398142") == ROLE_FULL
    filtered = _apply_role_filter(_WHITELIST, _POLICIES, "584249398142")
    assert filtered == _WHITELIST  # no filtering for full admins


def test_legacy_admin_without_role_keeps_everything() -> None:
    legacy = {"admin_access": {"admin_only": True, "admin_phones": ["+584249398142"]}}
    filtered = _apply_role_filter(_WHITELIST, legacy, "584249398142")
    assert filtered == _WHITELIST
