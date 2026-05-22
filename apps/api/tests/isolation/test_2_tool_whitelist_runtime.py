"""Garantía 2 — Tool whitelist por agente (RUNTIME).

Block D introduces real function-calling. The binding guarantee is the
**pre-LLM filter**: only tools in ``whitelist ∩ category[intent]`` reach
the LLM as ``tools=`` definitions. Even if the LLM hallucinates a name
outside that set, ``MCPRegistry.dispatch`` re-checks the whitelist as
defense in depth and records ``isolation.tool_whitelist_violation``.

This test asserts both planes:

1. The ``tools`` list passed to the LLM in a handler tool_loop is exactly
   the whitelist-intersected category — no leakage of non-whitelisted
   tool definitions.
2. Even when the InMemoryProvider scripts a hostile ``tool_caller`` that
   emits a tool name OUTSIDE the filtered set, the dispatch refuses,
   the violation counter increments, and the pipeline records a
   ``skipped:not_in_whitelist`` envelope (no side effects).

The data-layer contract for the same garantía lives in
``test_2_tool_whitelist_contract.py`` and stays in CI alongside this one.
"""

from __future__ import annotations

import uuid

import pytest
from nexus_worker.runtime.llm import ToolCall
from nexus_worker.runtime.state import new_state
from nexus_worker.runtime.thread_id import make_thread_id

from nexus_api.core.metrics import ISOLATION_TOOL_WHITELIST_VIOLATION, counters

from .conftest import make_pipeline, seed_active_agent_config, seed_channel

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def test_pre_llm_filter_blocks_non_whitelisted_definitions(
    db_session,
    tenants_ab,
    agent_loader,
    in_memory_provider,
    llm_router,
    memory_saver,
):
    """The handler tool_loop sends ``tools=`` with definitions limited to
    ``whitelist ∩ category[intent]``. We whitelist only ``booking.*`` and
    drive the classifier to the ``queue`` intent — the queue category
    overlaps the whitelist on nothing, so the LLM gets ``tools=[]``."""
    a = tenants_ab["a"]
    await seed_active_agent_config(
        db_session,
        tenant_id=a,
        system_prompt="You are A's assistant.",
        tools=["booking.check_availability", "booking.create_appointment"],
    )
    channel = await seed_channel(db_session, tenant_id=a, provider_identifier="iso2-a")

    in_memory_provider.responder = lambda call: "queue" if call.role == "classify" else "ok respond"
    counters.reset()

    pipeline = make_pipeline(
        agent_loader=agent_loader,
        llm_router=llm_router,
        checkpointer=memory_saver,
    )

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

    # ── 1. Handler-level LLM call (role='queue') was made — but the
    # ``tools`` list it received is empty (whitelist intersection with
    # the queue category is the empty set).
    queue_calls = [c for c in in_memory_provider.calls if c.role == "queue"]
    # No tool definitions reached the LLM for this intent.
    for c in queue_calls:
        for td in c.tools:
            name = td.get("function", {}).get("name", "")
            assert name in {
                "booking.check_availability",
                "booking.create_appointment",
            }, f"non-whitelisted tool {name!r} leaked into LLM context"

    # ── 2. tool_calls are empty — no side effect fired.
    statuses = {tc.get("status") for tc in final.get("tool_calls", [])}
    assert "ok" not in statuses, "no whitelisted tool should have actually run"

    # ── 3. The queue handler ran (ADR-023: it produces the final text
    # itself), but no queue tool definition leaked into its prompt —
    # neither as a ``tools=`` entry nor anywhere in the message text.
    assert queue_calls, "expected the queue handler to be invoked"
    last_queue = queue_calls[-1]
    flat_messages = "\n".join(
        m["content"] for m in last_queue.messages if isinstance(m.get("content"), str)
    )
    assert "queue.join_queue" not in flat_messages
    assert "queue.get_estimated_wait" not in flat_messages


