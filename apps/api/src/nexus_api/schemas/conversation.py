from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    channel_id: uuid.UUID
    customer_id: uuid.UUID
    status: str
    agent_active: bool
    agent_active_version: int = 0
    takeover_context: dict[str, Any] | None = None
    # Transport provider of the conversation's channel ("meta").
    # Populated by the endpoint from a channel lookup, not stored on the
    # Conversation row — lets the operator panel badge each thread and stop
    # assuming a provider. NULL only if the channel row
    # vanished (orphan conversation).
    provider: str | None = None
    created_at: datetime
    updated_at: datetime


class ConversationAgentToggleIn(BaseModel):
    """Block M.3 / Bloque C — body for PATCH .../conversations/:id/agent.

    ``reason`` and ``notes`` are populated when the operator pauses the
    agent (``agent_active=false``); they survive into
    ``conversations.takeover_context`` and the dispatcher consumes them
    on the first turn after the agent is reactivated to brief the LLM
    about what happened during the human-in-the-loop window. Both are
    optional — a paused conversation with no reason still works.
    """

    model_config = ConfigDict(extra="forbid")

    agent_active: bool
    reason: str | None = None
    notes: str | None = None


class ConversationPageOut(BaseModel):
    items: list[ConversationOut]
    next_cursor: str | None


class OperatorSendIn(BaseModel):
    """Bloque C — body for ``POST .../conversations/:id/send``.

    The operator sends free-form text on a paused conversation. The
    endpoint persists an outbound ``Message`` with ``actor_kind='operator'``;
    the existing outbound dispatcher picks it up on its next tick and
    routes through the channel adapter exactly like an agent reply.
    Interactive components (buttons / list / cta_url) are NOT in scope
    for this initial cut — the operator types text.
    """

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4096)


class MessageOut(BaseModel):
    """Full per-message record exposed to the admin operator panel.

    Block N expanded this from 11 fields to the full set the panel needs
    to render a class-world conversation view: delivery tracking,
    media + interactive previews, reactions, quoted replies, the
    outcome-grader verdict for the turn, and provider correlation ids
    for debugging. Every new field is optional — back-compat with rows
    written before the respective migration (e.g. ``interactive_payload``
    arrived in 0036, ``outcome_*`` in 0037).
    """

    model_config = ConfigDict(from_attributes=True)

    # Identity + ordering
    id: uuid.UUID
    conversation_id: uuid.UUID
    created_at: datetime

    # Core content
    direction: str
    content: str
    intent: str | None

    # LLM telemetry
    cost_usd: float | None
    latency_ms: int | None
    model: str | None
    trace_id: str | None
    tool_calls: list[dict[str, Any]]

    # Delivery lifecycle (B5 — operator can see "did this go out?")
    status: str
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    failed_at: datetime | None = None
    failure_code: str | None = None
    last_error: str | None = None
    attempts: int = 0
    provider_message_id: str | None = None
    pricing_category: str | None = None

    # Media (B1 — operator sees the file the agent sent)
    media_kind: str | None = None
    media_mime: str | None = None
    media_filename: str | None = None
    media_size_bytes: int | None = None
    media_transcript: str | None = None

    # Reactions + quoted reply (B1)
    reaction_emoji: str | None = None
    reaction_target_wamid: str | None = None
    context_message_id: str | None = None

    # Interactive component payload (B1 — the headline feature)
    interactive_payload: dict[str, Any] | None = None

    # Outcome grader verdict for the turn (B3)
    outcome_overall: str | None = None
    outcome_retries: int | None = None
    outcome_feedback: str | None = None

    # Actor identity (Bloque C — migration 0041). NULL on inbound and on
    # rows written before the migration. Outbound rows carry one of
    # ``agent`` / ``operator`` / ``owner`` / ``system``; ``operator``
    # rows additionally populate ``actor_id`` with the admin uuid.
    actor_kind: str | None = None
    actor_id: uuid.UUID | None = None
