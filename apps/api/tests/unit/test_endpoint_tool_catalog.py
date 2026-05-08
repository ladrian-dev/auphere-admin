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
    assert len(body) == 21


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
