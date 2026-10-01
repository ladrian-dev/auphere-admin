"""payments.request_review — the business team confirms or rejects a payment (spec 025).

Thin wrapper over ``nexus_api.services.payment_reviews.open_review``: it
loads the conversation, the business name and the reviewer list of the
active agent version, and lets the service record the review and queue the
notices. Everything it sends leaves from the business's own number as
pending outbound rows the dispatcher delivers and meters.
"""

from __future__ import annotations

from nexus_api.db.models import Conversation, Tenant
from nexus_api.repositories.agent_config import AgentConfigRepository
from nexus_api.services.agent_payment_review import reviewers_of
from nexus_api.services.payment_reviews import open_review

from nexus_mcp._db import tool_session
from nexus_mcp.base import InputModel, OutputModel, ToolBase, ToolError
from nexus_mcp.servers.payments.schemas import (
    RequestPaymentReviewInput,
    RequestPaymentReviewOutput,
)


class RequestPaymentReview(ToolBase):
    name = "payments.request_review"
    description = (
        "Ask the business team to confirm or reject a customer's payment. Sends, from "
        "the business number, the order summary and the customer's receipt to every "
        "payment reviewer with two buttons (Confirmar pago / Rechazar pago); when one of "
        "them taps, the customer is told the outcome automatically. Call it when the "
        "customer sends a bank-transfer receipt (method='transfer'), or when they say they "
        "paid through the store link (method='link', after finding their order with "
        "woocommerce.list_orders). Fill the summary with what was agreed in the chat. "
        "Then reply to the customer with `message_to_customer` and never confirm the "
        "payment yourself. If `notified` is 0, nobody could be reached: hand the "
        "conversation to a person with escalate.escalate_to_human."
    )
    input_model = RequestPaymentReviewInput
    output_model = RequestPaymentReviewOutput
    side_effects = ("mutates_db", "sends_message")

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, RequestPaymentReviewInput)
        async with tool_session() as session:
            conv = await session.get(Conversation, payload.conversation_id)
            if conv is None:
                raise ToolError(f"conversation {payload.conversation_id} not found for this tenant")
            active = await AgentConfigRepository(session).get_active()
            reviewers = reviewers_of(active.policies if active is not None else None)
            if not reviewers:
                raise ToolError(
                    "this business has no payment reviewers configured — use "
                    "escalate.escalate_to_human so a person checks the payment"
                )
            tenant = await session.get(Tenant, conv.tenant_id)
            opened = await open_review(
                session,
                conversation=conv,
                reviewers=reviewers,
                business=tenant.name if tenant is not None else "",
                method=payload.method,
                summary=payload.model_dump(
                    include={
                        "product",
                        "modality",
                        "place",
                        "date",
                        "slot",
                        "total",
                        "customer_name",
                    }
                ),
                order_id=payload.order_id if payload.method == "link" else None,
                order_status=payload.order_status if payload.method == "link" else None,
            )
            status = "informed" if opened.review.status == "informed" else "pending"
            return RequestPaymentReviewOutput(
                review_id=opened.review.id,
                status=status,
                notified=opened.notified,
                unreachable=opened.unreachable,
                already_pending=opened.already_pending,
                message_to_customer=opened.message_to_customer,
            )


PAYMENTS_TOOLS: tuple[type[ToolBase], ...] = (RequestPaymentReview,)
