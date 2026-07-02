"""Unit tests for the dispatcher's admin-only sender gate.

``_sender_is_admin`` is the pure matcher behind
``policies.admin_access`` — when an agent is admin-only (cobranza_v1
v2), only whitelisted phones get a reply; everyone else's inbound is
persisted but silently skipped (``pipeline.skipped.not_admin``).
"""

from __future__ import annotations

import pytest

from nexus_worker.runtime.dispatcher import _sender_is_admin

pytestmark = [pytest.mark.unit]

_MOUNA_ADMINS = [
    "+34632719028",
    "+34672138367",
    "+34610777570",
    "+584249125716",
    "+584244095405",
]


@pytest.mark.parametrize(
    "sender",
    [
        "+34632719028",  # exact E.164
        "34632719028",  # WhatsApp wa_id (no plus)
        "0424-912-5716",  # local format with punctuation
        "+58 424 409 5405",  # spaces
    ],
)
def test_admin_variants_match(sender: str) -> None:
    assert _sender_is_admin(sender, _MOUNA_ADMINS) is True


@pytest.mark.parametrize(
    "sender",
    [
        "+584241234567",  # a debtor, not an admin
        "+34999999999",  # unknown Spanish number
        "",  # empty
        None,  # missing
        "12345",  # too short to ever be granted admin
    ],
)
def test_non_admins_do_not_match(sender: str | None) -> None:
    assert _sender_is_admin(sender, _MOUNA_ADMINS) is False


def test_empty_whitelist_matches_nobody() -> None:
    assert _sender_is_admin("+34632719028", []) is False


def test_short_whitelist_entries_are_ignored() -> None:
    # A malformed 5-digit entry must never grant access via suffix match.
    assert _sender_is_admin("+584244095405", ["95405"]) is False
