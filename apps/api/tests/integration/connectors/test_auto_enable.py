"""auto_enable_connector_tools — step 11 of architecture/connectors.md.

Connecting a connector stages a new agent_config version with the
connector's ``always``-mode (read-only) tools appended to the whitelist.
Destructive tools (``default_mode='blocked'``) are NOT auto-added — the
operator opts them in from the agent editor. The function is idempotent,
a no-op when the tenant has no agent_config yet, and a no-op when the
connector has ``auto_enable_on_connect=false``.

The connector + tools are synthetic so the test pins the function's
logic (always vs blocked) without depending on a specific catalog seed.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from nexus_api.core.tenant_context import apply_tenant_to_session, tenant_context
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    Connector,
    ToolCatalog,
    ToolStatus,
)
from nexus_api.services.connectors.service import auto_enable_connector_tools

pytestmark = pytest.mark.asyncio


async def _seed_connector(db_session, *, auto_enable_on_connect: bool = True) -> Connector:
    """Synthetic connector with two tools: one ``always`` (read-only) and
    one ``blocked`` (destructive). Inserted under the default role —
    ``connectors``/``tool_catalog`` are global, no RLS."""
    connector = Connector(
        slug="test_shop",
        display_name="Test Shop",
        vendor="Test",
        category="ecommerce",
        auth_kind="api_key",
        mcp_server_ref="internal:test_shop",
        auto_enable_on_connect=auto_enable_on_connect,
        auto_enable_destructive=False,
        status="available",
    )
    db_session.add(connector)
    await db_session.flush()
    db_session.add_all(
        [
            ToolCatalog(
                name="test_shop.list_items",
                description="List store items (read-only).",
                mcp_server="internal:test_shop",
                status=ToolStatus.ACTIVE,
                connector_id=connector.id,
                read_only=True,
                destructive=False,
                default_mode="always",
            ),
            ToolCatalog(
                name="test_shop.delete_item",
                description="Delete a store item (destructive).",
                mcp_server="internal:test_shop",
                status=ToolStatus.ACTIVE,
                connector_id=connector.id,
                read_only=False,
                destructive=True,
                default_mode="blocked",
            ),
        ]
    )
    await db_session.flush()
    return connector


async def _seed_active_config(db_session, tenant_id: uuid.UUID, tools: list[str]) -> None:
    db_session.add(
        AgentConfig(
            tenant_id=tenant_id,
            version=1,
            status=AgentConfigStatus.ACTIVE,
            system_prompt_rendered="Sos el asistente de la tienda.",
            channels=[],
            tools=tools,
            policies={},
            seed_template_ref="generic_v1",
        )
    )
    await db_session.flush()


async def test_auto_enable_stages_version_with_always_mode_tools(db_session, seed_tenants) -> None:
    tenant_id = seed_tenants["a"]
    connector = await _seed_connector(db_session)
    await apply_tenant_to_session(db_session, tenant_id)
    with tenant_context(tenant_id):
        await _seed_active_config(db_session, tenant_id, ["client.get_history"])

        added = await auto_enable_connector_tools(
            db_session, tenant_id=tenant_id, connector=connector, actor="test"
        )

        # Only the always-mode (read-only) tool lands; the blocked stays out.
        assert added == ["test_shop.list_items"]

        # A fresh STAGED version was created carrying base + connector tools.
        versions = (
            await db_session.scalars(select(AgentConfig).where(AgentConfig.tenant_id == tenant_id))
        ).all()
        staged = [v for v in versions if v.status == AgentConfigStatus.STAGED]
        assert len(staged) == 1
        new = staged[0]
        assert new.version == 2
        assert set(new.tools) == {"client.get_history", "test_shop.list_items"}
        assert "test_shop.delete_item" not in new.tools  # destructive stays out
        # Prompt / seed ref cloned from the base config.
        assert new.system_prompt_rendered == "Sos el asistente de la tienda."
        assert new.seed_template_ref == "generic_v1"


async def test_auto_enable_is_idempotent(db_session, seed_tenants) -> None:
    tenant_id = seed_tenants["a"]
    connector = await _seed_connector(db_session)
    await apply_tenant_to_session(db_session, tenant_id)
    with tenant_context(tenant_id):
        await _seed_active_config(db_session, tenant_id, ["client.get_history"])

        first = await auto_enable_connector_tools(
            db_session, tenant_id=tenant_id, connector=connector, actor="test"
        )
        assert first == ["test_shop.list_items"]

        # Second run sees the tool already in the latest version → no-op, so
        # reconnecting a connector never spams staged versions.
        second = await auto_enable_connector_tools(
            db_session, tenant_id=tenant_id, connector=connector, actor="test"
        )
        assert second == []
        versions = (
            await db_session.scalars(select(AgentConfig).where(AgentConfig.tenant_id == tenant_id))
        ).all()
        assert len(versions) == 2  # v1 + v2 only — no v3


async def test_auto_enable_noop_without_agent_config(db_session, seed_tenants) -> None:
    """A tenant with no agent_config yet — the operator must apply a seed
    template first. Auto-enable stays a clean no-op rather than failing."""
    tenant_id = seed_tenants["b"]
    connector = await _seed_connector(db_session)
    await apply_tenant_to_session(db_session, tenant_id)
    with tenant_context(tenant_id):
        added = await auto_enable_connector_tools(
            db_session, tenant_id=tenant_id, connector=connector, actor="test"
        )
        assert added == []
        versions = (
            await db_session.scalars(select(AgentConfig).where(AgentConfig.tenant_id == tenant_id))
        ).all()
        assert versions == []


async def test_auto_enable_noop_when_flag_off(db_session, seed_tenants) -> None:
    """A connector with auto_enable_on_connect=false never touches the agent."""
    tenant_id = seed_tenants["a"]
    connector = await _seed_connector(db_session, auto_enable_on_connect=False)
    await apply_tenant_to_session(db_session, tenant_id)
    with tenant_context(tenant_id):
        await _seed_active_config(db_session, tenant_id, ["client.get_history"])

        added = await auto_enable_connector_tools(
            db_session, tenant_id=tenant_id, connector=connector, actor="test"
        )
        assert added == []
        versions = (
            await db_session.scalars(select(AgentConfig).where(AgentConfig.tenant_id == tenant_id))
        ).all()
        assert len(versions) == 1  # v1 only
