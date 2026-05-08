import uuid

import pytest

pytestmark = pytest.mark.asyncio


async def test_list_tenants_empty(client, admin_headers):
    response = await client.get("/admin/tenants", headers=admin_headers)
    assert response.status_code == 200
    # may be empty or contain seeded — at least returns a list
    assert isinstance(response.json(), list)


async def test_list_tenants_includes_seeded(client, admin_headers, seed_tenants):
    response = await client.get("/admin/tenants", headers=admin_headers)
    slugs = {t["slug"] for t in response.json()}
    assert {"tenant-a", "tenant-b"} <= slugs


async def test_get_tenant_by_id(client, admin_headers, seed_tenants):
    response = await client.get(f"/admin/tenants/{seed_tenants['a']}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["slug"] == "tenant-a"


async def test_get_tenant_unknown(client, admin_headers):
    response = await client.get(f"/admin/tenants/{uuid.uuid4()}", headers=admin_headers)
    assert response.status_code == 404


async def test_get_tenant_invalid_uuid_returns_422(client, admin_headers):
    response = await client.get("/admin/tenants/not-a-uuid", headers=admin_headers)
    assert response.status_code == 422
