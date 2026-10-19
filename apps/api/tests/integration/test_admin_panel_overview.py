"""Spec 031 — what the operator panel reads about partners and the instance.

R3 (Panel), R4 (partner profile, team, editable billing e-mail). Every read
goes through ``require_admin_token``; the partner-scoped tables with FORCE
RLS (``partner_wallets``, ``partner_allocations``, ``tickets``) are read with
the GUC of the partner being read, one at a time — never by lifting RLS.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AuditLog, PartnerAllocation, PartnerWallet
from nexus_api.db.models.partner_membership import PartnerInvitation

pytestmark = pytest.mark.asyncio


async def _wallet(partner_id: uuid.UUID, *, purchased: int, included: int = 0) -> None:
    """Set the partner's balance. The wallet row may already exist (born with
    the partner); either way it ends with exactly these figures."""
    sm = get_sessionmaker()
    async with sm() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        row = await s.get(PartnerWallet, partner_id)
        if row is None:
            row = PartnerWallet(partner_id=partner_id)
            s.add(row)
        row.included_remaining = included
        row.purchased_remaining = purchased
        row.included_expires_at = datetime.now(UTC) + timedelta(days=3)


async def _exhaust_cap(partner_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    sm = get_sessionmaker()
    async with sm() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        await s.execute(
            sa.update(PartnerAllocation)
            .where(PartnerAllocation.tenant_id == tenant_id)
            .values(remaining=0)
        )


async def test_overview_counts_partners_clients_and_money(
    client, console_world, admin_headers
) -> None:
    a, b = console_world["a"], console_world["b"]
    # 1 US$ = 100 000 credits (billing/pricing.py). 2.5 US$ + 1.25 US$.
    await _wallet(a["partner_id"], purchased=250_000)
    await _wallet(b["partner_id"], purchased=100_000, included=25_000)
    await _exhaust_cap(b["partner_id"], b["tenant_id"])

    res = await client.get("/admin/overview", headers=admin_headers)
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["partners"]["total"] >= 2
    assert body["partners"]["active"] >= 2
    assert body["clients"]["active"] >= 2
    # The sum of each partner's own balance, read under that partner's GUC.
    assert body["balance_cents"] == 250 + 125
    assert body["unreadable"] == []
    without_cap = {row["tenant_id"] for row in body["clients_without_cap"]}
    assert without_cap == {str(b["tenant_id"])}
    row = body["clients_without_cap"][0]
    assert row["partner_id"] == str(b["partner_id"])
    assert row["name"] == "Client B One"


async def test_overview_lists_open_tickets(client, console_world, admin_headers) -> None:
    a = console_world["a"]
    opened = await client.post(
        "/console/support/tickets",
        headers=a["headers"](),
        json={
            "category": "help",
            "topic": "connector.shopify",
            "need": "Sincronizar pedidos",
            "checked": ["Clientes del partner"],
            "bridge": False,
        },
    )
    assert opened.status_code == 201, opened.text

    body = (await client.get("/admin/overview", headers=admin_headers)).json()
    assert body["tickets_open"] == 1
    assert body["open_tickets"][0]["ticket_ref"] == opened.json()["ticket_ref"]
    assert body["open_tickets"][0]["partner_id"] == str(a["partner_id"])


async def test_overview_requires_the_admin_token(client) -> None:
    res = await client.get("/admin/overview")
    assert res.status_code in (401, 403)


async def test_partner_out_carries_console_facts_and_counts(
    client, console_world, admin_headers
) -> None:
    a = console_world["a"]
    await _wallet(a["partner_id"], purchased=300_000)

    got = await client.get(f"/admin/partners/{a['partner_id']}", headers=admin_headers)
    assert got.status_code == 200, got.text
    p = got.json()
    assert p["console_enabled"] is True
    assert p["companion_enabled"] is True
    assert p["max_clients"] == 3
    assert p["clients_count"] == 1
    assert p["members_count"] == 1
    assert p["available_cents"] == 300

    listed = await client.get("/admin/partners", headers=admin_headers)
    row = next(r for r in listed.json() if r["id"] == str(a["partner_id"]))
    assert row["clients_count"] == 1
    assert row["members_count"] == 1
    assert row["available_cents"] == 300


async def test_billing_email_is_editable_and_audited(
    client, console_world, admin_headers, db_session
) -> None:
    a = console_world["a"]
    res = await client.patch(
        f"/admin/partners/{a['partner_id']}",
        headers=admin_headers,
        json={"billing_email": "facturas@partner-a.example"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["billing_email"] == "facturas@partner-a.example"

    row = (
        await db_session.execute(
            sa.select(AuditLog)
            .where(AuditLog.action == "partner.update")
            .where(AuditLog.target == f"partner:{a['partner_id']}")
        )
    ).scalar_one()
    assert row.before_json["billing_email"] is None
    assert row.after_json["billing_email"] == "facturas@partner-a.example"


async def test_members_lists_people_and_pending_invitations(
    client, console_world, admin_headers, db_session
) -> None:
    a, b = console_world["a"], console_world["b"]
    db_session.add(
        PartnerInvitation(
            partner_id=a["partner_id"],
            email="nueva@partner-a.example",
            role="analyst",
            token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            expires_at=datetime.now(UTC) + timedelta(days=21),
        )
    )
    await db_session.commit()

    res = await client.get(f"/admin/partners/{a['partner_id']}/members", headers=admin_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert [m["email"] for m in body["members"]] == ["owner-a@example.com"]
    assert body["members"][0]["role"] == "owner"
    assert [i["email"] for i in body["invitations"]] == ["nueva@partner-a.example"]
    # Partner B's people never show up on A's page.
    assert "owner-b@example.com" not in res.text
    assert str(b["partner_id"]) not in res.text

    missing = await client.get(f"/admin/partners/{uuid.uuid4()}/members", headers=admin_headers)
    assert missing.status_code == 404


async def test_instance_names_environment_schema_and_commit(client, admin_headers) -> None:
    res = await client.get("/admin/instance", headers=admin_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["schema_revision"]
    assert body["checks"]["postgres"] == "ok"
    assert body["environment"]
    assert body["commit"]
