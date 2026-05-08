"""Isolation suite shared fixtures: two distinct tenants per test."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy import text


@pytest_asyncio.fixture
async def tenants_ab(db_session) -> dict[str, uuid.UUID]:
    from nexus_api.db.models import Tenant, TenantPlan

    a_id = uuid.uuid4()
    b_id = uuid.uuid4()
    db_session.add_all(
        [
            Tenant(id=a_id, name="Iso A", slug=f"iso-a-{a_id.hex[:6]}", plan=TenantPlan.PRO),
            Tenant(id=b_id, name="Iso B", slug=f"iso-b-{b_id.hex[:6]}", plan=TenantPlan.ESSENTIAL),
        ]
    )
    await db_session.commit()
    return {"a": a_id, "b": b_id}


async def set_tenant(session, tenant_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"),
        {"t": str(tenant_id)},
    )
    await session.execute(text("SET LOCAL ROLE nexus_app"))


# ── Runtime fixtures (block C) ─────────────────────────────────────────────────


@pytest_asyncio.fixture
async def memory_saver() -> AsyncIterator[object]:
    """In-memory LangGraph checkpointer for runtime tests. Same thread_id
    semantics as AsyncPostgresSaver — block C asserts that scoping by
    ``thread_id`` is enough (architecture/agent-isolation.md garantía 4)."""
    from langgraph.checkpoint.memory import MemorySaver

    yield MemorySaver()


@pytest_asyncio.fixture
async def agent_loader():
    from nexus_worker.runtime.agent_loader import AgentLoader

    return AgentLoader()


@pytest_asyncio.fixture
async def in_memory_provider():
    from nexus_worker.runtime.llm import InMemoryProvider

    return InMemoryProvider()


@pytest_asyncio.fixture
async def llm_router(in_memory_provider):
    from nexus_worker.runtime.llm import LLMRouter

    return LLMRouter(
        provider=in_memory_provider,
        classify_model="test/classify",
        respond_model="test/respond",
        fallback_model="test/fallback",
    )


def make_pipeline(*, agent_loader, llm_router, checkpointer):
    """Helper used by runtime tests to assemble a pipeline."""
    from nexus_worker.runtime.pipeline import build_pipeline

    return build_pipeline(
        agent_loader=agent_loader,
        llm_router=llm_router,
        checkpointer=checkpointer,
    )


async def seed_active_agent_config(
    db_session,
    *,
    tenant_id: uuid.UUID,
    system_prompt: str,
    tools: list[str],
    policies: dict | None = None,
):
    """Insert and immediately promote a config so the AgentLoader can read it.

    Bypasses ``AgentConfigService`` because we want the row to be ``active``
    in a single test step. Tests that need promote semantics (the no-redeploy
    test) drive the service through the API instead.
    """
    from nexus_api.db.models import AgentConfig, AgentConfigStatus

    cfg = AgentConfig(
        tenant_id=tenant_id,
        version=1,
        status=AgentConfigStatus.ACTIVE,
        system_prompt_rendered=system_prompt,
        channels=[],
        tools=tools,
        policies=policies or {},
        seed_template_ref=None,
    )
    db_session.add(cfg)
    await db_session.commit()
    await db_session.refresh(cfg)
    return cfg


async def seed_channel(
    db_session,
    *,
    tenant_id: uuid.UUID,
    provider_identifier: str,
):
    from nexus_api.db.models import Channel, ChannelStatus, ChannelType

    ch = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="ycloud",
        provider_identifier=provider_identifier,
        config={},
        status=ChannelStatus.ACTIVE,
    )
    db_session.add(ch)
    await db_session.commit()
    await db_session.refresh(ch)
    return ch


async def seed_customer_and_conversation(
    db_session,
    *,
    tenant_id: uuid.UUID,
    channel_id: uuid.UUID,
    user_id: str,
):
    from nexus_api.db.models import (
        Conversation,
        ConversationStatus,
        Customer,
    )

    c = Customer(tenant_id=tenant_id, identifier=user_id, name=None, preferences={})
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)

    conv = Conversation(
        tenant_id=tenant_id,
        channel_id=channel_id,
        customer_id=c.id,
        status=ConversationStatus.OPEN,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    return c, conv
