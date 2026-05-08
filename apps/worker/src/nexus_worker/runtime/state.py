"""LangGraph state for the agent pipeline.

All fields are replace-on-write — the LangGraph default. Each turn dispatches
exactly one handler so ``tool_calls`` does not need an additive reducer; if
we used one, the previous turn's entries would carry over via the
checkpointer-restored state and the handler would *append* on top of them.

Identity fields (``tenant_id`` etc.) are duplicated into the state so traces
are self-describing; the source of truth for repo/tool dispatch is still
``nexus_api.core.tenant_context`` (set by the consumer before the run).
"""

from __future__ import annotations

import uuid
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # Identity (set at entry, never mutated by nodes)
    tenant_id: str
    channel_id: str
    user_id: str
    conversation_id: str
    customer_id: str
    inbound_message_id: str

    # Inbound payload
    user_message: str

    # Filled by classify
    intent: str
    route: str

    # Filled by the chosen handler — replaces the previous turn's tool calls.
    tool_calls: list[dict[str, Any]]

    # Filled by respond
    response: str
    response_model: str

    # Free-form trace metadata (replaced by the last writer)
    meta: dict[str, Any]


def new_state(
    *,
    tenant_id: uuid.UUID,
    channel_id: uuid.UUID,
    user_id: str,
    conversation_id: uuid.UUID,
    customer_id: uuid.UUID,
    inbound_message_id: uuid.UUID,
    user_message: str,
) -> AgentState:
    return {
        "tenant_id": str(tenant_id),
        "channel_id": str(channel_id),
        "user_id": user_id,
        "conversation_id": str(conversation_id),
        "customer_id": str(customer_id),
        "inbound_message_id": str(inbound_message_id),
        "user_message": user_message,
        "tool_calls": [],
        "meta": {},
    }
