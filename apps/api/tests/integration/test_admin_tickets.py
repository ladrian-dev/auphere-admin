"""F4: persist from POST /console/support/tickets, admin inbox, isolation."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AuditLog
from nexus_api.db.models.support_ticket import SupportTicket, SupportTicketEvent

pytestmark = pytest.mark.asyncio

POST = "/console/support/tickets"


def _body(**extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "category": "help",
        "topic": "connector.shopify",
        "need": "Sincronizar pedidos de la tienda",
        "checked": ["Clientes del partner", "Qué existe y qué no en Auphere"],
        "bridge": False,
    }
    payload.update(extra)
    return payload


async def _open(client, headers, **extra: object):
    return await client.post(POST, headers=headers, json=_body(**extra))


async def test_console_post_persists_and_admin_lists_unscoped(
    client, console_world, admin_headers
) -> None:
    a, b = console_world["a"], console_world["b"]
    opened_a = await _open(client, a["headers"]())
    opened_b = await _open(client, b["headers"](), topic="quota.clients")
    assert opened_a.status_code == 201, opened_a.text
    assert opened_b.status_code == 201, opened_b.text
    ref_a = opened_a.json()["ticket_ref"]
    ref_b = opened_b.json()["ticket_ref"]
    assert ref_a.startswith("AU-")
    assert ref_b.startswith("AU-")
    assert set(opened_a.json()) == {"ticket_ref", "category", "topic", "sla", "opened_at"}

    listed = await client.get("/admin/tickets", headers=admin_headers)
    assert listed.status_code == 200, listed.text
    refs = {row["ticket_ref"] for row in listed.json()}
    assert {ref_a, ref_b} <= refs
    partners = {row["ticket_ref"]: row["partner_id"] for row in listed.json()}
    assert partners[ref_a] == str(a["partner_id"])
    assert partners[ref_b] == str(b["partner_id"])

    only_a = await client.get(f"/admin/tickets?partner_id={a['partner_id']}", headers=admin_headers)
    assert only_a.status_code == 200, only_a.text
    assert {row["ticket_ref"] for row in only_a.json()} == {ref_a}

    open_only = await client.get("/admin/tickets?status=open", headers=admin_headers)
    assert open_only.status_code == 200
    assert {ref_a, ref_b} <= {row["ticket_ref"] for row in open_only.json()}


async def test_admin_get_and_patch_status(client, console_world, admin_headers) -> None:
    a = console_world["a"]
    opened = await _open(client, a["headers"]())
    assert opened.status_code == 201, opened.text
    ref = opened.json()["ticket_ref"]

    listed = await client.get("/admin/tickets", headers=admin_headers)
    row = next(r for r in listed.json() if r["ticket_ref"] == ref)
    ticket_id = row["id"]

    got = await client.get(f"/admin/tickets/{ticket_id}", headers=admin_headers)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["ticket_ref"] == ref
    assert body["need"] == "Sincronizar pedidos de la tienda"
    assert body["checked"] == ["Clientes del partner", "Qué existe y qué no en Auphere"]
    assert body["status"] == "open"
    assert body["events"][0]["kind"] == "open"
    assert body["events"][0]["actor"].startswith("console:")
    assert body["links"]["consumo"] == f"/partners/{a['partner_id']}/wallet"
    assert body["links"]["modelos"] == f"/partners/{a['partner_id']}/models"
    assert body["links"]["conocimiento"] == f"/partners/{a['partner_id']}/knowledge"
    assert body["links"]["auditoria"] == f"/partners/{a['partner_id']}/audit"

    patched = await client.patch(
        f"/admin/tickets/{ticket_id}",
        headers=admin_headers,
        json={"status": "pending"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["status"] == "pending"
    kinds = [e["kind"] for e in patched.json()["events"]]
    assert kinds == ["open", "status"]
    assert patched.json()["events"][-1]["actor"].startswith("admin:")
    assert len(patched.json()["events"][-1]["actor"]) == len("admin:") + 8

    missing = await client.get(f"/admin/tickets/{uuid.uuid4()}", headers=admin_headers)
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Unknown ticket"}


async def test_extra_forbid_and_no_partner_id_in_body(client, console_world, admin_headers) -> None:
    a = console_world["a"]
    extra = await _open(client, a["headers"](), partner_id=str(a["partner_id"]))
    assert extra.status_code == 422, extra.text

    opened = await _open(client, a["headers"]())
    assert opened.status_code == 201, opened.text
    listed = await client.get("/admin/tickets", headers=admin_headers)
    ticket_id = next(
        r["id"] for r in listed.json() if r["ticket_ref"] == opened.json()["ticket_ref"]
    )
    bad = await client.patch(
        f"/admin/tickets/{ticket_id}",
        headers=admin_headers,
        json={"status": "closed", "partner_id": str(a["partner_id"])},
    )
    assert bad.status_code == 422, bad.text
    need_body = await client.patch(
        f"/admin/tickets/{ticket_id}",
        headers=admin_headers,
        json={"status": "closed", "need": "nope"},
    )
    assert need_body.status_code == 422, need_body.text
    with_body = await client.patch(
        f"/admin/tickets/{ticket_id}",
        headers=admin_headers,
        json={"status": "closed", "body": "nope"},
    )
    assert with_body.status_code == 422, with_body.text


async def test_foreign_client_ref_is_the_same_404_as_missing(client, console_world) -> None:
    a, b = console_world["a"], console_world["b"]
    foreign = await _open(client, a["headers"](), client_ref=b["ref"])
    missing = await _open(client, a["headers"](), client_ref="no-such-client")
    assert foreign.status_code == 404
    assert missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": "Unknown client reference"}


async def test_partner_a_cannot_read_partner_b_ticket(client, console_world) -> None:
    a, b = console_world["a"], console_world["b"]
    opened_b = await _open(client, b["headers"]())
    assert opened_b.status_code == 201, opened_b.text
    ref_b = opened_b.json()["ticket_ref"]

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, a["partner_id"])
        own = (
            await session.scalars(sa.select(SupportTicket).where(SupportTicket.ticket_ref == ref_b))
        ).first()
        assert own is None
        events = (await session.scalars(sa.select(SupportTicketEvent))).all()
        assert events == []


async def test_audit_ticket_open_and_status(client, console_world, admin_headers) -> None:
    a = console_world["a"]
    opened = await _open(client, a["headers"]())
    assert opened.status_code == 201, opened.text
    ref = opened.json()["ticket_ref"]

    sm = get_sessionmaker()
    async with sm() as session:
        opens = (
            await session.scalars(sa.select(AuditLog).where(AuditLog.action == "ticket.open"))
        ).all()
    assert any((row.after_json or {}).get("ticket_ref") == ref for row in opens)
    opener = next(row for row in opens if (row.after_json or {}).get("ticket_ref") == ref)
    assert opener.actor.startswith("console:")

    listed = await client.get("/admin/tickets", headers=admin_headers)
    ticket_id = next(r["id"] for r in listed.json() if r["ticket_ref"] == ref)
    patched = await client.patch(
        f"/admin/tickets/{ticket_id}",
        headers=admin_headers,
        json={"status": "closed"},
    )
    assert patched.status_code == 200, patched.text

    async with sm() as session:
        statuses = (
            await session.scalars(sa.select(AuditLog).where(AuditLog.action == "ticket.status"))
        ).all()
    moved = next(row for row in statuses if (row.after_json or {}).get("ticket_ref") == ref)
    assert moved.actor.startswith("admin:")
    assert moved.before_json == {"status": "open"}
    assert moved.after_json["status"] == "closed"


async def test_no_console_get_and_admin_requires_token(client, console_world) -> None:
    a = console_world["a"]
    get_collection = await client.get(POST, headers=a["headers"]())
    assert get_collection.status_code == 405
    get_one = await client.get(f"{POST}/{uuid.uuid4()}", headers=a["headers"]())
    assert get_one.status_code == 404
    no_token = await client.get("/admin/tickets")
    assert no_token.status_code == 401


async def test_list_query_extra_forbid(client, admin_headers) -> None:
    extra = await client.get("/admin/tickets?note=x", headers=admin_headers)
    assert extra.status_code == 422, extra.text


async def test_console_get_ticket_is_opaque_404(client, console_world, admin_headers) -> None:
    """No GET on console. A and missing look the same (404, not 403)."""
    a, b = console_world["a"], console_world["b"]
    opened_b = await _open(client, b["headers"]())
    assert opened_b.status_code == 201, opened_b.text
    listed = await client.get("/admin/tickets", headers=admin_headers)
    ticket_id = next(
        r["id"] for r in listed.json() if r["ticket_ref"] == opened_b.json()["ticket_ref"]
    )
    as_a = await client.get(f"{POST}/{ticket_id}", headers=a["headers"]())
    missing = await client.get(f"{POST}/{uuid.uuid4()}", headers=a["headers"]())
    assert as_a.status_code == 404
    assert missing.status_code == 404
    assert as_a.json() == missing.json()


async def test_is_admin_guc_unscopes_without_it_zero(client, console_world) -> None:
    """FORCE + nexus_app: sin is_admin cero filas; con is_admin las dos."""
    a, b = console_world["a"], console_world["b"]
    opened_a = await _open(client, a["headers"]())
    opened_b = await _open(client, b["headers"](), topic="quota.clients")
    assert opened_a.status_code == 201, opened_a.text
    assert opened_b.status_code == 201, opened_b.text
    refs = {opened_a.json()["ticket_ref"], opened_b.json()["ticket_ref"]}

    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(sa.text("SELECT set_config('app.is_admin', '', true)"))
        await session.execute(sa.text("SET ROLE nexus_app"))
        n = await session.scalar(sa.text("SELECT count(*) FROM support_tickets"))
        assert n == 0
        await session.execute(sa.text("RESET ROLE"))

    async with sm() as session:
        from nexus_api.core.partner_context import apply_admin_to_session

        async with session.begin():
            await apply_admin_to_session(session)
            visible = set(
                (await session.execute(sa.text("SELECT ticket_ref FROM support_tickets"))).scalars().all()
            )
            assert refs <= visible
