"""Garantía 7 — LLM stateless per tenant (RUNTIME).

Two concurrent pipeline runs with different tenants must produce two
independent provider invocations. The recorded ``LLMCall`` list must contain:

- distinct ``tenant_id`` values for each call;
- the same ``tenant_id`` shared across all calls in a single run
  (classify and respond both belong to that tenant);
- no batched call lists (the InMemoryProvider records one entry per
  ``acomplete`` invocation by design).

The contract test (``test_7_llm_calls_per_tenant.py``) still asserts that the
LiteLLM kwargs used in production never enable cross-tenant batching.
"""

from __future__ import annotations

import asyncio

import pytest
from nexus_worker.runtime.llm import litellm_kwargs_contract
from nexus_worker.runtime.state import new_state
from nexus_worker.runtime.thread_id import make_thread_id

from .conftest import make_pipeline, seed_active_agent_config, seed_channel

pytestmark = [pytest.mark.isolation]  # asyncio is auto-detected (asyncio_mode=auto)


async def test_concurrent_tenants_produce_independent_provider_calls(
    db_session,
    tenants_ab,
    agent_loader,
    in_memory_provider,
    llm_router,
    memory_saver,
):
    a, b = tenants_ab["a"], tenants_ab["b"]
    await seed_active_agent_config(
        db_session, tenant_id=a, system_prompt="A", tools=["client.get_history"]
    )
    await seed_active_agent_config(
        db_session, tenant_id=b, system_prompt="B", tools=["client.get_history"]
    )
    ch_a = await seed_channel(db_session, tenant_id=a, provider_identifier="iso7-a")
    ch_b = await seed_channel(db_session, tenant_id=b, provider_identifier="iso7-b")

    in_memory_provider.responder = lambda c: "info" if c.role == "classify" else "ok"

    pipeline = make_pipeline(
        agent_loader=agent_loader,
        llm_router=llm_router,
        checkpointer=memory_saver,
    )

    # Seed customers/conversations/inbound rows up front so the concurrent
    # pipeline runs don't share the test's session for writes.
    from nexus_api.db.models import (
        Conversation,
        ConversationStatus,
        Customer,
        Message,
        MessageDirection,
    )

    seed: dict[str, dict] = {}
    for tenant_id, channel, user_id in [(a, ch_a, "u-a"), (b, ch_b, "u-b")]:
        cust = Customer(tenant_id=tenant_id, identifier=user_id, preferences={})
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
        seed[user_id] = {
            "tenant_id": tenant_id,
            "channel_id": channel.id,
            "user_id": user_id,
            "conversation_id": conv.id,
            "customer_id": cust.id,
            "inbound_message_id": inbound.id,
        }

    async def run_for(user_id: str):
        s = seed[user_id]
        state = new_state(user_message="hi", **s)
        return await pipeline.ainvoke(
            state,
            config={
                "configurable": {
                    "thread_id": make_thread_id(s["tenant_id"], s["channel_id"], user_id)
                }
            },
        )

    # Drive A and B concurrently — pipeline-internal sessions are independent.
    await asyncio.gather(run_for("u-a"), run_for("u-b"))

    # Block D: each turn produces classify + a handler-intent tool_loop
    # call (role='info' here, since the responder routes to the info
    # intent) + respond. Three calls per tenant.
    a_calls = [c for c in in_memory_provider.calls if str(c.tenant_id) == str(a)]
    b_calls = [c for c in in_memory_provider.calls if str(c.tenant_id) == str(b)]

    assert {c.role for c in a_calls} == {"classify", "info", "respond"}
    assert {c.role for c in b_calls} == {"classify", "info", "respond"}
    assert len(a_calls) == 3
    assert len(b_calls) == 3

    # No call ever carries the wrong tenant.
    assert all(str(c.tenant_id) in {str(a), str(b)} for c in in_memory_provider.calls)


@pytest.mark.unit
def test_litellm_contract_still_disallows_cross_tenant_batching():
    cfg = litellm_kwargs_contract()
    assert cfg["enable_batching"] is False
    assert cfg["group_by"] in (None, "tenant_id")
