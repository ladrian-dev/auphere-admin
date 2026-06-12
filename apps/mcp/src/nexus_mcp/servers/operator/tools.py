"""operator.consult_owner — entry point for the owner-backchannel HITL flow.

Behaviour (spec ``architecture/owner-backchannel.md`` §4):

1. Refuse if the tenant has ``backchannel_enabled=false``. The agent
   should pick ``escalate.escalate_to_human`` as the documented fallback.
2. Refuse if the tenant has no owner phone registered in
   ``owner_phone_index``. Without a recipient there is nothing to send —
   we surface the error so the agent does not lie to the customer.
3. Refuse if the tenant has hit the per-hour rate cap. A runaway agent
   loop must not spam the owner — fall back to ``escalate.escalate_to_human``.
4. Insert a ``pending`` row in ``owner_consultations`` with a fresh
   ``correlation_id``. The outbox dispatcher (worker loop) will pick it
   up and send the WhatsApp template asynchronously — this tool never
   waits for the template to be delivered.
5. Mark the conversation ``awaiting_owner_response`` so the next inbound
   from the same customer knows there's a question in flight.
6. Return an ack message the agent should send to the customer
   immediately. The agent's prompt instructs it never to mention the
   word "owner" or "backchannel" — the ack is a plain "let me check and
   I'll confirm shortly".

The tool is **generic** — nothing here is barbershop-specific. Any tenant
with ``backchannel_enabled=true`` and a registered owner phone can use
it; the spec on what to ask lives in the tenant's seed prompt, not in
this code.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nexus_api.db.models import Conversation, Tenant
from nexus_api.repositories import OwnerConsultationRepository, OwnerPhoneIndexRepository

from nexus_mcp._db import tool_session
from nexus_mcp.base import InputModel, OutputModel, ToolBase, ToolError
from nexus_mcp.servers.operator.schemas import (
    ConsultOwnerInput,
    ConsultOwnerOutput,
)

# Default ack — generic and friendly. Tenants can override by adjusting
# the agent's system prompt; the spec mandates the agent never says
# "owner" or references the backchannel.
_DEFAULT_ACK = "Déjame consultar para confirmarte y te aviso por acá apenas tenga la respuesta. 🙏"


def _pick_template(expected_reply_kind: str) -> str:
    """Map ``expected_reply_kind`` to a WhatsApp template name.

    Template names match the strings already submitted to Meta for
    approval on the Auphere WABA (see ADR-018).
    """
    if expected_reply_kind == "action_done":
        return "auphere_owner_action_request"
    # both ``yes_no`` and ``free_text`` share the same template body —
    # only the prompt to the owner changes wording downstream.
    return "auphere_owner_consult"


class ConsultOwner(ToolBase):
    name = "operator.consult_owner"
    description = (
        "Ask the tenant owner a question via the Auphere ↔ Owner WhatsApp "
        "backchannel. Use whenever the answer is not in your system prompt "
        "AND the customer is waiting on something only the owner can "
        "confirm (a custom price, an out-of-policy schedule change, a "
        "service the catalog doesn't list, etc.). The owner replies "
        "asynchronously; the pipeline re-enters on this conversation when "
        "the response arrives. You MUST reply to the customer with the "
        "returned ``ack_message_to_customer`` (or your own equivalent) "
        "immediately — never wait for the owner. NEVER mention the words "
        "'owner', 'consultar al equipo' is fine but do not describe the "
        "backchannel to the customer."
    )
    input_model = ConsultOwnerInput
    output_model = ConsultOwnerOutput
    side_effects = ("mutates_db", "sends_message", "async_reply")

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, ConsultOwnerInput)
        async with tool_session() as session:
            conv = await session.get(Conversation, payload.conversation_id)
            if conv is None:
                raise ToolError(f"conversation {payload.conversation_id} not found for this tenant")

            tenant = await session.get(Tenant, conv.tenant_id)
            if tenant is None:  # pragma: no cover — FK guarantees presence
                raise ToolError("tenant row missing for active conversation")
            if not tenant.backchannel_enabled:
                raise ToolError(
                    "owner backchannel disabled for this tenant — "
                    "use escalate.escalate_to_human instead"
                )

            phone_repo = OwnerPhoneIndexRepository(session)
            owner_phone = await phone_repo.get_phone_for_tenant(tenant.id)
            if not owner_phone:
                raise ToolError(
                    "tenant has no owner phone registered in owner_phone_index — "
                    "use escalate.escalate_to_human instead"
                )

            consult_repo = OwnerConsultationRepository(session)
            cap = tenant.backchannel_max_consultations_per_hour
            since = datetime.now(UTC) - timedelta(hours=1)
            recent = await consult_repo.count_in_window(since=since)
            if recent >= cap:
                raise ToolError(
                    f"owner consultation rate cap reached ({cap}/hour) — "
                    "use escalate.escalate_to_human"
                )

            template_name = _pick_template(payload.expected_reply_kind)
            template_params = {
                "tenant_name": tenant.name,
                "question": payload.question,
                "urgency": payload.urgency,
                # ``correlation_id`` is added below once known so the
                # template body can carry the ref the owner will quote.
            }
            row = await consult_repo.create(
                conversation_id=conv.id,
                question_text=payload.question,
                urgency=payload.urgency,
                expected_reply_kind=payload.expected_reply_kind,
                template_name=template_name,
                template_params=template_params,
                context_summary=payload.context_summary,
                created_by="agent",
            )
            row.template_params_json = {
                **template_params,
                "correlation_id": row.correlation_id,
            }

            conv.awaiting_owner_response = True
            conv.awaiting_owner_correlation_id = row.correlation_id

            consultation_id = row.id
            correlation_id = row.correlation_id

        return ConsultOwnerOutput(
            consultation_id=consultation_id,
            correlation_id=correlation_id,
            status="queued",
            ack_message_to_customer=_DEFAULT_ACK,
        )


OPERATOR_TOOLS: tuple[type[ToolBase], ...] = (ConsultOwner,)
