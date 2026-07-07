"""ADR-023 — the handler runs a real ReAct loop and tool results reach
the LLM that writes the customer-facing answer.

Before ADR-023 the pipeline dispatched tools but the node that produced
the reply only saw ``tool: status`` — never the actual ``result``. Every
read tool was decorative. This test proves the fix end-to-end on the real
compiled pipeline:

1. The scripted model requests ``client.get_history`` on the first loop
   iteration, then answers with text on the second.
2. The second handler LLM call must contain a ``role: "tool"`` message —
   the real tool result fed back into the context.
3. ``state["response"]`` is the text the loop produced itself (there is no
   separate ``respond`` node anymore).
"""

from __future__ import annotations

import uuid

import pytest
from langgraph.checkpoint.memory import MemorySaver
from nexus_worker.runtime.agent_loader import AgentLoader
from nexus_worker.runtime.llm import InMemoryProvider, LLMRouter, ToolCall
from nexus_worker.runtime.pipeline import MAX_TOOL_ITERATIONS, build_pipeline
from nexus_worker.runtime.state import new_state
from nexus_worker.runtime.thread_id import make_thread_id

from nexus_api.db.models import (
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    Tenant,
    TenantPlan,
)

from ..isolation.conftest import (  # type: ignore[import-not-found]
    seed_active_agent_config,
    seed_channel,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_FINAL_ANSWER = "Tu última visita fue hace dos semanas — ¿querés repetir el mismo corte?"


async def _seed_turn(db_session, *, tenant_id, channel, customer, conv, text):
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
    return new_state(
        tenant_id=tenant_id,
        channel_id=channel.id,
        user_id=customer.identifier,
        conversation_id=conv.id,
        customer_id=customer.id,
        inbound_message_id=inbound.id,
        user_message=text,
    )


async def test_tool_result_reaches_the_responding_llm(db_session):
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="ReactTen",
            slug=f"react-{tenant_id.hex[:6]}",
            plan=TenantPlan.PRO,
        )
    )
    await db_session.commit()

    await seed_active_agent_config(
        db_session,
        tenant_id=tenant_id,
        system_prompt="Sos el asistente de la barbería.",
        tools=["client.get_history"],
    )
    channel = await seed_channel(db_session, tenant_id=tenant_id, provider_identifier="react-1")
    cust = Customer(tenant_id=tenant_id, identifier="react-user", preferences={})
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

    provider = InMemoryProvider()

    def _has_tool_msg(call) -> bool:
        return any(m.get("role") == "tool" for m in call.messages)

    # classify → info. Handler: iteration 0 has no tool message yet → the
    # model "thinks" silently; iteration 1 sees the tool result → answers.
    def responder(call):
        if call.role == "classify":
            return "info"
        return _FINAL_ANSWER if _has_tool_msg(call) else ""

    def tool_caller(call):
        if call.role == "info" and not _has_tool_msg(call):
            return [
                ToolCall(
                    id="t1",
                    name="client.get_history",
                    arguments={"customer_id": str(cust.id), "limit": 5},
                )
            ]
        return []

    provider.responder = responder
    provider.tool_caller = tool_caller

    router = LLMRouter(
        provider=provider,
        classify_model="t/c",
        respond_model="t/r",
        fallback_model="t/f",
    )
    pipeline = build_pipeline(
        agent_loader=AgentLoader(),
        llm_router=router,
        checkpointer=MemorySaver(),
    )

    state = await _seed_turn(
        db_session,
        tenant_id=tenant_id,
        channel=channel,
        customer=cust,
        conv=conv,
        text="hola, lo de siempre",
    )
    final = await pipeline.ainvoke(
        state,
        config={"configurable": {"thread_id": make_thread_id(tenant_id, channel.id, "react-user")}},
    )

    # ── The loop produced the final text itself (no respond node). ────────
    assert final["response"] == _FINAL_ANSWER

    # ── The tool actually ran and its envelope is in tool_calls. ──────────
    statuses = {tc.get("status") for tc in final["tool_calls"]}
    assert "ok" in statuses
    history_calls = [tc for tc in final["tool_calls"] if tc.get("tool") == "client.get_history"]
    assert history_calls and history_calls[0].get("status") == "ok"

    # ── The decisive assertion (ADR-023): the SECOND handler LLM call
    # carries a ``role: "tool"`` message — the real result fed back. ──────
    info_calls = [c for c in provider.calls if c.role == "info"]
    assert len(info_calls) == 2, "handler should loop exactly twice"
    first_call, second_call = info_calls
    assert not any(m.get("role") == "tool" for m in first_call.messages)
    tool_msgs = [m for m in second_call.messages if m.get("role") == "tool"]
    assert tool_msgs, "the tool result never reached the responding LLM"
    assert tool_msgs[0]["tool_call_id"] == "t1"
    assert isinstance(tool_msgs[0]["content"], str) and tool_msgs[0]["content"]


async def test_loop_is_bounded_when_model_never_stops(db_session):
    """A model that requests a tool on every iteration must still
    terminate — the loop caps at MAX_TOOL_ITERATIONS and the final
    iteration is forced tool-free so an answer is always produced."""
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="LoopTen",
            slug=f"loop-{tenant_id.hex[:6]}",
            plan=TenantPlan.PRO,
        )
    )
    await db_session.commit()

    await seed_active_agent_config(
        db_session,
        tenant_id=tenant_id,
        system_prompt="prompt",
        tools=["client.get_history"],
    )
    channel = await seed_channel(db_session, tenant_id=tenant_id, provider_identifier="loop-1")
    cust = Customer(tenant_id=tenant_id, identifier="loop-user", preferences={})
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

    provider = InMemoryProvider()
    provider.responder = lambda c: "info" if c.role == "classify" else "still working"
    # Pathological model: always wants the tool again.
    provider.tool_caller = lambda c: (
        [
            ToolCall(
                id="t",
                name="client.get_history",
                arguments={"customer_id": str(cust.id), "limit": 5},
            )
        ]
        if c.role == "info"
        else []
    )

    router = LLMRouter(
        provider=provider,
        classify_model="t/c",
        respond_model="t/r",
        fallback_model="t/f",
    )
    pipeline = build_pipeline(
        agent_loader=AgentLoader(),
        llm_router=router,
        checkpointer=MemorySaver(),
    )

    state = await _seed_turn(
        db_session,
        tenant_id=tenant_id,
        channel=channel,
        customer=cust,
        conv=conv,
        text="dame mi historial",
    )
    final = await pipeline.ainvoke(
        state,
        config={"configurable": {"thread_id": make_thread_id(tenant_id, channel.id, "loop-user")}},
    )

    # The loop terminated and produced a non-empty answer.
    assert final["response"]
    # It made exactly MAX_TOOL_ITERATIONS handler calls — no more.
    info_calls = [c for c in provider.calls if c.role == "info"]
    assert len(info_calls) == MAX_TOOL_ITERATIONS
