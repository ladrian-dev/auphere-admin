"""Integration tests for the Auphere channel admin endpoints (Bloque D
Fase 2). Covers CRUD, validation, default-uniqueness, audit logging,
and secret-rotation semantics.

Spec 059 (T040; requisitos 6.2 y 6.4): every write names the panel's
operator (``X-Operator-Id``) and the audit records that person, never a
slice of the admin token; PATCH and DELETE carry a ``reason``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select

from nexus_api.api.admin.operator import operator_actor
from nexus_api.db.models import AuditLog, AuphereOwnerChannel, OperatorAccount
from nexus_api.services import operator_identity

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_ADMIN = {"Authorization": "Bearer test-admin-token"}


@pytest_asyncio.fixture
async def operator(db_session) -> OperatorAccount:
    async with db_session.begin():
        account = await operator_identity.create_account(
            db_session,
            email=f"ops-059-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
            display_name="Ops",
        )
    return account


@pytest.fixture
def ops(operator: OperatorAccount) -> dict[str, str]:
    """The panel's headers: the admin token and the person behind it."""
    return {**_ADMIN, "X-Operator-Id": str(operator.id)}


async def _deactivate(client, headers: dict[str, str], cid: Any, reason: str = "prueba") -> Any:
    return await client.request(
        "DELETE", f"/admin/auphere/channels/{cid}", headers=headers, json={"reason": reason}
    )


# NOTE: every test below takes ``db_session`` even when unused — the
# fixture's teardown is what TRUNCATEs ``auphere_owner_channels``
# between tests. Without it, write-heavy tests leak rows that trip the
# UNIQUE-default constraint in later tests.


class TestList:
    async def test_empty(self, client, db_session):
        r = await client.get("/admin/auphere/channels", headers=_ADMIN)
        assert r.status_code == 200
        assert r.json() == []

    async def test_excludes_inactive_by_default(self, client, db_session, ops):
        await client.post(
            "/admin/auphere/channels",
            headers=ops,
            json={
                "phone_e164": "+56000000001",
                "display_name": "A",
                "provider": "meta",
            },
        )
        b = await client.post(
            "/admin/auphere/channels",
            headers=ops,
            json={
                "phone_e164": "+56000000002",
                "display_name": "B",
                "provider": "meta",
            },
        )
        # Deactivate B.
        b_id = b.json()["id"]
        await _deactivate(client, ops, b_id)

        r = await client.get("/admin/auphere/channels", headers=_ADMIN)
        phones = [c["phone_e164"] for c in r.json()]
        assert phones == ["+56000000001"]

        r_all = await client.get("/admin/auphere/channels?include_inactive=true", headers=_ADMIN)
        phones_all = {c["phone_e164"] for c in r_all.json()}
        assert phones_all == {"+56000000001", "+56000000002"}


