import pytest

pytestmark = pytest.mark.asyncio


async def test_admin_endpoint_requires_authorization(client):
    response = await client.get("/admin/tenants")
    assert response.status_code == 401


async def test_admin_endpoint_rejects_wrong_token(client):
    response = await client.get("/admin/tenants", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


async def test_admin_endpoint_accepts_correct_token(client, admin_headers):
    response = await client.get("/admin/tenants", headers=admin_headers)
    assert response.status_code == 200


async def test_admin_endpoint_rejects_non_bearer_scheme(client):
    response = await client.get(
        "/admin/tenants", headers={"Authorization": "Basic test-admin-token"}
    )
    assert response.status_code == 401


async def test_admin_endpoint_rejects_malformed_header(client):
    response = await client.get("/admin/tenants", headers={"Authorization": "Bearer"})
    # FastAPI returns 401 because token is empty.
    assert response.status_code == 401
