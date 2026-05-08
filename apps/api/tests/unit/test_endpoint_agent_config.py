import uuid

import pytest

pytestmark = pytest.mark.asyncio


async def test_get_returns_empty_bundle_when_no_versions(client, admin_headers, seed_tenants):
    tid = seed_tenants["a"]
    response = await client.get(f"/admin/tenants/{tid}/agent-config", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["active"] is None
    assert body["versions"] == []


async def test_get_returns_404_for_unknown_tenant(client, admin_headers):
    response = await client.get(
        f"/admin/tenants/{uuid.uuid4()}/agent-config", headers=admin_headers
    )
    assert response.status_code == 404


async def test_put_creates_staged_v1(client, admin_headers, seed_tenants):
    tid = seed_tenants["a"]
    body = {
        "system_prompt_rendered": "You are an agent for Cultor Barber.",
        "channels": [],
        "tools": ["booking.check_availability"],
        "policies": {"cancellation": "24h"},
        "seed_template_ref": "barbershop_v1",
    }
    response = await client.put(
        f"/admin/tenants/{tid}/agent-config", json=body, headers=admin_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["version"] == 1
    assert data["status"] == "staged"
    assert data["seed_template_ref"] == "barbershop_v1"


async def test_put_rejects_unknown_tool(client, admin_headers, seed_tenants):
    tid = seed_tenants["a"]
    body = {
        "system_prompt_rendered": "x",
        "tools": ["does.not.exist"],
    }
    response = await client.put(
        f"/admin/tenants/{tid}/agent-config", json=body, headers=admin_headers
    )
    assert response.status_code == 409


async def test_put_rejects_empty_prompt(client, admin_headers, seed_tenants):
    tid = seed_tenants["a"]
    body = {"system_prompt_rendered": "", "tools": []}
    response = await client.put(
        f"/admin/tenants/{tid}/agent-config", json=body, headers=admin_headers
    )
    assert response.status_code == 422


async def test_promote_workflow(client, admin_headers, seed_tenants):
    tid = seed_tenants["a"]
    # stage v1
    r1 = await client.put(
        f"/admin/tenants/{tid}/agent-config",
        json={"system_prompt_rendered": "v1", "tools": []},
        headers=admin_headers,
    )
    assert r1.status_code == 201
    # promote v1
    r2 = await client.post(f"/admin/tenants/{tid}/agent-config/1/promote", headers=admin_headers)
    assert r2.status_code == 200
    assert r2.json()["status"] == "active"

    # bundle reflects active
    r3 = await client.get(f"/admin/tenants/{tid}/agent-config", headers=admin_headers)
    assert r3.json()["active"]["version"] == 1


async def test_rollback_workflow(client, admin_headers, seed_tenants):
    tid = seed_tenants["a"]
    for prompt in ("v1", "v2"):
        await client.put(
            f"/admin/tenants/{tid}/agent-config",
            json={"system_prompt_rendered": prompt, "tools": []},
            headers=admin_headers,
        )
    await client.post(f"/admin/tenants/{tid}/agent-config/1/promote", headers=admin_headers)
    await client.post(f"/admin/tenants/{tid}/agent-config/2/promote", headers=admin_headers)
    # Rollback to v1
    r = await client.post(f"/admin/tenants/{tid}/agent-config/1/rollback", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["version"] == 1
    assert r.json()["status"] == "active"


async def test_promote_unknown_version_returns_409(client, admin_headers, seed_tenants):
    tid = seed_tenants["a"]
    r = await client.post(f"/admin/tenants/{tid}/agent-config/999/promote", headers=admin_headers)
    assert r.status_code == 409


async def test_endpoints_require_auth(client, seed_tenants):
    tid = seed_tenants["a"]
    r = await client.get(f"/admin/tenants/{tid}/agent-config")
    assert r.status_code == 401
    r = await client.put(
        f"/admin/tenants/{tid}/agent-config",
        json={"system_prompt_rendered": "x"},
    )
    assert r.status_code == 401
    r = await client.post(f"/admin/tenants/{tid}/agent-config/1/promote")
    assert r.status_code == 401


async def test_versions_listed_in_descending_order(client, admin_headers, seed_tenants):
    tid = seed_tenants["a"]
    for prompt in ("v1", "v2", "v3"):
        await client.put(
            f"/admin/tenants/{tid}/agent-config",
            json={"system_prompt_rendered": prompt, "tools": []},
            headers=admin_headers,
        )
    r = await client.get(f"/admin/tenants/{tid}/agent-config", headers=admin_headers)
    versions = [v["version"] for v in r.json()["versions"]]
    assert versions == [3, 2, 1]