class TestCreate:
    async def test_minimal_payload(self, client, db_session, ops):
        r = await client.post(
            "/admin/auphere/channels",
            headers=ops,
            json={
                "phone_e164": "+56000000010",
                "display_name": "Auphere CL",
                "provider": "meta",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["phone_e164"] == "+56000000010"
        assert body["active"] is True
        assert body["is_default"] is False
        assert body["has_webhook_secret"] is False
        assert body["has_access_token"] is False

    async def test_with_access_token(self, client, db_session, ops):
        r = await client.post(
            "/admin/auphere/channels",
            headers=ops,
            json={
                "phone_e164": "+56000000017",
                "display_name": "Auphere CL",
                "provider": "meta",
                "provider_phone_id": "123456789",
                "access_token": "EAAsystemusertoken",
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["has_access_token"] is True
        assert body["provider_phone_id"] == "123456789"
        # Stored encrypted; decryptable via the Fernet column type.
        row = await db_session.get(AuphereOwnerChannel, uuid.UUID(body["id"]))
        assert row is not None
        assert row.access_token_encrypted == b"EAAsystemusertoken"

    async def test_with_per_channel_secret(self, client, db_session, ops):
        r = await client.post(
            "/admin/auphere/channels",
            headers=ops,
            json={
                "phone_e164": "+56000000011",
                "display_name": "Auphere CL",
                "provider": "meta",
                "webhook_secret": "channel-specific-hmac",
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["has_webhook_secret"] is True
        # Verify the secret is actually stored encrypted by reading the
        # row directly — the bytes column should be populated and
        # decryptable.
        row = await db_session.get(AuphereOwnerChannel, uuid.UUID(body["id"]))
        assert row is not None
        assert row.webhook_secret_encrypted == b"channel-specific-hmac"

    async def test_invalid_phone_rejected(self, client, db_session, ops):
        r = await client.post(
            "/admin/auphere/channels",
            headers=ops,
            json={
                "phone_e164": "56912345678",  # missing leading +
                "display_name": "bad",
                "provider": "meta",
            },
        )
        assert r.status_code == 422

    async def test_invalid_provider_rejected(self, client, db_session, ops):
        r = await client.post(
            "/admin/auphere/channels",
            headers=ops,
            json={
                "phone_e164": "+56000000012",
                "display_name": "x",
                "provider": "telegram",
            },
        )
        assert r.status_code == 422

    async def test_country_code_uppercased(self, client, db_session, ops):
        r = await client.post(
            "/admin/auphere/channels",
            headers=ops,
            json={
                "phone_e164": "+56000000013",
                "display_name": "CL",
                "provider": "meta",
                "country_code": "cl",
            },
        )
        assert r.json()["country_code"] == "CL"

    async def test_duplicate_phone_returns_409(self, client, db_session, ops):
        await client.post(
            "/admin/auphere/channels",
            headers=ops,
            json={
                "phone_e164": "+56000000014",
                "display_name": "first",
                "provider": "meta",
            },
        )
        r = await client.post(
            "/admin/auphere/channels",
            headers=ops,
            json={
                "phone_e164": "+56000000014",
                "display_name": "second",
                "provider": "meta",
            },
        )
        assert r.status_code == 409

    async def test_duplicate_default_per_provider_returns_409(self, client, db_session, ops):
        await client.post(
            "/admin/auphere/channels",
            headers=ops,
            json={
                "phone_e164": "+56000000015",
                "display_name": "first default",
                "provider": "meta",
                "is_default": True,
            },
        )
        r = await client.post(
            "/admin/auphere/channels",
            headers=ops,
            json={
                "phone_e164": "+56000000016",
                "display_name": "second default",
                "provider": "meta",
                "is_default": True,
            },
        )
        assert r.status_code == 409


class TestUpdate:
    async def _make(self, client, ops, **overrides) -> str:
        payload = {
            "phone_e164": overrides.pop("phone_e164", "+56000000020"),
            "display_name": overrides.pop("display_name", "name"),
            "provider": overrides.pop("provider", "meta"),
        }
        payload.update(overrides)
        r = await client.post("/admin/auphere/channels", headers=ops, json=payload)
        return r.json()["id"]

    async def test_patch_display_name(self, client, db_session, ops):
        cid = await self._make(client, ops)
        r = await client.patch(
            f"/admin/auphere/channels/{cid}",
            headers=ops,
            json={"reason": "prueba", "display_name": "new name"},
        )
        assert r.status_code == 200
        assert r.json()["display_name"] == "new name"

    async def test_rotate_secret_via_patch(self, client, db_session, ops):
        cid = await self._make(client, ops, phone_e164="+56000000021")
        r = await client.patch(
            f"/admin/auphere/channels/{cid}",
            headers=ops,
            json={"reason": "prueba", "webhook_secret": "rotated"},
        )
        assert r.status_code == 200
        row = await db_session.get(AuphereOwnerChannel, uuid.UUID(cid))
        assert row is not None and row.webhook_secret_encrypted == b"rotated"

    async def test_clear_secret_via_empty_string(self, client, db_session, ops):
        cid = await self._make(client, ops, phone_e164="+56000000022", webhook_secret="initial")
        r = await client.patch(
            f"/admin/auphere/channels/{cid}",
            headers=ops,
            json={"reason": "prueba", "webhook_secret": ""},
        )
        assert r.status_code == 200
        row = await db_session.get(AuphereOwnerChannel, uuid.UUID(cid))
        assert row is not None and row.webhook_secret_encrypted is None

    async def test_rotate_access_token_via_patch(self, client, db_session, ops):
        cid = await self._make(client, ops, phone_e164="+56000000025")
        r = await client.patch(
            f"/admin/auphere/channels/{cid}",
            headers=ops,
            json={"reason": "prueba", "access_token": "EAArotated"},
        )
        assert r.status_code == 200
        assert r.json()["has_access_token"] is True
        row = await db_session.get(AuphereOwnerChannel, uuid.UUID(cid))
        assert row is not None and row.access_token_encrypted == b"EAArotated"

    async def test_clear_access_token_via_empty_string(self, client, db_session, ops):
        cid = await self._make(client, ops, phone_e164="+56000000026", access_token="EAAinitial")
        r = await client.patch(
            f"/admin/auphere/channels/{cid}",
            headers=ops,
            json={"reason": "prueba", "access_token": ""},
        )
        assert r.status_code == 200
        assert r.json()["has_access_token"] is False
        row = await db_session.get(AuphereOwnerChannel, uuid.UUID(cid))
        assert row is not None and row.access_token_encrypted is None

    async def test_promote_to_default_blocked_when_other_exists(self, client, db_session, ops):
        await self._make(
            client,
            ops,
            phone_e164="+56000000023",
            is_default=True,
        )
        other = await self._make(client, ops, phone_e164="+56000000024")
        r = await client.patch(
            f"/admin/auphere/channels/{other}",
            headers=ops,
            json={"reason": "prueba", "is_default": True},
        )
        assert r.status_code == 409


class TestDeactivate:
    async def test_sets_active_false_and_clears_default(self, client, db_session, ops):
        r = await client.post(
            "/admin/auphere/channels",
            headers=ops,
            json={
                "phone_e164": "+56000000030",
                "display_name": "to-deactivate",
                "provider": "meta",
                "is_default": True,
            },
        )
        cid = r.json()["id"]
        d = await _deactivate(client, ops, cid)
        assert d.status_code == 200
        body = d.json()
        assert body["active"] is False
        assert body["is_default"] is False

    async def test_404_unknown(self, client, db_session, ops):
        r = await _deactivate(client, ops, uuid.uuid4())
        assert r.status_code == 404


class TestAuditLog:
    async def test_create_writes_platform_audit_row(self, client, db_session, ops):
        await client.post(
            "/admin/auphere/channels",
            headers=ops,
            json={
                "phone_e164": "+56000000040",
                "display_name": "audited",
                "provider": "meta",
            },
        )
        # Bypass RLS via direct SELECT.
        rows = await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "auphere_channel.created",
                AuditLog.target == "auphere_channel:+56000000040",
            )
        )
        entries = list(rows.scalars())
        assert len(entries) == 1
        entry = entries[0]
        # Platform-level: tenant_id MUST be NULL.
        assert entry.tenant_id is None
        assert entry.after_json is not None
        assert entry.after_json["phone_e164"] == "+56000000040"
        assert entry.after_json["has_webhook_secret"] is False

    async def test_update_writes_before_and_after(self, client, db_session, ops):
        c = await client.post(
            "/admin/auphere/channels",
            headers=ops,
            json={
                "phone_e164": "+56000000041",
                "display_name": "v1",
                "provider": "meta",
            },
        )
        cid = c.json()["id"]
        await client.patch(
            f"/admin/auphere/channels/{cid}",
            headers=ops,
            json={"reason": "prueba", "display_name": "v2"},
        )
        rows = await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "auphere_channel.updated",
                AuditLog.target == "auphere_channel:+56000000041",
            )
        )
        entry = rows.scalar_one()
        assert entry.before_json["display_name"] == "v1"
        assert entry.after_json["display_name"] == "v2"


class TestOperatorAndReason:
    """Spec 059 (T040, 6.2, 6.4)."""

    async def _make(self, client, ops) -> str:
        r = await client.post(
            "/admin/auphere/channels",
            headers=ops,
            json={"phone_e164": "+56000000050", "display_name": "Auphere CL", "provider": "meta"},
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]

    async def test_every_write_needs_the_operator(self, client, db_session, ops):
        body = {"phone_e164": "+56000000051", "display_name": "x", "provider": "meta"}
        missing = await client.post("/admin/auphere/channels", headers=_ADMIN, json=body)
        assert missing.status_code == 400
        not_one = await client.post(
            "/admin/auphere/channels",
            headers={**_ADMIN, "X-Operator-Id": str(uuid.uuid4())},
            json=body,
        )
        assert not_one.status_code == 400
        cid = await self._make(client, ops)
        patch = await client.patch(
            f"/admin/auphere/channels/{cid}",
            headers=_ADMIN,
            json={"display_name": "y", "reason": "prueba"},
        )
        assert patch.status_code == 400
        delete = await _deactivate(client, _ADMIN, cid)
        assert delete.status_code == 400
        assert (await client.get(f"/admin/auphere/channels/{cid}", headers=_ADMIN)).json()[
            "active"
        ] is True

    async def test_the_operator_alone_is_not_the_panel(self, client, db_session, ops):
        """Without the admin token, naming an operator opens nothing."""
        alone = {"X-Operator-Id": ops["X-Operator-Id"]}
        body = {"phone_e164": "+56000000052", "display_name": "x", "provider": "meta"}
        assert (
            await client.post("/admin/auphere/channels", headers=alone, json=body)
        ).status_code in (
            401,
            403,
        )
        cid = await self._make(client, ops)
        patch = await client.patch(
            f"/admin/auphere/channels/{cid}", headers=alone, json={"reason": "x", "active": False}
        )
        assert patch.status_code in (401, 403)
        assert (await _deactivate(client, alone, cid)).status_code in (401, 403)

    async def test_patch_and_delete_need_a_reason(self, client, db_session, ops):
        cid = await self._make(client, ops)
        for body in ({"display_name": "y"}, {"display_name": "y", "reason": ""}):
            r = await client.patch(f"/admin/auphere/channels/{cid}", headers=ops, json=body)
            assert r.status_code == 422, r.text
        no_body = await client.request("DELETE", f"/admin/auphere/channels/{cid}", headers=ops)
        assert no_body.status_code == 422
        empty = await _deactivate(client, ops, cid, reason="  ")
        assert empty.status_code == 422
        assert (await client.get(f"/admin/auphere/channels/{cid}", headers=_ADMIN)).json()[
            "active"
        ] is True

    async def test_patch_changes_the_token_and_the_meta_number_id(
        self, client, db_session, ops, operator
    ):
        cid = await self._make(client, ops)
        r = await client.patch(
            f"/admin/auphere/channels/{cid}",
            headers=ops,
            json={
                "access_token": "EAAnuevo",
                "provider_phone_id": "998877",
                "reason": "El token caducó",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["provider_phone_id"] == "998877"
        assert r.json()["has_access_token"] is True
        row = await db_session.get(AuphereOwnerChannel, uuid.UUID(cid))
        assert row is not None and row.access_token_encrypted == b"EAAnuevo"

        entry = (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.action == "auphere_channel.updated",
                    AuditLog.target == "auphere_channel:+56000000050",
                )
            )
        ).scalar_one()
        assert entry.actor == operator_actor(operator)
        assert not entry.actor.startswith("admin:")
        assert entry.after_json["reason"] == "El token caducó"
        assert entry.after_json["provider_phone_id"] == "998877"
        assert "EAAnuevo" not in str(entry.after_json) + str(entry.before_json)

    async def test_create_and_deactivate_name_the_person(self, client, db_session, ops, operator):
        cid = await self._make(client, ops)
        assert (await _deactivate(client, ops, cid, reason="Ya no lo usamos")).status_code == 200
        rows = (
            (
                await db_session.execute(
                    select(AuditLog)
                    .where(AuditLog.target == "auphere_channel:+56000000050")
                    .order_by(AuditLog.created_at)
                )
            )
            .scalars()
            .all()
        )
        assert [r.action for r in rows] == [
            "auphere_channel.created",
            "auphere_channel.deactivated",
        ]
        assert {r.actor for r in rows} == {operator_actor(operator)}
        assert rows[1].after_json["reason"] == "Ya no lo usamos"
