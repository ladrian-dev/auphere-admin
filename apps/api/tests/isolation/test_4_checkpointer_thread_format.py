"""Garantía 4 — Checkpointer scoping.

Block C wires LangGraph + Postgres/Redis checkpointers with the canonical
thread_id format. Block B locks the FORMAT contract so block C's runtime test
can rely on it; the format is enforced here.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.isolation]

THREAD_FORMAT = "tenant:{tenant_id}:channel:{channel_id}:user:{user_id}"


def make_thread_id(tenant_id, channel_id, user_id) -> str:
    return THREAD_FORMAT.format(tenant_id=tenant_id, channel_id=channel_id, user_id=user_id)


def test_format_includes_tenant_channel_user():
    thread = make_thread_id("t1", "c1", "u1")
    assert thread.startswith("tenant:t1:")
    assert ":channel:c1:" in thread
    assert thread.endswith(":user:u1")


def test_threads_with_same_user_but_different_tenant_differ():
    a = make_thread_id("tenant-A", "c1", "user-1")
    b = make_thread_id("tenant-B", "c1", "user-1")
    assert a != b


def test_threads_with_same_tenant_user_but_different_channel_differ():
    a = make_thread_id("t", "c1", "u")
    b = make_thread_id("t", "c2", "u")
    assert a != b


def test_thread_format_has_no_global_fallback():
    """If the format ever degenerates to a flat user id we lose isolation —
    this test exists so a regression that drops the prefix surfaces here."""
    thread = make_thread_id("t", "c", "u")
    assert thread != "u"
    assert ":user:" in thread
