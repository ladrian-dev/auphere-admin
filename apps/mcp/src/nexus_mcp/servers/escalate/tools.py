"""escalate.escalate_to_human — flip the conversation to ``escalated`` and
record an audit_log row.

ADR-018 reframes "escalation" as the **last-resort** path: the agent
should normally call ``operator.consult_owner`` for HITL, which asks the
tenant owner asynchronously and re-enters the pipeline with the answer.
``escalate_to_human`` is reserved for the cases where the owner channel
itself is unavailable (``backchannel_enabled=false`` or no owner phone
registered), where Lee (the Auphere operator) takes over manually.

The tool keeps its name + registry slot so existing seeds and the
catalog stay untouched. Internally, when the tenant has the backchannel
enabled, it ALSO opens an ``owner_consultations`` row with
``urgency='high'`` so the owner is paged immediately — flipping the
conversation status is for the operator panel; the page is for the owner.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nexus_api.db.models import Conversation, ConversationStatus, Tenant
from nexus_api.repositories import (
    AuditRepository,
    OwnerConsultationRepository,
    OwnerPhoneIndexRepository,
)

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
        "satisfy the request and a human must take over. Prefer "
        "operator.consult_owner whenever the question is something the tenant "
        "owner can resolve in WhatsApp — escalation is the last resort."
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

            # ADR-018: when the tenant has the owner backchannel enabled
            # AND has a registered owner phone AND has headroom under the
            # rate cap, ALSO open an ``owner_consultations`` row with
            # ``urgency='high'`` so the owner sees the page in WhatsApp
            # without waiting for Lee to intervene. The conversation
            # remains ``escalated`` in the panel so Lee can still take
            # over if the owner doesn't answer.
            tenant = await session.get(Tenant, conv.tenant_id)
            if tenant is not None and tenant.backchannel_enabled:
                phone_repo = OwnerPhoneIndexRepository(session)
                owner_phone = await phone_repo.get_phone_for_tenant(tenant.id)
                if owner_phone:
                    consult_repo = OwnerConsultationRepository(session)
                    cap = tenant.backchannel_max_consultations_per_hour
                    since = datetime.now(UTC) - timedelta(hours=1)
                    recent = await consult_repo.count_in_window(since=since)
                    if recent < cap:
                        question = payload.reason
                        if payload.customer_summary:
                            question = f"{payload.reason}\n\nContexto: {payload.customer_summary}"
                        await consult_repo.create(
                            conversation_id=conv.id,
                            question_text=question[:1000],
                            urgency="high",
                            expected_reply_kind="free_text",
                            template_name="auphere_owner_consult",
                            template_params={
                                "tenant_name": tenant.name,
                                "question": payload.reason,
                                "urgency": "high",
                            },
                            context_summary=payload.customer_summary,
                            created_by="agent:escalate",
                        )

        return EscalateToHumanOutput(
            conversation_id=payload.conversation_id,
            audit_log_id=audit_id,
            status="operator_notified",
        )


ESCALATE_TOOLS: tuple[type[ToolBase], ...] = (EscalateToHuman,)
