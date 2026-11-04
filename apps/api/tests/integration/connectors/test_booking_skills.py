"""Owner, 2026-11-03 — connecting what can book turns booking on in the agent's draft.

Its writing tools are born blocked, so connecting left an agent that could see free
slots and not take one. Only the draft changes: the person saves it and its tests go
stale. An agent with Auphere's own calendar does not get a second one.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    AgentConnectorActivation,
    Connector,
    Partner,
    TenantConnector,
    ToolCatalog,
    ToolStatus,
)
from nexus_api.services.connectors import booking_skills
from nexus_api.services.connectors.toolkits import TOOLKIT_ALLOWLISTS

from ..business._business_world import Biz, new_business, seed_agent
from ._activation_world import READ, SLUG, SPEC, WRITE, connect, seed_integration

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    biz = await new_business(client, db_session, console_world, name="Barbería Cultor")
    partner = await db_session.get(Partner, biz.partner_id)
    assert partner is not None
    partner.console_v2_enabled_at = datetime.now(UTC)
    await db_session.commit()
    return biz


@pytest.fixture(autouse=True)
def _this_connector_books(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(booking_skills.BOOKING_TOOLS, SLUG, (READ, WRITE, "tienda_test.not_synced"))


async def _world(db_session: AsyncSession, biz: Biz, *, tools: list[str]) -> Any:
    connector = await seed_integration(db_session)
    install_id = await connect(db_session, biz, connector)
    agent_id, cfg_id = await seed_agent(
        db_session, biz.tenant_id, name="Ventas", prompt="Vende.", tools=tools
    )
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg = await db_session.get(AgentConfig, cfg_id)
        assert cfg is not None
        cfg.spec = {
            **SPEC,
            "identity": {"name": "Ventas", "description": "Atiende y agenda por WhatsApp."},
            "procedures": [],
            "tools": tools,
        }
        install = await db_session.get(TenantConnector, install_id)
    await db_session.commit()
    return connector, install, agent_id


async def _draft(db_session: AsyncSession, biz: Biz, agent_id: Any) -> AgentConfig | None:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        return await db_session.scalar(
            sa.select(AgentConfig)
            .where(AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.STAGED)
            .execution_options(populate_existing=True)
        )


async def _enable(
    db_session: AsyncSession,
    biz: Biz,
    connector: Connector,
    install: TenantConnector,
    agent_id: Any,
) -> list[str]:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        added = await booking_skills.enable_booking_skills(
            db_session, connector=connector, install=install, agent_id=agent_id, actor="test"
        )
    await db_session.commit()
    return added


async def test_connecting_puts_booking_in_the_draft_only(
    db_session: AsyncSession, biz: Biz
) -> None:
    connector, install, agent_id = await _world(db_session, biz, tools=[])

    added = await _enable(db_session, biz, connector, install, agent_id)

    assert added == [READ, WRITE], "what the provider did not return is not written"
    draft = await _draft(db_session, biz, agent_id)
    assert draft is not None and {READ, WRITE} <= set(draft.tools)
    assert {READ, WRITE} <= set(draft.spec["tools"])
    async with tenant_scoped_session(db_session, biz.tenant_id):
        active = await db_session.scalar(
            sa.select(AgentConfig).where(
                AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.ACTIVE
            )
        )
    assert active is not None and WRITE not in active.tools, "nothing is published by itself"


async def test_repeating_changes_nothing(db_session: AsyncSession, biz: Biz) -> None:
    connector, install, agent_id = await _world(db_session, biz, tools=[])
    await _enable(db_session, biz, connector, install, agent_id)
    assert await _enable(db_session, biz, connector, install, agent_id) == []


async def test_reading_only_is_not_enough_to_book(db_session: AsyncSession, biz: Biz) -> None:
    connector, install, agent_id = await _world(db_session, biz, tools=[])
    async with tenant_scoped_session(db_session, biz.tenant_id):
        db_session.add(
            AgentConnectorActivation(
                tenant_id=biz.tenant_id,
                agent_id=agent_id,
                connector_id=install.id,
                permission="read",
                settings={},
                created_by="test",
            )
        )
    await db_session.commit()

    await _enable(db_session, biz, connector, install, agent_id)

    async with tenant_scoped_session(db_session, biz.tenant_id):
        row = await db_session.scalar(
            sa.select(AgentConnectorActivation)
            .where(AgentConnectorActivation.agent_id == agent_id)
            .execution_options(populate_existing=True)
        )
    assert row is not None and row.permission == "read_write"


async def _activate(
    db_session: AsyncSession, biz: Biz, install: Any, agent_id: Any, perm: str
) -> None:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        db_session.add(
            AgentConnectorActivation(
                tenant_id=biz.tenant_id,
                agent_id=agent_id,
                connector_id=install.id,
                permission=perm,
                settings={},
                created_by="test",
            )
        )
    await db_session.commit()


async def _after_sync(db_session: AsyncSession, biz: Biz, connector: Any, install: Any) -> None:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await booking_skills.enable_after_sync(
            db_session, connector=connector, install=install, actor="test"
        )
    await db_session.commit()


async def test_a_sync_reaches_an_agent_connected_before_the_tools_existed(
    db_session: AsyncSession, biz: Biz
) -> None:
    connector, install, agent_id = await _world(db_session, biz, tools=[])
    await _activate(db_session, biz, install, agent_id, "read_write")

    await _after_sync(db_session, biz, connector, install)

    draft = await _draft(db_session, biz, agent_id)
    assert draft is not None and {READ, WRITE} <= set(draft.tools)


async def test_a_sync_leaves_an_agent_that_only_reads_or_does_not_use_it(
    db_session: AsyncSession, biz: Biz
) -> None:
    connector, install, agent_id = await _world(db_session, biz, tools=[])
    await _after_sync(db_session, biz, connector, install)
    assert await _draft(db_session, biz, agent_id) is None, "not activated: not this agent"

    await _activate(db_session, biz, install, agent_id, "read")
    await _after_sync(db_session, biz, connector, install)
    assert await _draft(db_session, biz, agent_id) is None, "reading stays reading"


async def test_a_sync_does_not_bring_back_what_a_person_took_out(
    db_session: AsyncSession, biz: Biz
) -> None:
    connector, install, agent_id = await _world(db_session, biz, tools=[])
    await _activate(db_session, biz, install, agent_id, "read_write")
    await _after_sync(db_session, biz, connector, install)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        draft = await db_session.scalar(
            sa.select(AgentConfig).where(
                AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.STAGED
            )
        )
        assert draft is not None
        draft.tools = [t for t in draft.tools if t != WRITE]
    await db_session.commit()

    await _after_sync(db_session, biz, connector, install)

    after = await _draft(db_session, biz, agent_id)
    assert after is not None and WRITE not in after.tools


async def test_an_agent_with_our_calendar_does_not_get_a_second_one(
    db_session: AsyncSession, biz: Biz
) -> None:
    connector, install, agent_id = await _world(db_session, biz, tools=["reservas.create"])
    assert await _enable(db_session, biz, connector, install, agent_id) == []


async def test_a_connector_that_does_not_book_changes_nothing(
    db_session: AsyncSession, biz: Biz, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector, install, agent_id = await _world(db_session, biz, tools=[])
    monkeypatch.delitem(booking_skills.BOOKING_TOOLS, SLUG)
    assert await _enable(db_session, biz, connector, install, agent_id) == []


def test_a_document_takes_a_connectors_slug_and_the_builder_does_not_propose_it() -> None:
    """Sin esto, conectar Calendly no le daba nada a un agente estructurado: el
    documento rechazaba ``CALENDLY_POST_INVITEE`` y ``write_spec`` iguala la lista."""
    from nexus_api.services.agent_spec.schema import SPEC_TOOL_NAME_PATTERN, TOOL_NAME_PATTERN

    assert re.fullmatch(SPEC_TOOL_NAME_PATTERN, "CALENDLY_POST_INVITEE")
    assert re.fullmatch(SPEC_TOOL_NAME_PATTERN, "reservas.create")
    assert not re.fullmatch(SPEC_TOOL_NAME_PATTERN, "calendly post")
    assert not re.fullmatch(TOOL_NAME_PATTERN, "CALENDLY_POST_INVITEE")


async def test_a_real_slug_reaches_a_structured_draft(db_session: AsyncSession, biz: Biz) -> None:
    connector, install, agent_id = await _world(db_session, biz, tools=[])
    slug = "TIENDA_TEST_BOOK"
    async with tenant_scoped_session(db_session, biz.tenant_id):
        db_session.add(
            ToolCatalog(
                name=slug,
                description=slug,
                mcp_server=f"internal:{SLUG}",
                status=ToolStatus.ACTIVE,
                connector_id=connector.id,
                read_only=False,
                destructive=True,
                default_mode="blocked",
            )
        )
    await db_session.commit()
    booking_skills.BOOKING_TOOLS[SLUG] = (slug,)

    assert await _enable(db_session, biz, connector, install, agent_id) == [slug]

    draft = await _draft(db_session, biz, agent_id)
    assert draft is not None and slug in draft.tools and slug in draft.spec["tools"]


def test_calendly_books_with_tools_we_sync_and_never_cancels() -> None:
    calendly = booking_skills.BOOKING_TOOLS["calendly"]
    assert set(calendly) <= set(TOOLKIT_ALLOWLISTS["calendly"])
    assert "CALENDLY_POST_INVITEE" in calendly
    assert not any(
        "CANCEL" in tool or "DELETE" in tool
        for tools in booking_skills.BOOKING_TOOLS.values()
        for tool in tools
    )
