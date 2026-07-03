"""Unit tests for the shared admin-only gate.

Single source of truth used by the worker dispatcher (skip the reply) and
the Meta webhook (skip the read receipt) — a non-admin on an admin-only
coexistence line must get NEITHER.
"""

from __future__ import annotations

import pytest

from nexus_api.core.admin_gate import admin_only_suppresses, sender_is_admin

pytestmark = [pytest.mark.unit]

_ADMINS = ["+34610777570", "+584249125716", "+34632719028"]


@pytest.mark.parametrize(
    "sender",
    ["+34632719028", "34632719028", "0424-912-5716", "+58 424 409 5405".replace("405", "716")],
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
