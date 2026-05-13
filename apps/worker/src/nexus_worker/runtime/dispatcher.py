"""Inbound event dispatcher.

The Redis Stream consumer hands an ``InboundEvent`` to ``process_inbound``;
this module owns the per-turn lifecycle:

1. Open a tenant-scoped session, upsert customer + conversation, persist
   the inbound message row. Close the session before invoking the pipeline
   so we don't hold a transaction open across LLM calls.
2. Verify the tenant is ACTIVE. PAUSED / ARCHIVED tenants persist the
   inbound for audit but the pipeline is skipped — no outbound is
   generated until the operator resumes the tenant.
3. Build the LangGraph state and the canonical ``thread_id``.
4. Invoke the compiled pipeline. The pipeline's ``checkpoint`` node writes
   the outbound row in its own short transaction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Tenant, TenantStatus

from nexus_worker.observability.tracing import trace_turn, update_trace
from nexus_worker.persistence.messages import (
    persist_inbound_message,
    upsert_conversation_for_customer,
)
from nexus_worker.persistence.messages import upsert_customer as _upsert_customer
from nexus_worker.runtime.state import new_state
from nexus_worker.runtime.thread_id import make_thread_id

log = structlog.get_logger(__name__)

# Tenant statuses where the agent is muted — the inbound message is
# persisted for audit but the pipeline does NOT run. PAUSED is reversible
# (operator clicks Resume); ARCHIVED is one-way (soft delete).
_INACTIVE_STATUSES: frozenset[TenantStatus] = frozenset(
    {TenantStatus.PAUSED, TenantStatus.ARCHIVED}
)


@dataclass(frozen=True)
class InboundEvent:
    tenant_id: uuid.UUID
    channel_id: uuid.UUID
    user_id: str  # external identifier (phone number, etc.)
    content: str
    customer_name: str | None = None
    provider: str = "ycloud"


async def process_inbound(
    event: InboundEvent,
    *,
    pipeline: Any,
) -> dict[str, Any]:
    sm = get_sessionmaker()

    # Phase 1: persist inbound side. Short transaction, then close.
    # The tenant.status lookup uses the same scoped session — Tenant is the
    # one entity that doesn't carry tenant_id (it IS the tenant), so RLS on
    # tenants is global; reading it inside the scoped session keeps the
    # transaction count to one.
    async with sm() as session, tenant_scoped_session(session, event.tenant_id):
        tenant_status_raw = (
            await session.execute(sa.select(Tenant.status).where(Tenant.id == event.tenant_id))
        ).scalar_one_or_none()
        if tenant_status_raw is None:
            log.warning(
                "pipeline.skipped.tenant_unknown",
                tenant_id=str(event.tenant_id),
            )
            return {"skipped": "tenant_unknown"}

        customer = await _upsert_customer(
            session, identifier=event.user_id, name=event.customer_name
        )
        conversation = await upsert_conversation_for_customer(
            session, channel_id=event.channel_id, customer_id=customer.id
        )
        inbound_msg = await persist_inbound_message(
            session, conversation_id=conversation.id, content=event.content
        )
        customer_id = customer.id
        conversation_id = conversation.id
        inbound_id = inbound_msg.id
        conversation_agent_active = conversation.agent_active

    tenant_status = TenantStatus(tenant_status_raw)
    if tenant_status in _INACTIVE_STATUSES:
        # Inbound is captured, agent is muted. The operator panel surfaces
        # the message in the conversation view; resuming the tenant does NOT
        # auto-reply to backlog (next turn only). This matches the
        # consumer-side ack semantics: we still ack the Redis entry.
        log.info(
            "pipeline.skipped.tenant_inactive",
            tenant_id=str(event.tenant_id),
            tenant_status=tenant_status.value,
            conversation_id=str(conversation_id),
            inbound_message_id=str(inbound_id),
        )
        return {
            "skipped": "tenant_inactive",
            "tenant_status": tenant_status.value,
            "conversation_id": str(conversation_id),
            "inbound_message_id": str(inbound_id),
        }

    if not conversation_agent_active:
        # M.3 — operator has taken control of this thread. The inbound
        # is captured but the agent stays muted until the operator
        # reactivates via PATCH .../conversations/:id. No backlog
        # auto-reply on resume: next inbound only.
        log.info(
            "pipeline.skipped.human_takeover",
            tenant_id=str(event.tenant_id),
            conversation_id=str(conversation_id),
            inbound_message_id=str(inbound_id),
        )
        return {
            "skipped": "human_takeover",
            "conversation_id": str(conversation_id),
            "inbound_message_id": str(inbound_id),
        }

    state = new_state(
        tenant_id=event.tenant_id,
        channel_id=event.channel_id,
        user_id=event.user_id,
        conversation_id=conversation_id,
        customer_id=customer_id,
        inbound_message_id=inbound_id,
        user_message=event.content,
    )
    thread_id = make_thread_id(event.tenant_id, event.channel_id, event.user_id)
    config = {"configurable": {"thread_id": thread_id}}

    log.info(
        "pipeline.run.start",
        tenant_id=str(event.tenant_id),
        channel_id=str(event.channel_id),
        user_id=event.user_id,
        thread_id=thread_id,
    )
    with trace_turn(
        tenant_id=event.tenant_id,
        channel_id=event.channel_id,
        user_id_inside_channel=event.user_id,
        name="agent.turn",
        metadata={"thread_id": thread_id, "provider": event.provider},
    ):
        final = await pipeline.ainvoke(state, config=config)
        update_trace(
            output={
                "intent": final.get("intent"),
                "response_present": bool(final.get("response")),
                "tool_calls": [
                    {"tool": c.get("tool"), "status": c.get("status")}
                    for c in (final.get("tool_calls") or [])
                ],
            }
        )
    log.info(
        "pipeline.run.done",
        tenant_id=str(event.tenant_id),
        intent=final.get("intent"),
        response_present=bool(final.get("response")),
    )
    return dict(final)
