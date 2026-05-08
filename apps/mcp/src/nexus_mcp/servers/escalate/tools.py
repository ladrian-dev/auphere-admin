"""escalate.escalate_to_human — flip the conversation to ``escalated`` and
record an audit_log row. The actual operator ping (WhatsApp / email) is
Block F's job; Block D persists the durable state.
"""

from __future__ import annotations

from nexus_api.db.models import Conversation, ConversationStatus
from nexus_api.repositories import AuditRepository

from nexus_mcp._db import tool_session
from nexus_mcp.base import InputModel, OutputModel, ToolBase, ToolError
from nexus_mcp.servers.escalate.schemas import (
    EscalateToHumanInput,
    EscalateToHumanOutput,
)


class EscalateToHuman(ToolBase):
    name = "escalate.escalate_to_human"
    description = (
        "Hand off the conversation to a human operator. Marks the conversation as "
        "escalated and records an audit entry. Use only when the assistant cannot "
        "satisfy the request and a human must take over."
    )
    input_model = EscalateToHumanInput
    output_model = EscalateToHumanOutput
    side_effects = ("mutates_db", "sends_message")

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, EscalateToHumanInput)
        async with tool_session() as session:
            conv = await session.get(Conversation, payload.conversation_id)
            if conv is None:
                # RLS would silently filter cross-tenant rows; either way the
                # tool refuses. ``IsolationViolation`` would be alarmist
                # (the LLM may simply have a stale conversation_id) so use a
                # plain ``ToolError``.
                raise ToolError(f"conversation {payload.conversation_id} not found for this tenant")

            before = {"status": conv.status.value}
            conv.status = ConversationStatus.ESCALATED
            await session.flush()
            after = {"status": conv.status.value}

            audit = AuditRepository(session)
            entry = await audit.record(
                actor="system:agent",
                action="conversation.escalated",
                target=str(conv.id),
                before=before,
                after={**after, "reason": payload.reason},
            )
            audit_id = entry.id

        return EscalateToHumanOutput(
            conversation_id=payload.conversation_id,
            audit_log_id=audit_id,
            status="operator_notified",
        )


ESCALATE_TOOLS: tuple[type[ToolBase], ...] = (EscalateToHuman,)
