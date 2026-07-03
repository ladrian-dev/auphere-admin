"""Admin-only agent gate — the single source of truth for "may this sender
talk to the agent?".

Used in two places so a non-admin sender on an admin-only agent gets NEITHER
a reply NOR a read receipt (important on a WhatsApp coexistence line, where a
read receipt sent by the Cloud API marks the message read in the human's
WhatsApp Business app):

- Worker dispatcher: skip the pipeline (``pipeline.skipped.not_admin``).
- Meta webhook: skip the read receipt so the message stays unread until a
  human opens the chat.
"""

from __future__ import annotations

import re
from typing import Any


def sender_is_admin(sender: str | None, admin_phones: list[Any]) -> bool:
    """True when ``sender`` matches one of the whitelisted admin phones.

    Compared by trailing digits (up to 10) so ``+58424…``, ``0424…`` and
    formatted variants all match. Numbers shorter than 7 digits never match —
    too ambiguous to grant admin access on.
    """
    ds = re.sub(r"\D", "", sender or "")
    if len(ds) < 7:
        return False
    for raw in admin_phones:
        da = re.sub(r"\D", "", str(raw or ""))
        if len(da) < 7:
            continue
        n = min(len(ds), len(da), 10)
        if ds[-n:] == da[-n:]:
            return True
    return False


def admin_only_suppresses(policies: dict[str, Any] | None, sender: str | None) -> bool:
    """True when the active agent is ``admin_only`` and ``sender`` is NOT
    whitelisted — the inbound must be fully suppressed (no reply, no read
    receipt). Returns False for non-admin-only agents (normal behaviour)."""
    access = (policies or {}).get("admin_access") or {}
    if not (isinstance(access, dict) and access.get("admin_only")):
        return False
    return not sender_is_admin(sender, list(access.get("admin_phones") or []))


__all__ = ["admin_only_suppresses", "sender_is_admin"]
