"""Spec 079, requisito 1: the role → permission matrix of the operator panel.

The panel keeps a copy (``apps/admin/src/lib/permissions.ts``) and its own test
reads this module's file to catch any drift; this one pins the table Luis
decided on 2026-11-25 (spec 079, criterion 1.2).
"""

from __future__ import annotations

import pytest

from nexus_api.core.operator_permissions import OPERATOR_PERMISSIONS, has_permission

PERMISSIONS = (
    "read",
    "qa",
    "operate",
    "money",
    "credentials",
    "impersonate",
    "people",
    "delete",
    "platform",
)

EXPECTED: dict[str, set[str]] = {
    "admin": set(PERMISSIONS),
    "qa_operator": {"read", "qa", "operate"},
    "viewer": {"read"},
}


def test_exactly_the_nine_permissions() -> None:
    assert tuple(OPERATOR_PERMISSIONS) == PERMISSIONS


@pytest.mark.parametrize("role", sorted(EXPECTED))
def test_each_role_has_exactly_what_the_spec_says(role: str) -> None:
    granted = {p for p in PERMISSIONS if has_permission(role, p)}
    assert granted == EXPECTED[role]


@pytest.mark.parametrize("role", ["", "owner", "superadmin", "ADMIN"])
def test_an_unknown_role_has_nothing(role: str) -> None:
    assert not any(has_permission(role, p) for p in PERMISSIONS)


def test_an_unknown_permission_is_never_granted() -> None:
    assert not has_permission("admin", "everything")
