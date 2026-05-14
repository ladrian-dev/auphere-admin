"""Block N — Composio runtime proxy: verifies the proxy delegates to the
client with the correct user_id / connection_id and wraps the result in
the standard envelope shape.

We use ``FakeComposioClient`` so no SDK / network is exercised.
"""

from __future__ import annotations

import uuid

import pytest
from nexus_mcp.servers.composio_proxy.proxy import (
    ComposioProxyTool,
    ComposioToolBlueprint,
)

from nexus_api.core.tenant_context import tenant_context
from nexus_api.services.connectors.composio_client import (
    FakeComposioClient,
)
from nexus_api.services.connectors.runtime import set_composio_client

pytestmark = pytest.mark.asyncio


@pytest.fixture
def fake_composio() -> FakeComposioClient:
    client = FakeComposioClient()
    set_composio_client(client)
    try:
        yield client
    finally:
        set_composio_client(None)


async def test_proxy_invoke_calls_execute_with_invariants(fake_composio):
    tenant = uuid.uuid4()
    fake_composio.force_connect(
        connection_id="conn_1",
        user_id="tenant_cultor",
        toolkit="googlecalendar",
    )
    bp = ComposioToolBlueprint(
        tool_name="googlecalendar.create_event",
        description="Create event",
        input_schema={"type": "object", "properties": {"summary": {"type": "string"}}},
        toolkit_slug="googlecalendar",
        connection_id="conn_1",
        user_id="tenant_cultor",
    )
    proxy = ComposioProxyTool(bp)

    with tenant_context(tenant):
        envelope = await proxy.invoke({"summary": "Corte Juan 15:00"})

    assert envelope["tool"] == "googlecalendar.create_event"
    assert envelope["tenant_id"] == str(tenant)
    assert envelope["status"] == "ok"
    # The Composio fake echoes the args back in ``result.data``.
    assert envelope["result"]["data"]["echo"]["summary"] == "Corte Juan 15:00"

    log = fake_composio.execute_log
    assert len(log) == 1
    assert log[0]["tool_slug"] == "googlecalendar.create_event"
    assert log[0]["user_id"] == "tenant_cultor"
    assert log[0]["connection_id"] == "conn_1"


async def test_proxy_uid_mismatch_is_rejected_by_fake(fake_composio):
    """The FakeComposioClient mirrors the live invariant: passing a
    user_id that doesn't match the connection's recorded user_id raises.
    This is the exact behaviour we rely on for cross-tenant isolation
    when one tenant somehow ends up with another tenant's connection_id."""
    tenant = uuid.uuid4()
    fake_composio.force_connect(
        connection_id="conn_A",
        user_id="tenant_a",
        toolkit="googlecalendar",
    )
    bp = ComposioToolBlueprint(
        tool_name="googlecalendar.create_event",
        description="x",
        input_schema={"type": "object"},
        toolkit_slug="googlecalendar",
        connection_id="conn_A",
        user_id="tenant_b",  # WRONG: not what the connection recorded
    )
    proxy = ComposioProxyTool(bp)

    with tenant_context(tenant):
        from nexus_mcp.base import ToolError

        with pytest.raises(ToolError):
            await proxy.invoke({})


async def test_proxy_to_tool_def_exposes_advertised_schema(fake_composio):
    bp = ComposioToolBlueprint(
        tool_name="notion.create_page",
        description="Create a Notion page",
        input_schema={
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        },
        toolkit_slug="notion",
        connection_id="c",
        user_id="tenant_x",
    )
    proxy = ComposioProxyTool(bp)
    td = proxy.to_tool_def()
    assert td.name == "notion.create_page"
    assert td.description.startswith("Create")
    assert "title" in td.parameters["properties"]
