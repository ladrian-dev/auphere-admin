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


# ── Block J: seed-template bootstrap ───────────────────────────────────────


async def test_list_seed_templates_includes_barbershop(client, admin_headers):
    r = await client.get("/admin/seed-templates", headers=admin_headers)
    assert r.status_code == 200
    payload = r.json()
    names = [t["name"] for t in payload]
    assert "barbershop_v1" in names
    bs = next(t for t in payload if t["name"] == "barbershop_v1")
    assert bs["version"] == "1.0.0"
    assert "booking.check_availability" in bs["tools_required"]


async def test_from_seed_renders_and_stages_v1(client, admin_headers, seed_tenants):
    tid = seed_tenants["a"]
    body = {
        "seed_template_ref": "barbershop_v1",
        "placeholders": {
            "tenant.name": "Cultor Barber",
            "tenant.address": "Av. Apoquindo 1234",
            "tenant.timezone": "America/Santiago",
            "tenant.business_hours_label": "Lun-Sáb 10-19",
        },
    }
    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/from-seed",
        headers=admin_headers,
        json=body,
    )
    assert r.status_code == 201, r.text
    config = r.json()
    assert config["status"] == "staged"
    assert config["version"] == 1
    assert config["seed_template_ref"] == "barbershop_v1"
    assert "Cultor Barber" in config["system_prompt_rendered"]
    assert "Av. Apoquindo 1234" in config["system_prompt_rendered"]
    assert "booking.create_appointment" in config["tools"]
    assert config["policies"]["cancellation"]["free_hours_before"] == 24


async def test_from_seed_unknown_template_404(client, admin_headers, seed_tenants):
    tid = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/from-seed",
        headers=admin_headers,
        json={"seed_template_ref": "ghost_v9", "placeholders": {}},
    )
    assert r.status_code == 404


async def test_from_seed_missing_placeholder_400(client, admin_headers, seed_tenants):
    tid = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/from-seed",
        headers=admin_headers,
        json={
            "seed_template_ref": "barbershop_v1",
            "placeholders": {"tenant.name": "Cultor Barber"},
        },
    )
    assert r.status_code == 400
    assert "placeholder" in r.json()["detail"]


# ── Runtime capabilities PATCH (refactor 0035) ───────────────────────


async def _stage_v1(client, admin_headers, tenant_id) -> int:
    response = await client.put(
        f"/admin/tenants/{tenant_id}/agent-config",
        json={"system_prompt_rendered": "v1 prompt", "tools": []},
        headers=admin_headers,
    )
    assert response.status_code == 201
    return int(response.json()["version"])


async def test_patch_runtime_capabilities_updates_staged(
    client, admin_headers, seed_tenants
):
    tid = seed_tenants["a"]
    version = await _stage_v1(client, admin_headers, tid)
    body = {
        "runtime_memory_tool": True,
        "runtime_outcome_grader": True,
        "runtime_mcp_connector": False,
        "runtime_skills": [
            {"skill_id": "skill_abc", "version": "latest"},
            {"skill_id": "skill_def", "version": "3"},
        ],
        "runtime_mcp_servers": [],
    }
    response = await client.patch(
        f"/admin/tenants/{tid}/agent-config/{version}/runtime",
        json=body,
        headers=admin_headers,
    )
    assert response.status_code == 200, response.json()
    data = response.json()
    assert data["runtime_memory_tool"] is True
    assert data["runtime_outcome_grader"] is True
    assert data["runtime_mcp_connector"] is False
    assert len(data["runtime_skills"]) == 2
    assert data["runtime_skills"][0]["skill_id"] == "skill_abc"


async def test_patch_runtime_refuses_active(client, admin_headers, seed_tenants):
    """Capabilities must not be mutated on an ACTIVE version. The
    operator stages a new version and patches that."""
    tid = seed_tenants["a"]
    version = await _stage_v1(client, admin_headers, tid)
    promote = await client.post(
        f"/admin/tenants/{tid}/agent-config/{version}/promote",
        headers=admin_headers,
    )
    assert promote.status_code == 200
    body = {
        "runtime_memory_tool": True,
        "runtime_outcome_grader": True,
        "runtime_mcp_connector": False,
        "runtime_skills": [],
        "runtime_mcp_servers": [],
    }
    response = await client.patch(
        f"/admin/tenants/{tid}/agent-config/{version}/runtime",
        json=body,
        headers=admin_headers,
    )
    assert response.status_code == 409
    assert "STAGED" in response.json()["detail"]


async def test_patch_runtime_returns_404_for_unknown_version(
    client, admin_headers, seed_tenants
):
    tid = seed_tenants["a"]
    body = {
        "runtime_memory_tool": False,
        "runtime_outcome_grader": False,
        "runtime_mcp_connector": False,
        "runtime_skills": [],
        "runtime_mcp_servers": [],
    }
    response = await client.patch(
        f"/admin/tenants/{tid}/agent-config/999/runtime",
        json=body,
        headers=admin_headers,
    )
    assert response.status_code == 404


async def test_patch_runtime_writes_audit_log(
    client, admin_headers, seed_tenants, db_session
):
    """Every runtime capability change must end up in the audit log so
    operators can see who turned memory tool on for a tenant and when.
    """
    from nexus_api.db.models import AuditLog

    tid = seed_tenants["a"]
    version = await _stage_v1(client, admin_headers, tid)
    body = {
        "runtime_memory_tool": True,
        "runtime_outcome_grader": False,
        "runtime_mcp_connector": False,
        "runtime_skills": [],
        "runtime_mcp_servers": [],
    }
    response = await client.patch(
        f"/admin/tenants/{tid}/agent-config/{version}/runtime",
        json=body,
        headers=admin_headers,
    )
    assert response.status_code == 200

    # Bypass RLS to inspect the audit row across tenants.
    from sqlalchemy import text as _text

    await db_session.execute(_text("RESET ROLE"))
    rows = (
        await db_session.execute(
            __import__("sqlalchemy").select(AuditLog).where(
                AuditLog.tenant_id == tid,
                AuditLog.action == "agent_config.runtime.update",
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].after_json["runtime_memory_tool"] is True


async def test_get_available_skills_returns_bundled_list(client, admin_headers):
    """The /admin/skills/available endpoint surfaces the 3 SKILL.md files
    shipped with the worker. uploaded.json being empty (default in repo)
    means skill_id is None for each entry."""
    response = await client.get("/admin/skills/available", headers=admin_headers)
    assert response.status_code == 200
    skills = response.json()
    names = [s["name"] for s in skills]
    assert "anti-hallucination-booking" in names
    assert "whatsapp-24h-window" in names
    assert "escalation-policy" in names
    # uploaded.json starts empty — skill_id None.
    for s in skills:
        assert s["description"]  # frontmatter parsed
        assert s["local_version"]
