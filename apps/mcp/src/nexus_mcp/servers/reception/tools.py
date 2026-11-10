"""reception.handoff — Recepción pasa la conversación a otro agente del cliente
(spec 047, requisito 53; ``nexus_api.services.reception``).

Tres ejes de aislamiento, como el resto de herramientas de cara al cliente final:

- **el negocio**, por la RLS (``tool_session``): un agente de otro cliente no
  existe y se rechaza igual que uno que no está en la lista;
- **la persona**, por el turno (``current_customer_or_refuse``): la conversación
  es la de la persona del turno, nunca un argumento del modelo;
- **el agente**, por la conversación (``agent_for_conversation``): quien deriva es
  el agente que contesta en ella, y solo a los destinos de **su** versión
  publicada (garantía 9).

Una negativa no es un error: el modelo la lee y sigue (se queda la conversación
o la pasa a una persona). Solo la quinta derivación de una conversación la pasa a
una persona sin preguntar (``reception_loop``).
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import Conversation
from nexus_api.services import inbox_lifecycle
from nexus_api.services.inbox_stream import publish_inbox_event
from nexus_api.services.reception import (
    HANDOFF_TOOL,
    Outcome,
    agent_for_conversation,
    hand_off,
)
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_mcp._customer import current_customer_or_refuse
from nexus_mcp._db import tool_session
from nexus_mcp.base import InputModel, OutputModel, ToolBase, ToolError
from nexus_mcp.servers.reception.schemas import HandoffInput, HandoffOutput

log = structlog.get_logger(__name__)

#: Qué hace el modelo después de cada resultado.
NOTES: dict[Outcome, str] = {
    "handed_off": (
        "Done. The other agent answers the customer now, in this same chat: do not "
        "answer the request yourself and do not call more tools."
    ),
    "not_reception": "You cannot hand conversations over. Keep helping the customer yourself.",
    "not_in_list": (
        "That agent is not one you can hand over to. Use only the agents listed in "
        "your instructions, or keep the conversation."
    ),
    "same_agent": "That is you. Keep helping the customer yourself.",
    "target_unavailable": (
        "That agent is not available right now (paused or not published). Do not "
        "hand over: help the customer yourself if you can, or hand the conversation "
        "to a person of the team."
    ),
    "loop": (
        "This conversation has gone back and forth between agents too many times: a "
        "person of the team takes it now. Tell the customer so, kindly, and do not "
        "hand it over again."
    ),
}


async def _turn_conversation(session: AsyncSession, customer_id: uuid.UUID) -> Conversation | None:
    """La conversación de la persona del turno: la de su último mensaje."""
    found: Conversation | None = await session.scalar(
        sa.select(Conversation)
        .where(Conversation.customer_id == customer_id)
        .order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.id.desc())
        .limit(1)
    )
    return found


class ReceptionHandoff(ToolBase):
    name = HANDOFF_TOOL
    description = (
        "Hand this conversation over to another agent of this business, one of the "
        "agents listed in your instructions, when what the customer asks is theirs. "
        "Same chat and same number: the other agent answers right away with its own "
        "instructions and tools. Give a short summary so the customer is not asked "
        "again. If the result says it was not handed over, keep the conversation or "
        "hand it to a person."
    )
    input_model = HandoffInput
    output_model = HandoffOutput
    side_effects = ("mutates_db",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, HandoffInput)
        customer_id = current_customer_or_refuse("pasar la conversación a otro agente")
        tenant_id = require_current_tenant()
        async with tool_session() as session:
            conv = await _turn_conversation(session, customer_id)
            if conv is None:
                raise ToolError("there is no conversation with this customer to hand over")
            caller = await agent_for_conversation(session, conv)
            result = await hand_off(
                session,
                conv,
                from_agent_id=caller,
                to_agent_id=payload.to_agent_id,
                summary=payload.summary,
            )
            conversation_id = conv.id
        # Confirmado: ahora el registro, la Bandeja y, si pasó a una persona, sus avisos.
        if result.handed_off:
            log.info(
                "reception.handoff",
                tenant_id=str(tenant_id),
                agent_id=str(result.from_agent_id),
                conversation_id=str(conversation_id),
                from_agent_id=str(result.from_agent_id),
                to_agent_id=str(result.to_agent_id),
                hop=result.hop,
            )
            await publish_inbox_event(
                None,
                tenant_id=tenant_id,
                event="conversation.updated",
                conversation_id=conversation_id,
            )
        if result.mark is not None:
            await inbox_lifecycle.announce_waiting(result.mark)
        return HandoffOutput(
            handed_off=result.handed_off,
            outcome=result.outcome,
            to_agent=result.to_agent_name,
            hop=result.hop,
            note=NOTES[result.outcome],
        )


RECEPTION_TOOLS: tuple[type[ToolBase], ...] = (ReceptionHandoff,)
