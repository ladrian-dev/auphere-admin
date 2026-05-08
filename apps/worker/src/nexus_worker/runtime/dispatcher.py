"""Inbound event dispatcher.

The Redis Stream consumer hands an ``InboundEvent`` to ``process_inbound``;
this module owns the per-turn lifecycle:

1. Open a tenant-scoped session, upsert customer + conversation, persist
   the inbound message row. Close the session before invoking the pipeline
   so we don't hold a transaction open across LLM calls.
2. Build the LangGraph state and the canonical ``thread_id``.
3. Invoke the compiled pipeline. The pipeline's ``checkpoint`` node writes
   the outbound row in its own short transaction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker

from nexus_worker.persistence.messages import (
    persist_inbound_message,
    upsert_conversation_for_customer,
)
from nexus_worker.persistence.messages import upsert_customer as _upsert_customer
from nexus_worker.runtime.state import new_state
from nexus_worker.runtime.thread_id import make_thread_id

log = structlog.get_logger(__name__)


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
    async with sm() as session, tenant_scoped_session(session, event.tenant_id):
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
    final = await pipeline.ainvoke(state, config=config)
    log.info(
        "pipeline.run.done",
        tenant_id=str(event.tenant_id),
        intent=final.get("intent"),
        response_present=bool(final.get("response")),
    )
    return dict(final)