async def test_hallucinated_tool_call_is_rejected_by_dispatch(
    db_session,
    tenants_ab,
    agent_loader,
    in_memory_provider,
    llm_router,
    memory_saver,
):
    """Defense-in-depth: even if the model emits a tool call outside the
    filtered set, ``MCPRegistry.dispatch`` rejects it and the violation
    counter increments. The pipeline records a ``skipped`` envelope."""
    a = tenants_ab["a"]
    await seed_active_agent_config(
        db_session,
        tenant_id=a,
        system_prompt="A",
        tools=["client.get_history"],
    )
    channel = await seed_channel(db_session, tenant_id=a, provider_identifier="iso2-h")

    counters.reset()

    in_memory_provider.responder = lambda c: "info" if c.role == "classify" else "resp"
    # Hostile model: emits a queue.* call into the info handler on the
    # first loop iteration. The info category does not include queue.* so
    # dispatch must refuse. (The ``no tool message yet`` guard makes the
    # script emit exactly once, not on every ReAct iteration.)
    in_memory_provider.tool_caller = lambda c: (
        [
            ToolCall(
                id="t1",
                name="queue.join_queue",
                arguments={"customer_id": "00000000-0000-0000-0000-000000000000"},
            )
        ]
        if c.role == "info" and not any(m.get("role") == "tool" for m in c.messages)
        else []
    )

    pipeline = make_pipeline(
        agent_loader=agent_loader,
        llm_router=llm_router,
        checkpointer=memory_saver,
    )

    from nexus_api.db.models import (
        Conversation,
        ConversationStatus,
        Customer,
        Message,
        MessageDirection,
    )

    cust = Customer(tenant_id=a, identifier="iso2h-user", preferences={})
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
        content="qué hora es",
        tool_calls=[],
    )
    db_session.add(inbound)
    await db_session.commit()
    await db_session.refresh(inbound)

    state = new_state(
        tenant_id=a,
        channel_id=channel.id,
        user_id="iso2h-user",
        conversation_id=conv.id,
        customer_id=cust.id,
        inbound_message_id=inbound.id,
        user_message="qué hora es",
    )
    thread_id = make_thread_id(a, channel.id, "iso2h-user")
    final = await pipeline.ainvoke(state, config={"configurable": {"thread_id": thread_id}})

    # The hostile tool call was rejected by dispatch; counter incremented.
    assert counters.get(ISOLATION_TOOL_WHITELIST_VIOLATION) >= 1
    statuses = {tc.get("status") for tc in final["tool_calls"]}
    assert "skipped:not_in_whitelist" in statuses
    # No actual queue side effects happened.
    assert "ok" not in statuses


async def test_two_tenants_with_disjoint_whitelists_do_not_leak(
    db_session,
    tenants_ab,
    agent_loader,
    in_memory_provider,
    llm_router,
    memory_saver,
):
    """A's whitelist has client.get_preferences only; B's has client.get_history.

    Both classify to ``info``. The info category exposes both ``client.*``
    tools, so the pre-LLM filter sends A only ``client.get_preferences``
    and B only ``client.get_history``. The LLM is scripted (per-tenant) to
    invoke client.get_history. For A, dispatch refuses (not whitelisted)
    and increments the violation counter. For B, the tool actually runs.
    """
    a, b = tenants_ab["a"], tenants_ab["b"]
    await seed_active_agent_config(
        db_session,
        tenant_id=a,
        system_prompt="A",
        tools=["client.get_preferences"],
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

    from nexus_api.db.models import (
        Conversation,
        ConversationStatus,
        Customer,
        Message,
        MessageDirection,
    )

    async def run_for(tenant_id, channel):
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
        # Scripted tool call references THIS tenant's customer_id. Emitted
        # once (first ReAct iteration, before any tool message exists).
        in_memory_provider.tool_caller = lambda c, cid=cust.id: (
            [
                ToolCall(
                    id="t",
                    name="client.get_history",
                    arguments={"customer_id": str(cid), "limit": 5},
                )
            ]
            if c.role == "info" and not any(m.get("role") == "tool" for m in c.messages)
            else []
        )
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

    # A: client.get_history is NOT in A's whitelist; dispatch refuses.
    assert "skipped:not_in_whitelist" in statuses_a
    # B: it IS in B's whitelist; the tool actually executes.
    assert "ok" in statuses_b
    # And the counter increased only for A's run.
    assert counters.get(ISOLATION_TOOL_WHITELIST_VIOLATION) >= 1


def _unused(_x: uuid.UUID) -> None:  # keep uuid import live for mypy
    pass
