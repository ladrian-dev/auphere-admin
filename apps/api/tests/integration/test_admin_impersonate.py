"""F5: admin impersonation sessions, banner liveness, no partner JWT."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.partner_context import apply_admin_to_session
from nexus_api.db.models import AuditLog, OperatorAccount
from nexus_api.db.models.admin_impersonation import AdminImpersonationSession
from nexus_api.services import operator_identity

pytestmark = pytest.mark.asyncio

PASSWORD = "operator-password-1"
EMAIL_A = "ops-a@auphere.test"
EMAIL_B = "ops-b@auphere.test"


async def _make_operator(db_session, *, email: str) -> OperatorAccount:
    unique = f"{email.split('@')[0]}-{uuid.uuid4().hex[:8]}@auphere.test"
    async with db_session.begin():
        return await operator_identity.create_account(
            db_session, email=unique, password=PASSWORD, display_name=email
        )


def _op_headers(admin_headers: dict[str, str], operator_id: uuid.UUID) -> dict[str, str]:
    return {**admin_headers, "X-Operator-Id": str(operator_id)}


async def _start(
    client,
    admin_headers: dict[str, str],
    partner_id: object,
    operator_id: uuid.UUID,
    **body: object,
) -> Any:
    payload: dict[str, object] = {"reason": "soporte ticket AU-1"}
    payload.update(body)
    return await client.post(
        f"/admin/partners/{partner_id}/impersonate",
        headers=_op_headers(admin_headers, operator_id),
        json=payload,
    )


def _assert_no_partner_cred(resp: Any) -> None:
    assert "set-cookie" not in {k.lower() for k in resp.headers}
    text = resp.text.lower()
    assert "nexus-console.session" not in text
    assert "nexus_console" not in text
    if resp.headers.get("content-type", "").startswith("application/json") and resp.content:
        data = resp.json()
        if isinstance(data, dict):
            assert "token" not in data
            assert "jwt" not in data
            assert "access_token" not in data
        blob = json.dumps(data)
        assert "eyJ" not in blob


async def test_reason_shorter_than_eight_is_422(
    client, console_world, admin_headers, db_session
) -> None:
    op = await _make_operator(db_session, email=EMAIL_A)
    a = console_world["a"]
    resp = await _start(client, admin_headers, a["partner_id"], op.id, reason="corto")
    assert resp.status_code == 422, resp.text
    _assert_no_partner_cred(resp)


async def test_ttl_bounds_are_422(client, console_world, admin_headers, db_session) -> None:
    op = await _make_operator(db_session, email=EMAIL_A)
    a = console_world["a"]
    low = await _start(client, admin_headers, a["partner_id"], op.id, ttl_seconds=59)
    high = await _start(client, admin_headers, a["partner_id"], op.id, ttl_seconds=3601)
    extra = await client.post(
        f"/admin/partners/{a['partner_id']}/impersonate",
        headers=_op_headers(admin_headers, op.id),
        json={
            "reason": "soporte ticket AU-1",
            "ttl_seconds": 120,
            "partner_id": str(a["partner_id"]),
        },
    )
    assert low.status_code == 422, low.text
    assert high.status_code == 422, high.text
    assert extra.status_code == 422, extra.text


async def test_start_sets_session_not_partner_jwt(
    client, console_world, admin_headers, db_session
) -> None:
    op = await _make_operator(db_session, email=EMAIL_A)
    a = console_world["a"]
    resp = await _start(client, admin_headers, a["partner_id"], op.id)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["partner_id"] == str(a["partner_id"])
    assert body["operator_id"] == str(op.id)
    assert body["reason"] == "soporte ticket AU-1"
    assert body["ttl_seconds"] == 900
    assert body["revoked_at"] is None
    _assert_no_partner_cred(resp)

    audit = await db_session.scalar(
        sa.select(AuditLog)
        .where(AuditLog.action == "impersonate.start")
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    assert audit is not None
    assert audit.tenant_id is None
    assert audit.actor == "admin:test-adm"
    assert audit.target == f"partner:{a['partner_id']}"


async def test_missing_partner_is_named_404(client, admin_headers, db_session) -> None:
    op = await _make_operator(db_session, email=EMAIL_A)
    missing = uuid.uuid4()
    resp = await _start(client, admin_headers, missing, op.id)
    assert resp.status_code == 404
    assert resp.json() == {"detail": f"partner {missing} not found"}


async def test_foreign_and_missing_session_are_the_same_404(
    client, console_world, admin_headers, db_session
) -> None:
    op_a = await _make_operator(db_session, email=EMAIL_A)
    op_b = await _make_operator(db_session, email=EMAIL_B)
    a = console_world["a"]
    started = await _start(client, admin_headers, a["partner_id"], op_a.id)
    assert started.status_code == 201, started.text
    session_id = started.json()["id"]

    foreign = await client.post(
        f"/admin/impersonate/{session_id}/revoke",
        headers=_op_headers(admin_headers, op_b.id),
    )
    missing = await client.post(
        f"/admin/impersonate/{uuid.uuid4()}/revoke",
        headers=_op_headers(admin_headers, op_b.id),
    )
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": "Unknown impersonation session"}
    _assert_no_partner_cred(foreign)
    _assert_no_partner_cred(missing)


async def test_active_is_this_operator_only_and_expired_hidden(
    client, console_world, admin_headers, db_session
) -> None:
    op_a = await _make_operator(db_session, email=EMAIL_A)
    op_b = await _make_operator(db_session, email=EMAIL_B)
    a, b = console_world["a"], console_world["b"]
    live = await _start(client, admin_headers, a["partner_id"], op_a.id)
    other = await _start(client, admin_headers, b["partner_id"], op_b.id)
    assert live.status_code == 201, live.text
    assert other.status_code == 201, other.text

    listed_a = await client.get(
        "/admin/impersonate/active",
        headers=_op_headers(admin_headers, op_a.id),
    )
    assert listed_a.status_code == 200, listed_a.text
    ids_a = {row["id"] for row in listed_a.json()}
    assert live.json()["id"] in ids_a
    assert other.json()["id"] not in ids_a

    expired_id = uuid.UUID(live.json()["id"])
    async with db_session.begin():
        await apply_admin_to_session(db_session)
        row = await db_session.get(AdminImpersonationSession, expired_id)
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=5)

    after = await client.get(
        "/admin/impersonate/active",
        headers=_op_headers(admin_headers, op_a.id),
    )
    assert after.status_code == 200, after.text
    assert live.json()["id"] not in {row["id"] for row in after.json()}


async def test_recharge_and_block_stay_admin_actor(
    client, console_world, admin_headers, db_session, monkeypatch
) -> None:
    op = await _make_operator(db_session, email=EMAIL_A)
    a, b = console_world["a"], console_world["b"]
    started = await _start(client, admin_headers, a["partner_id"], op.id)
    assert started.status_code == 201, started.text

    recharge = await client.post(
        f"/admin/partners/{a['partner_id']}/wallet/purchased",
        headers=admin_headers,
        json={"qty": 10},
    )
    assert recharge.status_code == 200, recharge.text

    key_a = "sk-vk-partner-a"
    key_b = "sk-vk-partner-b"
    monkeypatch.setenv("LITELLM_PROXY_API_BASE", "http://litellm.proxy.test")
    monkeypatch.setenv(
        "LITELLM_PROXY_VIRTUAL_KEYS",
        json.dumps({str(a["partner_id"]): key_a, str(b["partner_id"]): key_b}),
    )
    monkeypatch.setattr(
        "nexus_api.core.llm_proxy._settings_base_and_keys",
        lambda: (
            "http://litellm.proxy.test",
            json.dumps({str(a["partner_id"]): key_a, str(b["partner_id"]): key_b}),
        ),
    )
    monkeypatch.setattr("nexus_api.core.llm_proxy.litellm_admin_master", lambda: "master")

    async def fake_call(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        class _Resp:
            status_code = 200

            def json(self) -> dict[str, Any]:
                return {"blocked": True, "info": {"blocked": True}}

        return _Resp()

    monkeypatch.setattr("nexus_api.core.llm_proxy.litellm_admin_call", fake_call)

    blocked = await client.post(
        f"/admin/partners/{a['partner_id']}/llm/block",
        headers=admin_headers,
        json={"blocked": True},
    )
    assert blocked.status_code == 200, blocked.text

    actions = (
        await db_session.scalars(
            sa.select(AuditLog).where(AuditLog.action.in_(("wallet.admin_purchased", "llm.block")))
        )
    ).all()
    found = {row.action: row for row in actions}
    assert "wallet.admin_purchased" in found
    assert "llm.block" in found
    assert found["wallet.admin_purchased"].actor == "admin:test-adm"
    assert found["llm.block"].actor == "admin:test-adm"
    assert found["wallet.admin_purchased"].tenant_id is None
    assert found["llm.block"].tenant_id is None


async def test_operator_id_is_not_the_bearer(
    client, console_world, admin_headers, db_session
) -> None:
    a = console_world["a"]
    missing = await client.post(
        f"/admin/partners/{a['partner_id']}/impersonate",
        headers=admin_headers,
        json={"reason": "soporte ticket AU-1"},
    )
    assert missing.status_code == 400, missing.text

    garbage = await client.post(
        f"/admin/partners/{a['partner_id']}/impersonate",
        headers={**admin_headers, "X-Operator-Id": "not-a-principal"},
        json={"reason": "soporte ticket AU-1"},
    )
    assert garbage.status_code == 400, garbage.text
