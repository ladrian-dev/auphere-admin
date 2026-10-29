"""Spec 049, requirement 3 — the windows Meta allows on Instagram and Messenger."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nexus_api.services.meta_window import decide, person_window, private_reply_allowed

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def test_never_written_first_is_closed() -> None:
    d = decide(now=NOW, last_dm_at=None, actor_kind="agent")
    assert not d.allowed and d.reason == "window_closed"


def test_agent_within_24h_is_a_plain_response() -> None:
    d = decide(now=NOW, last_dm_at=NOW - timedelta(hours=23), actor_kind="agent")
    assert d.allowed and not d.human_agent


def test_agent_after_24h_is_refused_never_tagged() -> None:
    d = decide(now=NOW, last_dm_at=NOW - timedelta(hours=25), actor_kind="agent")
    assert not d.allowed and not d.human_agent


def test_person_after_24h_uses_the_human_agent_tag() -> None:
    d = decide(now=NOW, last_dm_at=NOW - timedelta(days=3), actor_kind="member")
    assert d.allowed and d.human_agent


def test_person_within_24h_needs_no_tag() -> None:
    d = decide(now=NOW, last_dm_at=NOW - timedelta(hours=2), actor_kind="member")
    assert d.allowed and not d.human_agent


def test_nobody_after_7_days() -> None:
    d = decide(now=NOW, last_dm_at=NOW - timedelta(days=7, minutes=1), actor_kind="member")
    assert not d.allowed


def test_unknown_actor_is_treated_as_automatic() -> None:
    assert not decide(now=NOW, last_dm_at=NOW - timedelta(days=2), actor_kind=None).allowed
    assert not decide(now=NOW, last_dm_at=NOW - timedelta(days=2), actor_kind="system").allowed


def test_private_reply_window() -> None:
    assert private_reply_allowed(now=NOW, comment_at=NOW - timedelta(days=6))
    assert not private_reply_allowed(now=NOW, comment_at=NOW - timedelta(days=8))


def test_inbox_window_per_channel() -> None:
    assert person_window("instagram") == timedelta(days=7)
    assert person_window("messenger") == timedelta(days=7)
    assert person_window("whatsapp") == timedelta(hours=24)
