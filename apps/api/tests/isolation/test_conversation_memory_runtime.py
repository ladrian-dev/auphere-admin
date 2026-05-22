"""Conversation memory (bug #10) — the agent remembers prior turns.

Before the fix, every graph node saw only the current ``user_message``:
the agent re-greeted on every turn and lost context across turns.
``_load_recent_history`` now loads prior ``messages`` rows into the LLM
context for ``classify``, the handler and ``respond``.

This runs two turns on the SAME conversation through the real pipeline and
asserts turn 2's LLM calls carry turn 1's exchange (the user's question and
the agent's own reply). It lives in the isolation suite because that is
where the runtime-pipeline fixtures (``make_pipeline`` + ``InMemoryProvider``
+ DB seeding) live.
"""

from __future__ import annotations

import pytest
from nexus_worker.runtime.state import new_state
from nexus_worker.runtime.thread_id import make_thread_id

from .conftest import make_pipeline, seed_active_agent_config, seed_channel

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

_TURN1 = "quiero comprar una funda de cojin"
_TURN1_REPLY = "respuesta-del-turno-uno"
_TURN2 = "y que tamanos tienen"


async def test_agent_sees_prior_turns_on_same_conversation(
    db_session,
    tenants_ab,
    agent_loader,
    in_memory_provider,
    llm_router,
    memory_saver,
):
    from nexus_api.db.models import (
        Conversation,
        ConversationStatus,
        Customer,
        Message,
        MessageDirection,
    )

    tenant = tenants_ab["a"]
    await seed_active_agent_config(
        db_session,
        tenant_id=tenant,
        system_prompt="Test assistant.",
        tools=["client.get_history"],
    )
    channel = await seed_channel(db_session, tenant_id=tenant, provider_identifier="mem-1")

    cust = Customer(tenant_id=tenant, identifier="mem-user", preferences={})
    db_session.add(cust)
    await db_session.commit()
    await db_session.refresh(cust)
    conv = Conversation(
        tenant_id=tenant,
        channel_id=channel.id,
        customer_id=cust.id,
        status=ConversationStatus.OPEN,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    in_memory_provider.responder = lambda c: (
        "info" if c.role == "classify" else _TURN1_REPLY
    )
    pipeline = make_pipeline(
        agent_loader=agent_loader,
        llm_router=llm_router,
        checkpointer=memory_saver,
    )
    thread_id = make_thread_id(tenant, channel.id, "mem-user")

    async def run_turn(text: str) -> None:
        inbound = Message(
            tenant_id=tenant,
            conversation_id=conv.id,
            direction=MessageDirection.INBOUND,
            content=text,
            tool_calls=[],
        )
        db_session.add(inbound)
        await db_session.commit()
        await db_session.refresh(inbound)
        state = new_state(
            tenant_id=tenant,
            channel_id=channel.id,
            user_id="mem-user",
            conversation_id=conv.id,
            customer_id=cust.id,
            inbound_message_id=inbound.id,
            user_message=text,
        )
        await pipeline.ainvoke(state, config={"configurable": {"thread_id": thread_id}})

    # ── Turn 1 — no history yet. ──────────────────────────────────────────
    await run_turn(_TURN1)
    turn1_count = len(in_memory_provider.calls)
    turn1_respond = [c for c in in_memory_provider.calls if c.role == "respond"][-1]
    flat1 = "\n".join(m["content"] for m in turn1_respond.messages)
    assert _TURN1 in flat1
    # First turn has no prior exchange — the reply text does not yet exist.
    assert _TURN1_REPLY not in flat1

    # ── Turn 2 — same conversation. Turn 1's inbound + outbound (persisted
    # by the checkpoint node) must now be visible to the agent. ───────────
    await run_turn(_TURN2)
    turn2_calls = in_memory_provider.calls[turn1_count:]

    turn2_respond = [c for c in turn2_calls if c.role == "respond"][-1]
    flat2 = "\n".join(m["content"] for m in turn2_respond.messages)
    assert _TURN1 in flat2, "turn 1 user message missing from turn 2 context"
    assert _TURN1_REPLY in flat2, "turn 1 assistant reply missing from turn 2 context"
    assert _TURN2 in flat2

    # classify also receives the history so follow-ups route with context.
    turn2_classify = [c for c in turn2_calls if c.role == "classify"][-1]
    flat_classify = "\n".join(m["content"] for m in turn2_classify.messages)
    assert _TURN1 in flat_classify
