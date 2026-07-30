"""Unit tests for the shared admin-only gate.

Single source of truth used by the worker dispatcher (skip the reply) and
the Meta webhook (skip the read receipt) — a non-admin on an admin-only
coexistence line must get NEITHER.
"""

from __future__ import annotations

import pytest

from nexus_api.core.admin_gate import (
    ROLE_FULL,
    ROLE_READONLY,
    admin_only_suppresses,
    sender_is_admin,
    sender_role,
)

pytestmark = [pytest.mark.unit]

_ADMINS = ["+34610777570", "+584249125716", "+34632719028"]


@pytest.mark.parametrize(
    "sender",
    ["+34632719028", "34632719028", "0424-912-5716", "+58 424 912 5716"],
)
def test_sender_is_admin_matches_variants(sender: str) -> None:
    assert sender_is_admin(sender, _ADMINS) is True


@pytest.mark.parametrize("sender", ["+34999999999", "", None, "12345"])
def test_sender_is_admin_rejects(sender: str | None) -> None:
    assert sender_is_admin(sender, _ADMINS) is False


def test_suppress_when_admin_only_and_not_admin() -> None:
    policies = {"admin_access": {"admin_only": True, "admin_phones": _ADMINS}}
    assert admin_only_suppresses(policies, "+34999999999") is True  # brother → suppress


def test_no_suppress_for_admin_sender() -> None:
    policies = {"admin_access": {"admin_only": True, "admin_phones": _ADMINS}}
    assert admin_only_suppresses(policies, "+34632719028") is False


def test_no_suppress_when_not_admin_only() -> None:
    # A normal (non-admin-only) agent never suppresses — everyone is served.
    assert (
        admin_only_suppresses({"admin_access": {"admin_phones": _ADMINS}}, "+34999999999") is False
    )
    assert admin_only_suppresses({}, "+34999999999") is False
    assert admin_only_suppresses(None, "+34999999999") is False


# ── per-admin roles ─────────────────────────────────────────────────────────

_ROLE_POLICIES = {
    "admin_access": {
        "admin_only": True,
        "admin_phones": ["+584249398142", "+584249693698"],
        "admins": [
            {"phone": "+584249398142", "role": "full"},
            {"phone": "+584249693698", "role": "readonly"},
        ],
    }
}


def test_sender_role_full() -> None:
    assert sender_role(_ROLE_POLICIES, "584249398142") == ROLE_FULL


@pytest.mark.parametrize("sender", ["+584249693698", "0424-969-3698", "584249693698"])
def test_sender_role_readonly_tolerates_format(sender: str) -> None:
    assert sender_role(_ROLE_POLICIES, sender) == ROLE_READONLY


def test_sender_role_none_for_non_admin() -> None:
    assert sender_role(_ROLE_POLICIES, "+34999999999") is None
    assert sender_role(_ROLE_POLICIES, None) is None


def test_sender_role_defaults_full_without_admins_list() -> None:
    # Back-compat: a whitelist with no per-admin roles keeps every admin full.
    pol = {"admin_access": {"admin_phones": ["+584249398142"]}}
    assert sender_role(pol, "584249398142") == ROLE_FULL


def test_sender_role_unknown_role_string_is_full() -> None:
    # Fail-open on POWER only for someone who IS a whitelisted admin.
    pol = {
        "admin_access": {
            "admin_phones": ["+584249398142"],
            "admins": [{"phone": "+584249398142", "role": "superuser"}],
        }
    }
    assert sender_role(pol, "584249398142") == ROLE_FULL


def test_sender_role_non_admin_never_gets_a_role_via_admins_list() -> None:
    # An entry in ``admins`` still only matches its own phone.
    assert sender_role(_ROLE_POLICIES, "+584240000000") is None
