"""Promote without redeploy.

Drives the AgentLoader through a real promote cycle:

1. Tenant has ``agent_config v1`` with whitelist ``[booking.check_availability]``.
2. Run turn 1 → AgentLoader caches v1.
3. Stage + promote v2 with whitelist ``[client.get_history]`` via the API
   service (so the promote pub/sub event fires the same way it does in
   production). Block C wires that publish from the FastAPI endpoint, but
   here we exercise the loader by invalidating directly — which is what the
   subscriber would do — and assert the cache picks up v2 on the next turn.

If the loader ever silently kept v1 served, the second run would still hit
``isolation.tool_whitelist_violation`` for ``client.get_history``. Asserting
the second run skips ``booking.check_availability`` (now NOT in the whitelist)
and runs ``client.get_history`` (now in it) is a positive proof of the swap.
"""

from __future__ import annotations

import uuid

import pytest
from langgraph.checkpoint.memory import MemorySaver
from nexus_worker.runtime.agent_loader import AgentLoader
from nexus_worker.runtime.llm import InMemoryProvider, LLMRouter, ToolCall
from nexus_worker.runtime.pipeline import build_pipeline
from nexus_worker.runtime.state import new_state
from nexus_worker.runtime.thread_id import make_thread_id

from nexus_api.core.tenant_context import tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    Tenant,
    TenantPlan,
)
from nexus_api.services import AgentConfigService

from ..isolation.conftest import (  # type: ignore[import-not-found]
    seed_active_agent_config,
    seed_channel,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_promote_swaps_active_config_without_restart(db_session):
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id, name="PromoTen", slug=f"promo-{tenant_id.hex[:6]}", plan=TenantPlan.PRO
        )
    )
    await db_session.commit()

    # v1 active. The whitelist deliberately includes a tool in the ``info``
    # category (so the handler tool_loop actually invokes the LLM) but
    # NOT ``client.get_history`` — so when the scripted model emits a
    # ``client.get_history`` call, dispatch refuses with skipped.
    await seed_active_agent_config(
        db_session,
        tenant_id=tenant_id,
        system_prompt="prompt v1",
        tools=["booking.check_availability", "client.get_preferences"],
    )
    channel = await seed_channel(db_session, tenant_id=tenant_id, provider_identifier="prom-1")

    provider = InMemoryProvider()
    # Force "info" intent so the handler attempts client.get_history.
    provider.responder = lambda c: "info" if c.role == "classify" else "ok"

    loader = AgentLoader()
    router = LLMRouter(
        provider=provider,
        classify_model="t/c",
        respond_model="t/r",
        fallback_model="t/f",
    )
    saver = MemorySaver()
    pipeline = build_pipeline(agent_loader=loader, llm_router=router, checkpointer=saver)

    cust = Customer(tenant_id=tenant_id, identifier="user-1", preferences={})
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

    # Block D: scripted tool_caller emits client.get_history once (on the
    # first ReAct iteration, before any tool message exists). With v1's
    # whitelist (booking.* only) the dispatch refuses; with v2's whitelist
    # (client.get_history) it executes.
    customer_id = cust.id
    provider.tool_caller = lambda c: (
        [
            ToolCall(
                id="t",
                name="client.get_history",
                arguments={"customer_id": str(customer_id), "limit": 5},
            )
        ]
        if c.role == "info" and not any(m.get("role") == "tool" for m in c.messages)
        else []
    )

    async def run_turn(text: str) -> dict:
        inbound = Message(
            tenant_id=tenant_id,
            conversation_id=conv.id,
            direction=MessageDirection.INBOUND,
            content=text,
            tool_calls=[],
        )
        db_session.add(inbound)
        await db_session.commit()
        await db_session.refresh(inbound)
        state = new_state(
            tenant_id=tenant_id,
            channel_id=channel.id,
            user_id="user-1",
            conversation_id=conv.id,
            customer_id=cust.id,
            inbound_message_id=inbound.id,
            user_message=text,
        )
        return await pipeline.ainvoke(
            state,
            config={"configurable": {"thread_id": make_thread_id(tenant_id, channel.id, "user-1")}},
        )

    # Turn 1 — under v1, info handler tries client.get_history but it's NOT
    # in v1's whitelist. So it's skipped.
    final_v1 = await run_turn("hola")
    statuses_v1 = {tc.get("status") for tc in final_v1["tool_calls"]}
    assert "skipped:not_in_whitelist" in statuses_v1
    assert "ok" not in statuses_v1

    # Promote v2 via the service in a tenant-scoped session — the same path
    # the admin endpoint uses.
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        with tenant_context(tenant_id):
            svc = AgentConfigService(session)
            staged = await svc.stage_new_version(
                actor="test",
                system_prompt_rendered="prompt v2",
                channels=[],
                tools=["client.get_history"],
                policies={},
            )
            await svc.promote(staged.version, actor="test")

    # The pub/sub subscriber would call invalidate; emulate it directly so
    # the test does not need a live Redis subscriber loop.
    await loader.invalidate(tenant_id)

    # Turn 2 — v2 active, client.get_history is in the whitelist.
    final_v2 = await run_turn("y ahora?")
    statuses_v2 = {tc.get("status") for tc in final_v2["tool_calls"]}
    assert "ok" in statuses_v2  # client.get_history actually executed
    assert "skipped:not_in_whitelist" not in statuses_v2

    # And the loader holds the v2 version now.
    bundle = await loader.load(tenant_id)
    assert bundle.version == 2
    assert bundle.system_prompt == "prompt v2"
    assert "client.get_history" in bundle.tools
