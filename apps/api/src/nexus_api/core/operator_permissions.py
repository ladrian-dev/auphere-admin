"""What each role of the operator panel may do (spec 079, requisito 1).

The panel (``apps/admin``) is Auphere's own team. Its three roles map to nine
permissions; every Server Action, page and route of the panel declares one of
them, and from spec 079's phase 2 every ``/admin/*`` route of this API will too.

This module is the authority. The panel keeps a copy in
``apps/admin/src/lib/permissions.ts`` to decide and to render, and its test reads
**this file** to fail on any drift — so keep ``OPERATOR_PERMISSIONS`` a plain
literal: one line per permission, roles as a tuple of string literals.

What each permission covers is in ``specs/079-panel-respeta-el-rol/inventario.md``.
The table was decided by Luis on 2026-11-25.
"""

from __future__ import annotations

from typing import Final

OPERATOR_PERMISSIONS: Final[dict[str, tuple[str, ...]]] = {
    "read": ("admin", "qa_operator", "viewer"),
    "qa": ("admin", "qa_operator"),
    "operate": ("admin", "qa_operator"),
    "money": ("admin",),
    "credentials": ("admin",),
    "impersonate": ("admin",),
    "people": ("admin",),
    "delete": ("admin",),
    "platform": ("admin",),
}


def has_permission(role: str, permission: str) -> bool:
    """``True`` only for a known permission granted to a known role."""
    return role in OPERATOR_PERMISSIONS.get(permission, ())
