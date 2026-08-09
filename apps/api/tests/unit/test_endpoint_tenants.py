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


# ── Block M.1: hard delete (only-after-archive guard) ──────────────────────


async def test_delete_tenant_requires_archived(client, admin_headers, seed_tenants):
    """Active tenants cannot be hard-deleted. The operator must archive
    first (PUT status='archived') — the two-step is the safety."""
    tenant_id = seed_tenants["a"]
    r = await client.delete(f"/admin/tenants/{tenant_id}", headers=admin_headers)
    assert r.status_code == 409, r.text
    assert "archived" in r.text.lower()


async def test_delete_tenant_after_archive_succeeds(
    client, admin_headers, seed_tenants, db_session
):
    tenant_id = seed_tenants["a"]
    archive = await client.put(
        f"/admin/tenants/{tenant_id}",
        headers=admin_headers,
        json={"status": "archived"},
    )
    assert archive.status_code == 200, archive.text

    r = await client.delete(f"/admin/tenants/{tenant_id}", headers=admin_headers)
    assert r.status_code == 204, r.text

    gone = await client.get(f"/admin/tenants/{tenant_id}", headers=admin_headers)
    assert gone.status_code == 404


async def test_delete_tenant_unknown_returns_404(client, admin_headers):
    r = await client.delete(f"/admin/tenants/{uuid.uuid4()}", headers=admin_headers)
    assert r.status_code == 404


async def test_delete_tenant_requires_auth(client, seed_tenants):
    tenant_id = seed_tenants["a"]
    r = await client.delete(f"/admin/tenants/{tenant_id}")
    assert r.status_code == 401


# ── channel roles ──────────────────────────────────────────────────────────
#
# Assigning what a number is for. ``role`` decides which line a
# business-initiated send leaves from; ``agent_enabled`` decides whether the
# line answers. They are independent, and both live in ``channels.config``.


async def _seed_whatsapp_channel(db_session, tenant_id, identifier="+584249018017"):
    from nexus_api.db.models import Channel, ChannelStatus, ChannelType

    ch = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=identifier,
        config={"phone_number_id": "PNID-1"},
        status=ChannelStatus.ACTIVE,
    )
    db_session.add(ch)
    await db_session.commit()
    await db_session.refresh(ch)
    return ch


async def test_patch_channel_sets_role_and_agent_enabled(
    client, admin_headers, seed_tenants, db_session
):
    tenant_id = seed_tenants["a"]
    channel = await _seed_whatsapp_channel(db_session, tenant_id)

    r = await client.patch(
        f"/admin/tenants/{tenant_id}/channels/{channel.id}",
        json={"role": "notifications", "agent_enabled": False},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    config = r.json()["config"]
    assert config["role"] == "notifications"
    assert config["agent_enabled"] is False
    # Meta identifiers written at connect time must survive the edit.
    assert config["phone_number_id"] == "PNID-1"

    audit = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.tenant_id == tenant_id, AuditLog.action == "channel.role_changed"
        )
    )
    assert audit is not None
    assert audit.after_json == {"role": "notifications", "agent_enabled": False}


async def test_patch_channel_leaves_omitted_fields_untouched(
    client, admin_headers, seed_tenants, db_session
):
    tenant_id = seed_tenants["a"]
    channel = await _seed_whatsapp_channel(db_session, tenant_id)

    await client.patch(
        f"/admin/tenants/{tenant_id}/channels/{channel.id}",
        json={"role": "agent", "agent_enabled": False},
        headers=admin_headers,
    )
    r = await client.patch(
        f"/admin/tenants/{tenant_id}/channels/{channel.id}",
        json={"agent_enabled": True},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["config"]["role"] == "agent"
    assert r.json()["config"]["agent_enabled"] is True


async def test_patch_channel_null_role_clears_it(client, admin_headers, seed_tenants, db_session):
    tenant_id = seed_tenants["a"]
    channel = await _seed_whatsapp_channel(db_session, tenant_id)

    await client.patch(
        f"/admin/tenants/{tenant_id}/channels/{channel.id}",
        json={"role": "notifications"},
        headers=admin_headers,
    )
    r = await client.patch(
        f"/admin/tenants/{tenant_id}/channels/{channel.id}",
        json={"role": None},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert "role" not in r.json()["config"]


async def test_patch_channel_rejects_unknown_role(client, admin_headers, seed_tenants, db_session):
    tenant_id = seed_tenants["a"]
    channel = await _seed_whatsapp_channel(db_session, tenant_id)
    r = await client.patch(
        f"/admin/tenants/{tenant_id}/channels/{channel.id}",
        json={"role": "notificaciones"},
        headers=admin_headers,
    )
    assert r.status_code == 422


async def test_patch_channel_unknown_id_is_404(client, admin_headers, seed_tenants):
    r = await client.patch(
        f"/admin/tenants/{seed_tenants['a']}/channels/{uuid.uuid4()}",
        json={"role": "agent"},
        headers=admin_headers,
    )
    assert r.status_code == 404


async def test_patch_channel_of_another_tenant_is_404(
    client, admin_headers, seed_tenants, db_session
):
    """The channel id is caller-supplied. RLS scopes the lookup to the tenant
    in the path, so tenant A cannot retag tenant B's number."""
    b_channel = await _seed_whatsapp_channel(
        db_session, seed_tenants["b"], identifier="+560000000077"
    )
    r = await client.patch(
        f"/admin/tenants/{seed_tenants['a']}/channels/{b_channel.id}",
        json={"role": "notifications"},
        headers=admin_headers,
    )
    assert r.status_code == 404


async def test_patch_channel_requires_admin_token(client, seed_tenants, db_session):
    channel = await _seed_whatsapp_channel(db_session, seed_tenants["a"])
    r = await client.patch(
        f"/admin/tenants/{seed_tenants['a']}/channels/{channel.id}",
        json={"role": "agent"},
    )
    assert r.status_code in (401, 403)
