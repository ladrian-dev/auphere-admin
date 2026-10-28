from __future__ import annotations

import uuid
from typing import Literal

from pydantic import Field

from nexus_mcp.base import InputModel, OutputModel


class HandoffInput(InputModel):
    # Ni la conversación ni el cliente final: los pone el servidor (garantía 8).
    # El destino es uno de la lista de Recepción; cualquier otro se rechaza. Sin
    # docstring a propósito: iría al esquema que lee el modelo.

    to_agent_id: uuid.UUID = Field(
        description=(
            "The agent that takes the conversation: the id of one of the agents "
            "listed under «Derivar a otro agente» in your instructions. Any other "
            "agent is refused."
        ),
    )
    summary: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "For the agent that takes it, in one or two sentences: what the customer "
            "wants and what they already told you, so they are not asked again."
        ),
    )


class HandoffOutput(OutputModel):
    handed_off: bool
    outcome: Literal[
        "handed_off",
        "not_reception",
        "not_in_list",
        "same_agent",
        "target_unavailable",
        "loop",
    ]
    #: El nombre del destino, solo cuando la derivación se hizo.
    to_agent: str | None = None
    #: Cuántas derivaciones lleva la conversación.
    hop: int
    #: Qué hacer ahora, para el modelo.
    note: str
