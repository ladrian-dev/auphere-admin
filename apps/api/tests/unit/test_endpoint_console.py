"""Functional tests of the partner console surface (``/console/*``).

Isolation is covered in ``tests/isolation/test_console_*``; this file pins
BEHAVIOUR: lifecycle transitions, the quota 409 with no side effects
(CP-06), publish/rollback leaving ``console.agent.publish`` (CP-12), the
team rules (last owner, self-change), keys shown once (CP-27), usage in
units without cost (C9), audit summaries (CP-28), invitation accept flow
through the service token (CP-02/CP-26).
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    Invoice,
    Message,
    MessageDirection,
    MessageStatus,
    Partner,
    PartnerTenant,
    Tenant,
    TenantStatus,
)
from tests.conftest import add_console_member, mint_console_token

pytestmark = pytest.mark.asyncio


def _svc_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {mint_console_token(user_id='bff', partner_id=None, service=True)}"
    }


# ── clients: create + quota (CP-06) ────────────────────────────────────


async def test_create_client_and_quota_409_leaves_nothing_behind(
    client, console_world, db_session
) -> None:
    a = console_world["a"]  # max_clients=3, 1 in use
    for i in (2, 3):
        r = await client.post(
            "/console/clients",
            headers=a["headers"](),
            json={"external_client_ref": f"c{i}", "name": f"Client {i}"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["quota"]["used_clients"] == i
    assert (await client.get("/console/me", headers=a["headers"]())).json()["quota"] == {
        "max_clients": 3,
        "used_clients": 3,
        "remaining_clients": 0,
        "max_channels_per_client": 2,
    }

    tenants_before = await db_session.scalar(sa.select(sa.func.count()).select_from(Tenant))
    mappings_before = await db_session.scalar(sa.select(sa.func.count()).select_from(PartnerTenant))
    audit_before = await db_session.scalar(
        sa.text("SELECT count(*) FROM embed_audit_log WHERE event = 'client.provisioned'")
    )

    r = await client.post(
        "/console/clients",
        headers=a["headers"](),
        json={"external_client_ref": "c4", "name": "Client 4"},
    )
    assert r.status_code == 409, r.text
    assert "3 of 3" in r.json()["detail"]
    assert "Archive a client" in r.json()["detail"]

    # No side effects: no tenant, no mapping, no audit row.
    assert await db_session.scalar(sa.select(sa.func.count()).select_from(Tenant)) == tenants_before
    assert (
        await db_session.scalar(sa.select(sa.func.count()).select_from(PartnerTenant))
        == mappings_before
    )
    assert (
        await db_session.scalar(
            sa.text("SELECT count(*) FROM embed_audit_log WHERE event = 'client.provisioned'")
        )
        == audit_before
    )

    # Existing refs stay idempotent and do not consume quota.
    again = await client.post(
        "/console/clients",
        headers=a["headers"](),
        json={"external_client_ref": "c2", "name": "Client 2"},
    )
    assert again.status_code == 201

    # Archiving frees a slot.
    r = await client.post(
        "/console/clients/c3/status", headers=a["headers"](), json={"status": "archived"}
    )
    assert r.status_code == 200
    r = await client.post(
        "/console/clients",
        headers=a["headers"](),
        json={"external_client_ref": "c4", "name": "Client 4"},
    )
    assert r.status_code == 201, r.text


async def test_partner_api_shares_the_quota(client, console_world, db_session) -> None:
    """The public ``/v2/partners/clients`` route goes through the same
    service: the API key hits the same 409."""
    from nexus_api.core.partner_keys import generate_api_key
    from nexus_api.db.models import PartnerApiKey

    a = console_world["a"]
    await db_session.execute(
        sa.update(Partner).where(Partner.id == a["partner_id"]).values(max_clients=1)
    )
    generated = generate_api_key()
    db_session.add(
        PartnerApiKey(
            id=uuid.uuid4(),
            partner_id=a["partner_id"],
            prefix_snippet=generated.prefix_snippet,
            key_hash=generated.key_hash,
            scopes=["provision"],
            allowed_origins=[],
        )
    )
    await db_session.commit()
    headers = {"Authorization": f"Bearer {generated.plaintext}"}
    # Existing ref → idempotent 200.
    ok = await client.post(
        "/v2/partners/clients", headers=headers, json={"external_client_ref": a["ref"], "name": "x"}
    )
    assert ok.status_code == 200, ok.text
    # New ref → over quota.
    over = await client.post(
        "/v2/partners/clients", headers=headers, json={"external_client_ref": "new", "name": "x"}
    )
    assert over.status_code == 409, over.text


async def test_client_detail_update_and_transitions(client, console_world, db_session) -> None:
    a = console_world["a"]
    h = a["headers"]
    detail = await client.get(f"/console/clients/{a['ref']}", headers=h())
    assert detail.status_code == 200
    body = detail.json()
    assert body["health"] == {
        "whatsapp_connected": False,
        "display_phone_number": None,
        "agent_version": None,
        "agent_configured": False,
        "ready": False,
        "missing": ["agent", "whatsapp"],
    }
    assert "tenant_id" not in body

    upd = await client.patch(
        f"/console/clients/{a['ref']}",
        headers=h(),
        json={"name": "Renamed", "timezone": "Europe/Madrid"},
    )
    assert upd.status_code == 200 and upd.json()["name"] == "Renamed"
    assert upd.json()["timezone"] == "Europe/Madrid"

    # active → paused → active; active → archived → active (reversible)
    for target in ("paused", "active", "archived", "active"):
        r = await client.post(
            f"/console/clients/{a['ref']}/status", headers=h(), json={"status": target}
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == target
    # provisioning → active requires an agent
    await db_session.execute(
        sa.update(Tenant)
        .where(Tenant.id == a["tenant_id"])
        .values(status=TenantStatus.PROVISIONING)
    )
    await db_session.commit()
    r = await client.post(
        f"/console/clients/{a['ref']}/status", headers=h(), json={"status": "active"}
    )
    assert r.status_code == 409
    assert "publish an agent" in r.json()["detail"]
    # analyst cannot write
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    r = await client.post(
        f"/console/clients/{a['ref']}/status",
        headers=analyst["headers"](),
        json={"status": "paused"},
    )
    assert r.status_code == 403

    audit_rows = (
        (
            await db_session.execute(
                sa.select(AuditLog.action).where(
                    AuditLog.tenant_id == a["tenant_id"],
                    AuditLog.actor == "console:owner-a@example.com",
                )
            )
        )
        .scalars()
        .all()
    )
    assert "console.client.update" in audit_rows
    assert audit_rows.count("console.client.status") == 4


async def test_delete_requires_archive_and_name(client, console_world, db_session) -> None:
    a = console_world["a"]
    h = a["headers"]
    # Not archived → 409
    r = await client.request(
        "DELETE", f"/console/clients/{a['ref']}", headers=h(), json={"confirm_name": "Client A One"}
    )
    assert r.status_code == 409 and "archived" in r.json()["detail"]
    await client.post(
        f"/console/clients/{a['ref']}/status", headers=h(), json={"status": "archived"}
    )
    # Wrong name → 409
    r = await client.request(
        "DELETE", f"/console/clients/{a['ref']}", headers=h(), json={"confirm_name": "wrong"}
    )
    assert r.status_code == 409 and "confirm_name" in r.json()["detail"]
    # Invoices block (legal retention)
    db_session.add(Invoice(tenant_id=a["tenant_id"], period_year=2026, period_month=7))
    await db_session.commit()
    r = await client.request(
        "DELETE", f"/console/clients/{a['ref']}", headers=h(), json={"confirm_name": "Client A One"}
    )
    assert r.status_code == 409 and "factura" in r.json()["detail"]
    await db_session.execute(sa.delete(Invoice))
    await db_session.commit()
    # Builder cannot delete
    builder = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    r = await client.request(
        "DELETE",
        f"/console/clients/{a['ref']}",
        headers=builder["headers"](),
        json={"confirm_name": "Client A One"},
    )
    assert r.status_code == 403
    # Owner deletes
    r = await client.request(
        "DELETE", f"/console/clients/{a['ref']}", headers=h(), json={"confirm_name": "Client A One"}
    )
    assert r.status_code == 204, r.text
    assert await db_session.get(Tenant, a["tenant_id"]) is None
    assert (await client.get(f"/console/clients/{a['ref']}", headers=h())).status_code == 404
    # The deletion is in the audit trail, actor = the console user.
    row = await db_session.scalar(
        sa.select(AuditLog)
        .where(AuditLog.action == "tenant.delete")
        .order_by(AuditLog.created_at.desc())
    )
    assert row is not None and row.actor == "console:owner-a@example.com"


# ── agents (CP-11/12) ──────────────────────────────────────────────────


async def test_agent_stage_publish_rollback_with_audit(client, console_world, db_session) -> None:
    a = console_world["a"]
    h = a["headers"]
    empty = await client.get(f"/console/clients/{a['ref']}/agent", headers=h())
    assert empty.status_code == 200 and empty.json() == {"active_version": None, "versions": []}

    v1 = await client.post(
        f"/console/clients/{a['ref']}/agent/versions",
        headers=h(),
        json={"system_prompt": "v1 prompt"},
    )
    assert v1.status_code == 201, v1.text
    assert v1.json()["version"] == 1 and v1.json()["status"] == "staged"

    pub = await client.post(f"/console/clients/{a['ref']}/agent/versions/1/publish", headers=h())
    assert pub.status_code == 200, pub.text
    assert (
        pub.json()["status"] == "active"
        and pub.json()["promoted_by"] == "console:owner-a@example.com"
    )

    v2 = await client.post(
        f"/console/clients/{a['ref']}/agent/versions",
        headers=h(),
        json={"system_prompt": "v2 prompt", "tools": []},
    )
    assert v2.status_code == 201
    pub2 = await client.post(f"/console/clients/{a['ref']}/agent/versions/2/publish", headers=h())
    assert pub2.status_code == 200
    bundle = (await client.get(f"/console/clients/{a['ref']}/agent", headers=h())).json()
    assert bundle["active_version"] == 2
    assert [v["version"] for v in bundle["versions"]] == [1, 2] or sorted(
        v["version"] for v in bundle["versions"]
    ) == [1, 2]

    back = await client.post(f"/console/clients/{a['ref']}/agent/versions/1/rollback", headers=h())
    assert back.status_code == 200 and back.json()["version"] == 1
    again = await client.post(f"/console/clients/{a['ref']}/agent/versions/1/rollback", headers=h())
    assert again.status_code == 409  # already active
    nope = await client.post(f"/console/clients/{a['ref']}/agent/versions/9/publish", headers=h())
    assert nope.status_code == 404
    bad_tool = await client.post(
        f"/console/clients/{a['ref']}/agent/versions",
        headers=h(),
        json={"system_prompt": "x", "tools": ["not.a.tool"]},
    )
    assert bad_tool.status_code == 422

    actions = (
        await db_session.execute(
            sa.select(AuditLog.action, AuditLog.actor).where(AuditLog.tenant_id == a["tenant_id"])
        )
    ).all()
    assert ("agent_config.promote", "console:owner-a@example.com") in actions
    assert ("agent_config.rollback", "console:owner-a@example.com") in actions
    # One event, one row: no duplicated console.* twin.
    assert not any(a.startswith("console.agent") for a, _ in actions)

    # The audit page renders it for a human.
    audit = (await client.get("/console/audit?action=agent_config.promote", headers=h())).json()
    assert audit["items"], audit
    assert audit["items"][0]["summary"].startswith("owner-a@example.com published agent version")
    assert audit["items"][0]["external_client_ref"] == a["ref"]


# ── channels + conversations (metadata) ────────────────────────────────


async def test_channels_and_conversation_metadata(client, console_world, db_session) -> None:
    a = console_world["a"]
    h = a["headers"]
    ch = Channel(
        id=uuid.uuid4(),
        tenant_id=a["tenant_id"],
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=f"+3460000{uuid.uuid4().int % 10000:04d}",
        config={"role": "agent", "access_token": "SECRET-TOKEN"},
        status=ChannelStatus.ACTIVE,
    )
    db_session.add(ch)
    cust = Customer(
        id=uuid.uuid4(), tenant_id=a["tenant_id"], identifier="+34600111222", preferences={}
    )
    db_session.add(cust)
    await db_session.flush()
    conv = Conversation(
        id=uuid.uuid4(),
        tenant_id=a["tenant_id"],
        channel_id=ch.id,
        customer_id=cust.id,
        status=ConversationStatus.ESCALATED,
    )
    db_session.add(conv)
    await db_session.flush()
    db_session.add_all(
        [
            Message(
                tenant_id=a["tenant_id"],
                conversation_id=conv.id,
                direction=MessageDirection.INBOUND,
                status=MessageStatus.DELIVERED,
                content="MY SECRET PHONE NUMBER IS 600",
                latency_ms=100,
            ),
            Message(
                tenant_id=a["tenant_id"],
                conversation_id=conv.id,
                direction=MessageDirection.OUTBOUND,
                status=MessageStatus.FAILED,
                content="ANOTHER SECRET",
                latency_ms=300,
            ),
        ]
    )
    await db_session.commit()

    chans = await client.get(f"/console/clients/{a['ref']}/channels", headers=h())
    assert chans.status_code == 200 and len(chans.json()) == 1
    assert chans.json()[0]["role"] == "agent"
    assert "SECRET-TOKEN" not in chans.text and "config" not in chans.json()[0]

    convs = await client.get(f"/console/clients/{a['ref']}/conversations", headers=h())
    assert convs.status_code == 200, convs.text
    assert convs.json()["total"] == 1
    item = convs.json()["items"][0]
    assert item["turns"] == 2 and item["inbound_messages"] == 1 and item["failed_messages"] == 1
    assert item["escalated"] is True and item["avg_latency_ms"] == 200
    assert "SECRET" not in convs.text

    only_errors = await client.get(
        f"/console/clients/{a['ref']}/conversations?with_errors=true", headers=h()
    )
    assert only_errors.json()["total"] == 1
    stats = await client.get(f"/console/clients/{a['ref']}/conversations/stats", headers=h())
    assert stats.status_code == 200
    assert stats.json()["conversations"] == 1 and stats.json()["escalated"] == 1
    assert stats.json()["failed_messages"] == 1
    # health now sees whatsapp
    detail = (await client.get(f"/console/clients/{a['ref']}", headers=h())).json()
    assert detail["health"]["whatsapp_connected"] is True


# ── usage (C9) ─────────────────────────────────────────────────────────


async def test_usage_is_units_by_source_and_never_cost(client, console_world, db_session) -> None:
    a = console_world["a"]
    for meter, source, qty in (
        ("llm.input_tokens", "channel", 1000),
        ("llm.input_tokens", "qa", 500),
        ("channel.message", "channel", 3),
    ):
        await db_session.execute(
            sa.text(
                "INSERT INTO usage_records (tenant_id, occurred_at, meter, quantity, cost_usd, "
                "billable_qty, idempotency_key, source) VALUES (:t, now(), :m, :q, 0.5, :q, :k, :s)"
            ),
            {"t": str(a["tenant_id"]), "m": meter, "q": qty, "k": f"k:{uuid.uuid4()}", "s": source},
        )
    await db_session.commit()

    resp = await client.get("/console/usage?days=7", headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "cost" not in resp.text.lower()
    assert body["totals_by_meter"] == {"llm.input_tokens": 1000.0, "channel.message": 3.0}
    assert body["total_records"] == 3
    qa = [b for b in body["buckets"] if b["source"] == "qa"]
    assert qa and qa[0]["quantity"] == 500.0
    only_qa = await client.get("/console/usage?source=qa", headers=a["headers"]())
    assert only_qa.json()["totals_by_meter"] == {}
    assert only_qa.json()["total_records"] == 1
    # billing role can read usage
    billing = await add_console_member(db_session, partner_id=a["partner_id"], role="billing")
    assert (await client.get("/console/usage", headers=billing["headers"]())).status_code == 200


# ── team (CP-26) ───────────────────────────────────────────────────────


async def test_team_invite_accept_and_owner_protection(client, console_world, db_session) -> None:
    a = console_world["a"]
    h = a["headers"]
    inv = await client.post(
        "/console/team/invitations",
        headers=h(),
        json={"email": "New@Example.com", "role": "builder"},
    )
    assert inv.status_code == 201, inv.text
    token = inv.json()["accept_path"].removeprefix("/invite/")
    assert inv.json()["email"] == "new@example.com" and inv.json()["email_sent"] is False
    dup = await client.post(
        "/console/team/invitations", headers=h(), json={"email": "new@example.com", "role": "admin"}
    )
    assert dup.status_code == 409
    member_dup = await client.post(
        "/console/team/invitations",
        headers=h(),
        json={"email": "owner-a@example.com", "role": "admin"},
    )
    assert member_dup.status_code == 409

    # Lookup via service token
    look = await client.get(f"/console/invitations/{token}", headers=_svc_headers())
    assert look.status_code == 200 and look.json()["partner_name"] == "Console Partner A"
    # Accept with wrong e-mail → 409
    bad = await client.post(
        f"/console/invitations/{token}/accept",
        headers=_svc_headers(),
        json={"user_id": "user_new", "email": "other@example.com"},
    )
    assert bad.status_code == 409 and bad.json()["detail"].startswith("email_mismatch")
    ok = await client.post(
        f"/console/invitations/{token}/accept",
        headers=_svc_headers(),
        json={"user_id": "user_new", "email": "new@example.com", "display_name": "New"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["role"] == "builder" and ok.json()["partner"]["slug"] == a["slug"]
    # Link is dead now
    assert (
        await client.get(f"/console/invitations/{token}", headers=_svc_headers())
    ).status_code == 404

    team = (await client.get("/console/team", headers=h())).json()
    assert {m["email"] for m in team["members"]} == {"owner-a@example.com", "new@example.com"}
    assert team["invitations"] == []
    new_id = next(m["id"] for m in team["members"] if m["email"] == "new@example.com")
    me_flag = next(m for m in team["members"] if m["email"] == "owner-a@example.com")
    assert me_flag["is_you"] is True

    # New user's own token works and carries builder permissions
    def new_headers() -> dict[str, str]:  # fresh jti per call — replay is refused
        return {
            "Authorization": (
                f"Bearer {mint_console_token(user_id='user_new', partner_id=a['partner_id'])}"
            )
        }

    me = await client.get("/console/me", headers=new_headers())
    assert me.status_code == 200 and me.json()["role"] == "builder"

    # Owner protection: cannot demote/remove the only owner (self-change first)
    r = await client.patch(
        f"/console/team/members/{a['membership_id']}/role", headers=h(), json={"role": "admin"}
    )
    assert r.status_code == 409 and "own membership" in r.json()["detail"]
    # Promote new to admin, then admin tries to demote the last owner → 409
    r = await client.patch(
        f"/console/team/members/{new_id}/role", headers=h(), json={"role": "admin"}
    )
    assert r.status_code == 200 and r.json()["role"] == "admin"
    r = await client.patch(
        f"/console/team/members/{a['membership_id']}/role",
        headers=new_headers(),
        json={"role": "analyst"},
    )
    assert r.status_code == 409 and "one active owner" in r.json()["detail"]
    r = await client.delete(f"/console/team/members/{a['membership_id']}", headers=new_headers())
    assert r.status_code == 409
    r = await client.patch(
        f"/console/team/members/{a['membership_id']}/status",
        headers=new_headers(),
        json={"status": "suspended"},
    )
    assert r.status_code == 409
    # Second owner → first can step down
    r = await client.patch(
        f"/console/team/members/{new_id}/role", headers=h(), json={"role": "owner"}
    )
    assert r.status_code == 200
    r = await client.patch(
        f"/console/team/members/{a['membership_id']}/role",
        headers=new_headers(),
        json={"role": "analyst"},
    )
    assert r.status_code == 200 and r.json()["role"] == "analyst"
    # …and the analyst can no longer manage
    r = await client.get("/console/team", headers=h())
    assert r.status_code == 200
    r = await client.delete(f"/console/team/members/{new_id}", headers=h())
    assert r.status_code == 403


async def test_invitation_revoke_and_expiry(client, console_world, db_session) -> None:
    from datetime import UTC, datetime, timedelta

    from nexus_api.db.models import PartnerInvitation

    a = console_world["a"]
    h = a["headers"]
    inv = await client.post(
        "/console/team/invitations",
        headers=h(),
        json={"email": "gone@example.com", "role": "analyst"},
    )
    inv_id = inv.json()["id"]
    token = inv.json()["accept_path"].removeprefix("/invite/")
    assert (
        await client.delete(f"/console/team/invitations/{inv_id}", headers=h())
    ).status_code == 204
    assert (
        await client.get(f"/console/invitations/{token}", headers=_svc_headers())
    ).status_code == 404

    inv = await client.post(
        "/console/team/invitations",
        headers=h(),
        json={"email": "late@example.com", "role": "analyst"},
    )
    token = inv.json()["accept_path"].removeprefix("/invite/")
    await db_session.execute(
        sa.update(PartnerInvitation)
        .where(PartnerInvitation.id == uuid.UUID(inv.json()["id"]))
        .values(expires_at=datetime.now(UTC) - timedelta(days=1))
    )
    await db_session.commit()
    assert (
        await client.get(f"/console/invitations/{token}", headers=_svc_headers())
    ).status_code == 404
    accept = await client.post(
        f"/console/invitations/{token}/accept",
        headers=_svc_headers(),
        json={"user_id": "user_late", "email": "late@example.com"},
    )
    assert accept.status_code == 404


# ── keys (CP-27) ───────────────────────────────────────────────────────


async def test_keys_plaintext_once_rotate_revoke(client, console_world, db_session) -> None:
    a = console_world["a"]
    h = a["headers"]
    created = await client.post(
        "/console/keys", headers=h(), json={"type": "test", "scopes": ["provision"]}
    )
    assert created.status_code == 201, created.text
    plaintext = created.json()["plaintext"]
    assert plaintext.startswith("ak_test_")
    key_id = created.json()["id"]
    listed = (await client.get("/console/keys", headers=h())).json()
    assert len(listed) == 1 and "plaintext" not in listed[0]
    assert plaintext not in (await client.get("/console/keys", headers=h())).text

    # The key authenticates on the partner API
    ok = await client.post(
        "/v2/partners/clients",
        headers={"Authorization": f"Bearer {plaintext}"},
        json={"external_client_ref": a["ref"], "name": "x"},
    )
    assert ok.status_code == 200, ok.text

    rotated = await client.post(
        f"/console/keys/{key_id}/rotate", headers=h(), json={"grace_hours": 1}
    )
    assert rotated.status_code == 201
    assert rotated.json()["plaintext"] != plaintext
    listed = (await client.get("/console/keys", headers=h())).json()
    old = next(k for k in listed if k["id"] == key_id)
    assert old["revoked_at"] is not None and old["grace_expires_at"] is not None
    revoked = await client.post(f"/console/keys/{key_id}/revoke", headers=h())
    assert revoked.status_code == 200 and revoked.json()["grace_expires_at"] is None
    again = await client.post(f"/console/keys/{key_id}/rotate", headers=h(), json={})
    assert again.status_code == 409

    # builder can list, cannot manage
    builder = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    assert (await client.get("/console/keys", headers=builder["headers"]())).status_code == 200
    assert (
        await client.post("/console/keys", headers=builder["headers"](), json={})
    ).status_code == 403

    # tenant-level scope cannot be requested from the console
    bad = await client.post("/console/keys", headers=h(), json={"scopes": ["messages_send"]})
    assert bad.status_code == 422

    audit = (await client.get("/console/audit?action=console.key", headers=h())).json()
    assert {i["action"] for i in audit["items"]} == {
        "console.key.create",
        "console.key.rotate",
        "console.key.revoke",
    }


# ── billing (CP-25) ────────────────────────────────────────────────────


async def test_billing_read(client, console_world, db_session) -> None:
    a = console_world["a"]
    db_session.add(
        Invoice(
            partner_id=a["partner_id"],
            period_year=2026,
            period_month=7,
            total_cents=12345,
            status="issued",
        )
    )
    await db_session.commit()
    resp = await client.get("/console/billing", headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    assert resp.json()["receipts"][0]["total_usd"] == 123.45
    assert resp.json()["receipts"][0]["period_month"] == 7


# ── audit paging ───────────────────────────────────────────────────────


async def test_audit_paging_and_filters(client, console_world, db_session) -> None:
    a = console_world["a"]
    for i in range(5):
        db_session.add(
            AuditLog(
                tenant_id=a["tenant_id"],
                actor="console:owner-a@example.com",
                action="console.client.update",
                target=f"tenant:{a['tenant_id']}",
                after_json={"i": i},
            )
        )
    await db_session.commit()
    first = (await client.get("/console/audit?limit=2", headers=a["headers"]())).json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = (
        await client.get(
            f"/console/audit?limit=2&cursor={first['next_cursor']}", headers=a["headers"]()
        )
    ).json()
    assert len(second["items"]) == 2
    assert {i["id"] for i in first["items"]}.isdisjoint({i["id"] for i in second["items"]})
    bad = await client.get("/console/audit?cursor=%%%", headers=a["headers"]())
    assert bad.status_code == 422
    by_actor = (await client.get("/console/audit?actor=owner-a", headers=a["headers"]())).json()
    assert len(by_actor["items"]) == 5
    assert by_actor["items"][0]["client_name"] == "Client A One"
    # analyst may read audit; builder may not
    builder = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    assert (await client.get("/console/audit", headers=builder["headers"]())).status_code == 403
