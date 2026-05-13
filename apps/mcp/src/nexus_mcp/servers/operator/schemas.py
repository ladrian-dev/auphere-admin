"""Pydantic input/output for operator-server tools."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import Field

from nexus_mcp.base import InputModel, OutputModel


class ConsultOwnerInput(InputModel):
    conversation_id: uuid.UUID = Field(
        description=(
            "UUID of the current customer conversation. The owner's "
            "response will re-enter the pipeline on this conversation."
        ),
    )
    question: str = Field(
        min_length=4,
        max_length=1000,
        description=(
            "Concrete question to ask the tenant owner. Write in the "
            "tenant's natural language. Include enough detail that the "
            "owner can answer without seeing the rest of the conversation."
        ),
    )
    urgency: Literal["low", "normal", "high"] = Field(
        default="normal",
        description=(
            "How quickly the owner should answer. 'high' triggers a "
            "30-minute reminder/escalation SLA; 'normal' is 4h; 'low' is "
            "24h. Choose 'high' only when the customer is actively "
            "waiting and any delay damages the relationship."
        ),
    )
    expected_reply_kind: Literal["free_text", "yes_no", "action_done"] = Field(
        default="free_text",
        description=(
            "What shape of reply you expect. 'yes_no' for binary "
            "decisions (e.g. accept an exception); 'free_text' for open "
            "questions (e.g. ask for the price of a service); "
            "'action_done' when the owner is expected to perform an "
            "action and then confirm completion."
        ),
    )
    context_summary: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "Optional one-line summary of the customer conversation so "
            "the owner has context without needing to scroll the panel."
        ),
    )


class ConsultOwnerOutput(OutputModel):
    consultation_id: uuid.UUID
    correlation_id: str
    status: str
    ack_message_to_customer: str
