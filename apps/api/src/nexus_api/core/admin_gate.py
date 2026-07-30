"""Admin-only agent gate — the single source of truth for "may this sender
talk to the agent?" and, once in, "with what permissions?".

Used so a non-admin sender on an admin-only agent gets NEITHER a reply NOR a
read receipt (important on a WhatsApp coexistence line, where a read receipt
sent by the Cloud API marks the message read in the human's WhatsApp Business
app):

- Worker dispatcher: skip the pipeline (``pipeline.skipped.not_admin``).
- Meta webhook: skip the read receipt so the message stays unread until a
  human opens the chat.

Per-admin roles (``full`` vs ``readonly``) let one whitelist hold a mix of
admins with different powers. The role gates WRITE tools at the worker: a
``readonly`` admin sees (and can dispatch) only non-side-effecting tools —
they can query debts but never register a payment, create an account, etc.
The whitelist itself (``admin_phones``) is unchanged: both roles are admins
for the "may this sender talk at all?" question.
"""

from __future__ import annotations

import re
from typing import Any

ROLE_FULL = "full"
ROLE_READONLY = "readonly"


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _phone_matches(sender: str | None, candidate: Any) -> bool:
    """Match two phones by trailing digits (up to 10) so ``+58424…``,
    ``0424…`` and formatted variants all match. Numbers shorter than 7 digits
    never match — too ambiguous to grant admin access on."""
    ds, dc = _digits(sender), _digits(candidate)
    if len(ds) < 7 or len(dc) < 7:
        return False
    n = min(len(ds), len(dc), 10)
    return ds[-n:] == dc[-n:]


def sender_is_admin(sender: str | None, admin_phones: list[Any]) -> bool:
    """True when ``sender`` matches one of the whitelisted admin phones."""
    return any(_phone_matches(sender, raw) for raw in admin_phones)


def admin_only_suppresses(policies: dict[str, Any] | None, sender: str | None) -> bool:
    """True when the active agent is ``admin_only`` and ``sender`` is NOT
    whitelisted — the inbound must be fully suppressed (no reply, no read
    receipt). Returns False for non-admin-only agents (normal behaviour)."""
    access = (policies or {}).get("admin_access") or {}
    if not (isinstance(access, dict) and access.get("admin_only")):
        return False
    return not sender_is_admin(sender, list(access.get("admin_phones") or []))


def sender_role(policies: dict[str, Any] | None, sender: str | None) -> str | None:
    """The admin role of ``sender`` for this agent, or ``None`` if not an admin.

    Resolution order:
    1. An explicit ``policies.admin_access.admins`` entry (``[{phone, role}]``)
       whose phone matches → its role (``readonly`` or, for anything else,
       ``full``).
    2. Otherwise, a match in ``admin_phones`` → ``full`` (back-compat: configs
       with no per-admin roles keep every admin at full access).
    3. No match → ``None``.

    The gate never invents a role for a non-admin, and an unknown/empty role
    string is treated as ``full`` (fail-open on POWER only for someone who is
    already a whitelisted admin — never for a non-admin).
    """
    access = (policies or {}).get("admin_access") or {}
    if not isinstance(access, dict):
        return None
    for entry in access.get("admins") or []:
        if isinstance(entry, dict) and _phone_matches(sender, entry.get("phone")):
            role = str(entry.get("role") or ROLE_FULL).strip().lower()
            return ROLE_READONLY if role == ROLE_READONLY else ROLE_FULL
    if sender_is_admin(sender, list(access.get("admin_phones") or [])):
        return ROLE_FULL
    return None


__all__ = [
    "ROLE_FULL",
    "ROLE_READONLY",
    "admin_only_suppresses",
    "sender_is_admin",
    "sender_role",
]
