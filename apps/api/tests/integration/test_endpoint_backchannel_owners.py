"""Integration tests for ``backchannel_owners`` admin endpoints.

Covers per-tenant owner_phone_index CRUD plus the
``auphere_channel_id`` pin (validated against the global channel
registry) and tenant isolation (one phone, one tenant).
"""

from __future__ import annotations

import uuid

import pytest

from nexus_api.db.models import AuphereOwnerChannel

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_ADMIN = {"Authorization": "Bearer test-admin-token"}


async def _insert_channel(db_session, *, phone: str = "+56999000001") -> str:
    row = AuphereOwnerChannel(
        phone_e164=phone,
        display_name="Test Channel",
        provider="meta",
        active=True,
        is_default=False,
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return str(row.id)


class TestList:
    async def test_empty(self, client, db_session, seed_tenants):
        tid = seed_tenants["a"]
        r = await client.get(f"/admin/tenants/{tid}/backchannel/owners", headers=_ADMIN)
        assert r.status_code == 200
        assert r.json() == []


class TestRegister:
    async def test_minimal(self, client, db_session, seed_tenants):
        tid = seed_tenants["a"]
        r = await client.post(
            f"/admin/tenants/{tid}/backchannel/owners",
            headers=_ADMIN,
            json={
                "phone_e164": "+56911111111",
                "user_label": "Luis",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["phone_e164"] == "+56911111111"
        assert body["tenant_id"] == str(tid)
        assert body["auphere_channel_id"] is None
        assert body["active"] is True

    async def test_with_channel_pin(self, client, db_session, seed_tenants):
        cid = await _insert_channel(db_session, phone="+56999000010")
        tid = seed_tenants["a"]
        r = await client.post(
            f"/admin/tenants/{tid}/backchannel/owners",
            headers=_ADMIN,
            json={
                "phone_e164": "+56911111112",
                "auphere_channel_id": cid,
            },
        )
        assert r.status_code == 201
        assert r.json()["auphere_channel_id"] == cid

    async def test_invalid_phone_rejected(self, client, db_session, seed_tenants):
        tid = seed_tenants["a"]
        r = await client.post(
            f"/admin/tenants/{tid}/backchannel/owners",
            headers=_ADMIN,
            json={"phone_e164": "56911111113"},  # no +
        )
        assert r.status_code == 422

    async def test_unknown_channel_id_rejected(self, client, db_session, seed_tenants):
        tid = seed_tenants["a"]
        r = await client.post(
            f"/admin/tenants/{tid}/backchannel/owners",
            headers=_ADMIN,
            json={
                "phone_e164": "+56911111114",
                "auphere_channel_id": str(uuid.uuid4()),
            },
        )
        assert r.status_code == 400

    async def test_inactive_channel_rejected(self, client, db_session, seed_tenants):
        # Insert an inactive channel and try to pin to it.
        row = AuphereOwnerChannel(
            phone_e164="+56999000020",
            display_name="Inactive",
            provider="meta",
            active=False,
            is_default=False,
        )
        db_session.add(row)
        await db_session.commit()
        await db_session.refresh(row)

        tid = seed_tenants["a"]
        r = await client.post(
            f"/admin/tenants/{tid}/backchannel/owners",
            headers=_ADMIN,
            json={
                "phone_e164": "+56911111115",
                "auphere_channel_id": str(row.id),
            },
        )
        assert r.status_code == 400
        assert "inactive" in r.json()["detail"]

    async def test_phone_cross_tenant_collision_returns_409(self, client, db_session, seed_tenants):
        # Register the same phone under tenant A first.
        a, b = seed_tenants["a"], seed_tenants["b"]
        r1 = await client.post(
            f"/admin/tenants/{a}/backchannel/owners",
            headers=_ADMIN,
            json={"phone_e164": "+56911111116"},
        )
        assert r1.status_code == 201
        # Tenant B can't register it.
        r2 = await client.post(
            f"/admin/tenants/{b}/backchannel/owners",
            headers=_ADMIN,
            json={"phone_e164": "+56911111116"},
        )
        assert r2.status_code == 409
        assert str(a) in r2.json()["detail"]


class TestUpdate:
    async def test_change_label(self, client, db_session, seed_tenants):
        tid = seed_tenants["a"]
        await client.post(
            f"/admin/tenants/{tid}/backchannel/owners",
            headers=_ADMIN,
            json={"phone_e164": "+56911111120", "user_label": "old"},
        )
        r = await client.patch(
            f"/admin/tenants/{tid}/backchannel/owners/+56911111120",
            headers=_ADMIN,
            json={"user_label": "new"},
        )
        assert r.status_code == 200
        assert r.json()["user_label"] == "new"

    async def test_pin_channel(self, client, db_session, seed_tenants):
        cid = await _insert_channel(db_session, phone="+56999000030")
        tid = seed_tenants["a"]
        await client.post(
            f"/admin/tenants/{tid}/backchannel/owners",
            headers=_ADMIN,
            json={"phone_e164": "+56911111121"},
        )
        r = await client.patch(
            f"/admin/tenants/{tid}/backchannel/owners/+56911111121",
            headers=_ADMIN,
            json={"auphere_channel_id": cid},
        )
        assert r.status_code == 200
        assert r.json()["auphere_channel_id"] == cid

    async def test_clear_channel_pin(self, client, db_session, seed_tenants):
        cid = await _insert_channel(db_session, phone="+56999000031")
        tid = seed_tenants["a"]
        await client.post(
            f"/admin/tenants/{tid}/backchannel/owners",
            headers=_ADMIN,
            json={
                "phone_e164": "+56911111122",
                "auphere_channel_id": cid,
            },
        )
        r = await client.patch(
            f"/admin/tenants/{tid}/backchannel/owners/+56911111122",
            headers=_ADMIN,
            json={"clear_channel_id": True},
        )
        assert r.status_code == 200
        assert r.json()["auphere_channel_id"] is None

    async def test_deactivate_via_patch(self, client, db_session, seed_tenants):
        tid = seed_tenants["a"]
        await client.post(
            f"/admin/tenants/{tid}/backchannel/owners",
            headers=_ADMIN,
            json={"phone_e164": "+56911111123"},
        )
        r = await client.patch(
            f"/admin/tenants/{tid}/backchannel/owners/+56911111123",
            headers=_ADMIN,
            json={"active": False},
        )
        assert r.status_code == 200
        assert r.json()["active"] is False

    async def test_404_wrong_tenant(self, client, db_session, seed_tenants):
        a, b = seed_tenants["a"], seed_tenants["b"]
        await client.post(
            f"/admin/tenants/{a}/backchannel/owners",
            headers=_ADMIN,
            json={"phone_e164": "+56911111124"},
        )
        # Tenant B can't PATCH tenant A's row.
        r = await client.patch(
            f"/admin/tenants/{b}/backchannel/owners/+56911111124",
            headers=_ADMIN,
            json={"active": False},
        )
        assert r.status_code == 404


class TestDelete:
    async def test_deregister(self, client, db_session, seed_tenants):
        tid = seed_tenants["a"]
        await client.post(
            f"/admin/tenants/{tid}/backchannel/owners",
            headers=_ADMIN,
            json={"phone_e164": "+56911111130"},
        )
        r = await client.delete(
            f"/admin/tenants/{tid}/backchannel/owners/+56911111130",
            headers=_ADMIN,
        )
        assert r.status_code == 204
        # And re-listing returns empty.
        rs = await client.get(f"/admin/tenants/{tid}/backchannel/owners", headers=_ADMIN)
        assert rs.json() == []

    async def test_404_unknown(self, client, db_session, seed_tenants):
        tid = seed_tenants["a"]
        r = await client.delete(
            f"/admin/tenants/{tid}/backchannel/owners/+56999999999",
            headers=_ADMIN,
        )
        assert r.status_code == 404


class TestAuditLog:
    async def test_register_writes_audit(self, client, db_session, seed_tenants):
        from sqlalchemy import select

        from nexus_api.db.models import AuditLog

        tid = seed_tenants["a"]
        await client.post(
            f"/admin/tenants/{tid}/backchannel/owners",
            headers=_ADMIN,
            json={"phone_e164": "+56911111140"},
        )
        rows = await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "backchannel_owner.registered",
                AuditLog.tenant_id == tid,
            )
        )
        entries = list(rows.scalars())
        assert len(entries) == 1
        assert entries[0].after_json["phone_e164"] == "+56911111140"
