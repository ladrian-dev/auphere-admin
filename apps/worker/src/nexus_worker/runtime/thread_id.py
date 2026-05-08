"""Canonical LangGraph ``thread_id`` format.

Garantía 4 of architecture/agent-isolation.md mandates that the checkpointer
key is composed of ``tenant_id``, ``channel_id`` and ``user_id`` with no global
fallback. The format is locked in tests/isolation/test_4_checkpointer_thread_format.py
and reused here so a regression surfaces in CI.
"""

from __future__ import annotations

import uuid

THREAD_FORMAT = "tenant:{tenant_id}:channel:{channel_id}:user:{user_id}"


def make_thread_id(
    tenant_id: uuid.UUID | str,
    channel_id: uuid.UUID | str,
    user_id: str,
) -> str:
    if not user_id:
        raise ValueError("user_id must be non-empty (no global thread fallback)")
    return THREAD_FORMAT.format(
        tenant_id=str(tenant_id),
        channel_id=str(channel_id),
        user_id=user_id,
    )
