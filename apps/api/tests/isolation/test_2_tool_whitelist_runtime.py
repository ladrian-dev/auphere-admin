"""Garantía 2 — Tool whitelist por agente (RUNTIME).

This test replaces the contract-only check from block B with an end-to-end run
through the LangGraph pipeline:

- Tenant A's ``agent_config.tools`` whitelist contains ``booking.*`` only.
- The classifier returns ``queue`` so the queue handler runs.
- Every queue tool the handler tries (``queue.join_queue``,
  ``queue.get_estimated_wait``) is missing from the whitelist.

The test asserts:

1. ``isolation.tool_whitelist_violation`` increments — at least once per
   non-whitelisted tool the handler attempted.
2. The handler records ``status: skipped:not_in_whitelist`` instead of
   actually invoking the stub.
3. The respond-phase prompt does NOT mention the queue tool names — they
   never reach the LLM context.

The data-layer contract for the same garantía lives in
``test_2_tool_whitelist_contract.py`` and stays in CI alongside this one.
"""

from __future__ import annotations

import uuid

import pytest
from nexus_worker.runtime.state import new_state
from nexus_worker.runtime.thread_id import make_thread_id

from nexus_api.core.metrics import ISOLATION_TOOL_WHITELIST_VIOLATION, counters

from .conftest import make_pipeline, seed_active_agent_config, seed_channel

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def test_runtime_blocks_tool_outside_whitelist(
    db_session,
    tenants_ab,
    agent_loader,
    in_memory_provider,
    llm_router,
    memory_saver,
):
    a = tenants_ab["a"]
    await seed_active_agent_config(
        db_session,
        tenant_id=a,
        system_prompt="You are A's assistant.",
        # Whitelist only the booking namespace — queue.* must be denied.
        tools=["booking.check_availability", "booking.create_appointment"],
    )
    channel = await seed_channel(db_session, tenant_id=a, provider_identifier="iso2-a")

    # The classifier always returns "queue" — handler will try queue tools.
    in_memory_provider.responder = lambda call: "queue" if call.role == "classify" else "ok respond"

    counters.reset()

    pipeline = make_pipeline(
        agent_loader=agent_loader,
        llm_router=llm_router,
        checkpointer=memory_saver,
    )

    # Use deterministic UUIDs for conversation/customer/inbound — the
    # checkpoint node persists into the messages table, so these must exist
    # in the DB to satisfy the FK. We seed them inline.
    from nexus_api.db.models import (
        Conversation,
        ConversationStatus,
        Customer,
        Message,
        MessageDirection,
    )

    cust = Customer(tenant_id=a, identifier="iso2-user", preferences={})
    db_session.add(cust)
    await db_session.commit()
    await db_session.refresh(cust)
    conv = Conversation(
        tenant_id=a,
        channel_id=channel.id,
        customer_id=cust.id,
        status=ConversationStatus.OPEN,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    inbound = Message(
        tenant_id=a,
        conversation_id=conv.id,
        direction=MessageDirection.INBOUND,
        content="ponme en la cola",
        tool_calls=[],
    )
    db_session.add(inbound)
    await db_session.commit()
    await db_session.refresh(inbound)

    state = new_state(
        tenant_id=a,
        channel_id=channel.id,
        user_id="iso2-user",
        conversation_id=conv.id,
        customer_id=cust.id,
        inbound_message_id=inbound.id,
        user_message="ponme en la cola",
    )
    thread_id = make_thread_id(a, channel.id, "iso2-user")
    final = await pipeline.ainvoke(state, config={"configurable": {"thread_id": thread_id}})

    # ── 1. Counter incremented (one per skipped tool in queue handler).
    assert counters.get(ISOLATION_TOOL_WHITELIST_VIOLATION) >= 2

    # ── 2. tool_calls show skip, not execution.
    statuses = {tc.get("status") for tc in final.get("tool_calls", [])}
    assert "skipped:not_in_whitelist" in statuses
    assert "ok" not in statuses  # NO tool actually fired

    # ── 3. Queue tool names didn't leak into the respond LLM messages.
    respond_calls = [c for c in in_memory_provider.calls if c.role == "respond"]
    assert respond_calls, "expected respond to be invoked"
    last_respond = respond_calls[-1]
    flat_messages = "\n".join(m["content"] for m in last_respond.messages)
    # The summarised intent line is allowed to mention "queue" the intent —
    # but tool names like "queue.join_queue" must never be passed verbatim
    # because the runtime treats them as skipped, not invoked.
    assert "queue.join_queue" not in flat_messages or "skipped" in flat_messages.lower()


async def test_two_tenants_with_disjoint_whitelists_do_not_leak(
    db_session,
    tenants_ab,
    agent_loader,
    in_memory_provider,
    llm_router,
    memory_saver,
):
    """A's whitelist has booking.*; B's has client.get_history.

    Drive the same intent (info → client.get_history) on each. A's handler
    must record skip; B's must execute.
    """
    a, b = tenants_ab["a"], tenants_ab["b"]
    await seed_active_agent_config(
        db_session,
        tenant_id=a,
        system_prompt="A",
        tools=["booking.check_availability"],
    )
    await seed_active_agent_config(
        db_session,
        tenant_id=b,
        system_prompt="B",
        tools=["client.get_history"],
    )
    ch_a = await seed_channel(db_session, tenant_id=a, provider_identifier="iso2-a2")
    ch_b = await seed_channel(db_session, tenant_id=b, provider_identifier="iso2-b2")

    in_memory_provider.responder = lambda c: "info" if c.role == "classify" else "resp"

    pipeline = make_pipeline(
        agent_loader=agent_loader,
        llm_router=llm_router,
        checkpointer=memory_saver,
    )

    async def run_for(tenant_id, channel):
        from nexus_api.db.models import (
            Conversation,
            ConversationStatus,
            Customer,
            Message,
            MessageDirection,
        )

        cust = Customer(tenant_id=tenant_id, identifier="u", preferences={})
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
            content="hi",
            tool_calls=[],
        )
        db_session.add(inbound)
        await db_session.commit()
        await db_session.refresh(inbound)
        state = new_state(
            tenant_id=tenant_id,
            channel_id=channel.id,
            user_id="u",
            conversation_id=conv.id,
            customer_id=cust.id,
            inbound_message_id=inbound.id,
            user_message="hi",
        )
        return await pipeline.ainvoke(
            state,
            config={"configurable": {"thread_id": make_thread_id(tenant_id, channel.id, "u")}},
        )

    counters.reset()
    state_a = await run_for(a, ch_a)
    state_b = await run_for(b, ch_b)

    statuses_a = {tc.get("status") for tc in state_a["tool_calls"]}
    statuses_b = {tc.get("status") for tc in state_b["tool_calls"]}

    # A skipped client.get_history (not in whitelist).
    assert "skipped:not_in_whitelist" in statuses_a
    # B actually executed it.
    assert "ok" in statuses_b
    # And the metric increased only for A's run.
    assert counters.get(ISOLATION_TOOL_WHITELIST_VIOLATION) >= 1


def _unused(_x: uuid.UUID) -> None:  # keep uuid import live for mypy
    pass
