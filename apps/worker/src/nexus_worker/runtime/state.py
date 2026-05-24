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
    # The channel medium this turn runs on — "whatsapp", "web", … (mirrors
    # ``ChannelType``). Carried so the ``ucm_formatter`` node degrades the
    # UCM for the right channel instead of assuming WhatsApp. The QA
    # Playground runs on a tenant's "web" channel; the production
    # dispatcher on "whatsapp". Optional (``total=False``): nodes fall
    # back to "whatsapp" when a caller omits it.
    channel_type: str
    user_id: str
    conversation_id: str
    customer_id: str
    inbound_message_id: str

    # Inbound payload
    user_message: str

    # ADR-018 fanout — when the turn is triggered by an owner response
    # (not a new customer message), the fanout passes a synthetic note
    # describing what the owner said. The classify + handler + respond
    # nodes prepend this to the system prompt so the agent can act on
    # the new information. None / empty on normal customer turns.
    system_addendum: str

    # Filled by classify
    intent: str
    route: str
    # The recent conversation turns as LLM ``messages``, loaded ONCE per
    # turn by ``classify`` and reused by the chosen handler. Before ADR-023
    # every node re-queried the DB (3x per turn); now it travels in state.
    history: list[dict[str, str]]

    # Filled by the chosen handler — replaces the previous turn's tool calls.
    # After ADR-023 this is the list of tool envelopes accumulated across
    # ALL iterations of the handler's ReAct loop, not a single round.
    tool_calls: list[dict[str, Any]]

    # Filled by the chosen handler (ADR-023). The handler's ReAct loop now
    # produces the final user-visible text directly — the old blind
    # ``respond`` node is gone.
    response: str
    response_model: str

    # Phase 2 (ADR-020): filled by ``ucm_formatter`` when
    # ``settings.use_ucm_formatter`` is True. ``ucm`` is the UCM v1.0.0
    # payload as a plain dict (already validated through the schema), and
    # ``ucm_shadow_diff`` is the comparison record between the channel-
    # degraded UCM and the legacy ``response`` text. Both stay ``None`` /
    # unset while the flag is off so existing code paths see no change.
    ucm: dict[str, Any]
    ucm_shadow_diff: dict[str, Any]

    # Fase C — outcome grader. ``outcome_overall`` is the final verdict
    # the pipeline acted on (``pass`` / ``fail`` / ``skipped`` /
    # ``error``); ``outcome_retries`` counts how many times the agent
    # was re-prompted before the grader passed (or before the pipeline
    # gave up); ``outcome_feedback`` is the LAST feedback string from
    # the grader (empty if the original draft passed). ``skipped`` is
    # used when the feature is off for this config — keeps Langfuse
    # traces self-describing.
    outcome_overall: str
    outcome_retries: int
    outcome_feedback: str

    # Per-config runtime flags forwarded by the handler so downstream
    # nodes (grade_outcome, ucm_formatter, checkpoint) can act on them
    # without re-querying the bundle. Populated from
    # ``AgentBundle.runtime_*`` by ``make_handler_node``.
    agent_runtime_flags: dict[str, bool]

    # Filled by the handler when the LLM calls ``response.send_interactive``.
    # Holds the validated tool args — body, optional header/footer, and
    # exactly one of buttons/list/cta_url. The ucm_formatter consumes it
    # to build the interactive UCM (composite-wrapped with the text reply
    # when ``response`` is also non-empty), and the checkpoint node
    # persists it on a second Message row so the outbound dispatcher can
    # route to ``adapter.send_interactive``. Empty / unset on turns that
    # produce plain text only.
    interactive_payload: dict[str, Any]

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
    system_addendum: str | None = None,
    channel_type: str = "whatsapp",
) -> AgentState:
    return {
        "tenant_id": str(tenant_id),
        "channel_id": str(channel_id),
        "channel_type": channel_type,
        "user_id": user_id,
        "conversation_id": str(conversation_id),
        "customer_id": str(customer_id),
        "inbound_message_id": str(inbound_message_id),
        "user_message": user_message,
        "system_addendum": system_addendum or "",
        "tool_calls": [],
        "meta": {},
    }
