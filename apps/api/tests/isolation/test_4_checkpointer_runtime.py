"""Garantía 4 — Checkpointer scoping (RUNTIME).

Two tenants, the same external ``user_id``, different ``channel_id``s. After
running one turn for each through the same compiled pipeline (sharing one
``MemorySaver``), the checkpoints must:

- Live under different ``thread_id`` keys.
- Carry the right ``tenant_id`` in their persisted state.
- Not share any conversation history.

Together with ``test_4_checkpointer_thread_format.py`` (format contract) this
locks both the format and the runtime behaviour for garantía 4.
"""

from __future__ import annotations

import pytest
from nexus_worker.runtime.state import new_state
from nexus_worker.runtime.thread_id import make_thread_id

from .conftest import make_pipeline, seed_active_agent_config, seed_channel

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


SHARED_USER = "+56-shared-number"


async def test_same_user_different_tenants_get_distinct_threads(
    db_session,
    tenants_ab,
    agent_loader,
    in_memory_provider,
    llm_router,
    memory_saver,
):
    a, b = tenants_ab["a"], tenants_ab["b"]
    await seed_active_agent_config(
        db_session, tenant_id=a, system_prompt="A's prompt", tools=["client.get_history"]
    )
    await seed_active_agent_config(
        db_session, tenant_id=b, system_prompt="B's prompt", tools=["client.get_history"]
    )
    ch_a = await seed_channel(db_session, tenant_id=a, provider_identifier="iso4-a")
    ch_b = await seed_channel(db_session, tenant_id=b, provider_identifier="iso4-b")

    in_memory_provider.responder = lambda c: (
        "info" if c.role == "classify" else f"hello from {c.tenant_id}"
    )

    pipeline = make_pipeline(
        agent_loader=agent_loader,
        llm_router=llm_router,
        checkpointer=memory_saver,
    )

    async def run_for(tenant_id, channel, message):
        from nexus_api.db.models import (
            Conversation,
            ConversationStatus,
            Customer,
            Message,
            MessageDirection,
        )

        cust = Customer(tenant_id=tenant_id, identifier=SHARED_USER, preferences={})
        db_session.add(cust)
        await db_session.commit()
        await db_session.refresh(cust)
        conv = Conversation(
            tenant_id=tenant_id,
            channel_id=channel.id,
            customer_id=cust.id,
            status=ConversationStatus.OPEN,
        )
        db_session.add(conv)
        await db_session.commit()
        await db_session.refresh(conv)
        inbound = Message(
            tenant_id=tenant_id,
            conversation_id=conv.id,
            direction=MessageDirection.INBOUND,
            content=message,
            tool_calls=[],
        )
        db_session.add(inbound)
        await db_session.commit()
        await db_session.refresh(inbound)
        state = new_state(
            tenant_id=tenant_id,
            channel_id=channel.id,
            user_id=SHARED_USER,
            conversation_id=conv.id,
            customer_id=cust.id,
            inbound_message_id=inbound.id,
            user_message=message,
        )
        thread_id = make_thread_id(tenant_id, channel.id, SHARED_USER)
        await pipeline.ainvoke(state, config={"configurable": {"thread_id": thread_id}})
        return thread_id

    thread_a = await run_for(a, ch_a, "private-to-A")
    thread_b = await run_for(b, ch_b, "private-to-B")

    assert thread_a != thread_b
    assert thread_a.startswith(f"tenant:{a}:")
    assert thread_b.startswith(f"tenant:{b}:")

    # MemorySaver exposes ``aget`` keyed by config.
    cfg_a = {"configurable": {"thread_id": thread_a}}
    cfg_b = {"configurable": {"thread_id": thread_b}}
    snap_a = await memory_saver.aget(cfg_a)
    snap_b = await memory_saver.aget(cfg_b)

    assert snap_a is not None and snap_b is not None
    assert snap_a is not snap_b

    state_a = snap_a.get("channel_values") or snap_a
    state_b = snap_b.get("channel_values") or snap_b

    a_tenant = state_a.get("tenant_id")
    b_tenant = state_b.get("tenant_id")
    assert a_tenant == str(a)
    assert b_tenant == str(b)

    # Confirm conversation histories don't bleed across.
    a_message = state_a.get("user_message")
    b_message = state_b.get("user_message")
    assert a_message == "private-to-A"
    assert b_message == "private-to-B"
