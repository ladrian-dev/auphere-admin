from __future__ import annotations

import uuid

from pydantic import Field

from nexus_mcp.base import InputModel, OutputModel


class EscalateToHumanInput(InputModel):
    conversation_id: uuid.UUID = Field(
        description="UUID of the live conversation to escalate.",
    )
    reason: str = Field(
        min_length=1,
        max_length=500,
        description="Short justification for the operator (why the agent gave up).",
    )
    customer_summary: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional brief summary of the conversation so far.",
    )


class EscalateToHumanOutput(OutputModel):
    conversation_id: uuid.UUID
    audit_log_id: uuid.UUID
    status: str
