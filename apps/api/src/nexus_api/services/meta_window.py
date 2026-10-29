"""Messaging windows of Instagram and Messenger — spec 049, requirement 3.

Meta's rules (Messenger Platform policy and Instagram Messaging, 2026-10):

- The person writes first. The business answers **within 24 hours** of the
  person's last message (``messaging_type=RESPONSE``).
- After 24 hours and **up to 7 days**, only a human may answer, with the
  ``HUMAN_AGENT`` tag. Using it without a person behind the message gets the
  permission revoked — so the tag is decided here from who wrote the message
  (``actor_kind``), never from anything the agent can set.
- A **private reply** to a comment goes once per comment, within 7 days of
  the comment.

The window is measured from ``conversations.last_inbound_at``, which on
these channels only a direct message moves (a comment does not open a DM
window).

Pure functions: the outbound dispatcher and the inbox share them, so the
inbox never offers a send the dispatcher would refuse.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

AGENT_WINDOW = timedelta(hours=24)
HUMAN_AGENT_WINDOW = timedelta(days=7)
PRIVATE_REPLY_WINDOW = timedelta(days=7)

#: ``messages.actor_kind`` values that mean a real person wrote the message.
PERSON_ACTORS = frozenset({"member", "operator", "owner"})

#: ``channels.type`` values these rules apply to.
META_SOCIAL_CHANNEL_TYPES = frozenset({"instagram", "messenger"})


@dataclass(frozen=True, slots=True)
class WindowDecision:
    allowed: bool
    human_agent: bool = False
    reason: str | None = None


def decide(*, now: datetime, last_dm_at: datetime | None, actor_kind: str | None) -> WindowDecision:
    """May a direct message go out now, and does it need the tag?"""
    if last_dm_at is None:
        return WindowDecision(allowed=False, reason="window_closed")
    elapsed = now - last_dm_at
    if elapsed < AGENT_WINDOW:
        return WindowDecision(allowed=True)
    if actor_kind in PERSON_ACTORS and elapsed < HUMAN_AGENT_WINDOW:
        return WindowDecision(allowed=True, human_agent=True)
    return WindowDecision(allowed=False, reason="window_closed")


def private_reply_allowed(*, now: datetime, comment_at: datetime) -> bool:
    return now - comment_at < PRIVATE_REPLY_WINDOW


def person_window(channel_type: str) -> timedelta:
    """How long after the person's last message a team member can still
    write — what the inbox uses to show the composer."""
    return HUMAN_AGENT_WINDOW if channel_type in META_SOCIAL_CHANNEL_TYPES else AGENT_WINDOW
