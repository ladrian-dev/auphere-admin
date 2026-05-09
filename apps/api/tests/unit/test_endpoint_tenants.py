import uuid

import pytest
from sqlalchemy import select

from nexus_api.db.models import AuditLog

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


# ── Block J: wizard endpoints ──────────────────────────────────────────────


async def test_check_slug_available(client, admin_headers):
    r = await client.get("/admin/tenants/check-slug?slug=brand-new-shop", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == {"slug": "brand-new-shop", "available": True}


async def test_check_slug_taken(client, admin_headers, seed_tenants):
    r = await client.get("/admin/tenants/check-slug?slug=tenant-a", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == {"slug": "tenant-a", "available": False}


async def test_create_tenant_minimal(client, admin_headers, db_session):
    body = {"slug": "cultor-barber", "name": "Cultor Barber", "plan": "pro"}
    r = await client.post("/admin/tenants", headers=admin_headers, json=body)
    assert r.status_code == 201, r.text
    payload = r.json()
    assert payload["slug"] == "cultor-barber"
    assert payload["plan"] == "pro"
    assert payload["status"] == "active"
    assert payload["timezone"] == "UTC"
    assert payload["cost_alert_threshold_usd_per_day"] == "40.00"

    # Audit row written under the new tenant id (RLS scope).
    tenant_id = uuid.UUID(payload["id"])
    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant_id, AuditLog.action == "tenant.create"
            )
        )
    ).scalar_one()
    assert audit.after_json is not None
    assert audit.after_json["slug"] == "cultor-barber"


async def test_create_tenant_full(client, admin_headers):
    body = {
        "slug": "cultor-barber-full",
        "name": "Cultor Barber",
        "plan": "pro",
        "market": "cl",  # lowercase → upcased by the validator
        "timezone": "America/Santiago",
        "owner_email": "diego@example.com",
        "owner_phone": "+56911112222",
        "business_hours": {"monday": "10:00-19:00"},
        "cost_alert_threshold_usd_per_day": 60,
    }
    r = await client.post("/admin/tenants", headers=admin_headers, json=body)
    assert r.status_code == 201, r.text
    payload = r.json()
    assert payload["market"] == "CL"
    assert payload["timezone"] == "America/Santiago"
    assert payload["owner_phone"] == "+56911112222"
    # NUMERIC(10,2) column → ".00" suffix on round-trip.
    assert payload["cost_alert_threshold_usd_per_day"] == "60.00"


async def test_create_tenant_slug_conflict(client, admin_headers, seed_tenants):
    body = {"slug": "tenant-a", "name": "Cultor Barber", "plan": "pro"}
    r = await client.post("/admin/tenants", headers=admin_headers, json=body)
    assert r.status_code == 409
    assert "already taken" in r.json()["detail"]


async def test_create_tenant_extra_fields_rejected(client, admin_headers):
    body = {"slug": "x-y", "name": "X", "plan": "pro", "ghost_field": "boo"}
    r = await client.post("/admin/tenants", headers=admin_headers, json=body)
    assert r.status_code == 422


async def test_create_tenant_invalid_phone(client, admin_headers):
    body = {"slug": "x-y", "name": "X", "plan": "pro", "owner_phone": "56-9-1111-2222"}
    r = await client.post("/admin/tenants", headers=admin_headers, json=body)
    assert r.status_code == 422


async def test_create_tenant_invalid_timezone(client, admin_headers):
    body = {"slug": "x-y", "name": "X", "plan": "pro", "timezone": "Mars/Olympus"}
    r = await client.post("/admin/tenants", headers=admin_headers, json=body)
    assert r.status_code == 422


async def test_create_tenant_invalid_plan(client, admin_headers):
    body = {"slug": "x-y", "name": "X", "plan": "enterprise"}
    r = await client.post("/admin/tenants", headers=admin_headers, json=body)
    assert r.status_code == 422


async def test_create_tenant_requires_auth(client):
    body = {"slug": "x-y", "name": "X", "plan": "pro"}
    r = await client.post("/admin/tenants", json=body)
    assert r.status_code == 401


async def test_update_tenant_partial(client, admin_headers, seed_tenants, db_session):
    tenant_id = seed_tenants["a"]
    r = await client.put(
        f"/admin/tenants/{tenant_id}",
        headers=admin_headers,
        json={"status": "paused", "cost_alert_threshold_usd_per_day": 80},
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["status"] == "paused"
    assert payload["cost_alert_threshold_usd_per_day"] == "80.00"

    # Other fields untouched.
    assert payload["slug"] == "tenant-a"

    # Audit row captures only what changed.
    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant_id, AuditLog.action == "tenant.update"
            )
        )
    ).scalar_one()
    assert set(audit.before_json.keys()) == {"status", "cost_alert_threshold_usd_per_day"}
    assert audit.after_json["status"] == "paused"


async def test_update_tenant_no_change_is_noop(client, admin_headers, seed_tenants, db_session):
    tenant_id = seed_tenants["a"]
    r = await client.put(f"/admin/tenants/{tenant_id}", headers=admin_headers, json={})
    assert r.status_code == 200
    audits = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.tenant_id == tenant_id, AuditLog.action == "tenant.update"
                )
            )
        )
        .scalars()
        .all()
    )
    assert audits == []


async def test_update_tenant_unknown(client, admin_headers):
    r = await client.put(
        f"/admin/tenants/{uuid.uuid4()}",
        headers=admin_headers,
        json={"status": "paused"},
    )
    assert r.status_code == 404
