import pytest

pytestmark = pytest.mark.asyncio


async def test_list_returns_seeded_catalog(client, admin_headers):
    r = await client.get("/admin/tool-catalog", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    names = {t["name"] for t in body}
    assert "booking.check_availability" in names
    assert "queue.join_queue" in names
    # Migration 0018 added ``operator.consult_owner`` (ADR-018) bringing
    # the seed catalog to 22 LLM-facing tools.
    assert "operator.consult_owner" in names
    assert len(body) == 22


async def test_each_tool_has_mcp_server(client, admin_headers):
    r = await client.get("/admin/tool-catalog", headers=admin_headers)
    for tool in r.json():
        assert tool["mcp_server"]


async def test_tool_catalog_requires_auth(client):
    r = await client.get("/admin/tool-catalog")
    assert r.status_code == 401


async def test_include_deprecated_query_param(client, admin_headers):
    r = await client.get("/admin/tool-catalog?include_deprecated=true", headers=admin_headers)
    assert r.status_code == 200


# ── Block M.2: connector binding fields surfaced on the global catalog ─────


async def test_global_catalog_exposes_connector_binding_fields(client, admin_headers):
    """Block L (migration 0013) added connector_id + read_only + destructive
    + requires_consent to tool_catalog. M.2 surfaces them on the API so the
    editor can render the connector context inline."""
    r = await client.get("/admin/tool-catalog", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    for tool in body:
        # Fields are present (may be null/False) on every row.
        assert "connector_id" in tool
        assert "read_only" in tool
        assert "destructive" in tool
        assert "requires_consent" in tool
        assert isinstance(tool["read_only"], bool)
        assert isinstance(tool["destructive"], bool)
