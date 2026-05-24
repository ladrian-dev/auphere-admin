"""Integration tests for the admin audit-log surface (Bloque B4).

Covers:
- Empty response for a fresh tenant.
- Newest-first ordering.
- Each filter (actor, action, action_prefix, target, after, before).
- Cursor pagination — page boundary preserves order.
- Tenant isolation — tenant A's audit rows never leak to tenant B.
- Distinct-actions endpoint groups + orders by frequency.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text as _text

from nexus_api.db.models import AuditLog

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


_ADMIN_HEADERS = {"Authorization": "Bearer test-admin-token"}


async def _insert_audit(
    db_session,
    *,
    tenant_id: uuid.UUID,
    actor: str,
    action: str,
    target: str,
    before: dict | None = None,
    after: dict | None = None,
    created_at: datetime | None = None,
) -> uuid.UUID:
    """Insert one audit_log row scoped to tenant_id, bypassing the
    tenant context because tests run plain sessions. Returns the
    row id so the test can correlate."""
    row = AuditLog(
        tenant_id=tenant_id,
        actor=actor,
        action=action,
        target=target,
        before_json=before,
        after_json=after,
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    if created_at is not None:
        # Overwrite the timestamp via raw SQL — created_at has a
        # server_default that can't be set on insert from the ORM
        # without breaking the trigger. Bypass RLS for this admin op.
        await db_session.execute(
            _text(
                "UPDATE audit_log SET created_at = :ts WHERE id = :id"
            ),
            {"ts": created_at, "id": row.id},
        )
        await db_session.commit()
    return row.id


async def test_empty_for_fresh_tenant(client, seed_tenants):
    tid = seed_tenants["a"]
    r = await client.get(
        f"/admin/tenants/{tid}/audit-log", headers=_ADMIN_HEADERS
    )
    assert r.status_code == 200
    body = r.json()
    assert body == {"items": [], "next_cursor": None}


async def test_returns_entries_newest_first(client, db_session, seed_tenants):
    tid = seed_tenants["a"]
    base = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
    await _insert_audit(
        db_session,
        tenant_id=tid,
        actor="luis",
        action="agent_config.promote",
        target="v3",
        created_at=base,
    )
    await _insert_audit(
        db_session,
        tenant_id=tid,
        actor="luis",
        action="connector.connected",
        target="woocommerce",
        created_at=base + timedelta(minutes=5),
    )
    r = await client.get(
        f"/admin/tenants/{tid}/audit-log", headers=_ADMIN_HEADERS
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2
    # Newest first.
    assert items[0]["action"] == "connector.connected"
    assert items[1]["action"] == "agent_config.promote"


async def test_filter_by_actor_substring(client, db_session, seed_tenants):
    tid = seed_tenants["a"]
    await _insert_audit(
        db_session, tenant_id=tid, actor="luis", action="x", target="t1"
    )
    await _insert_audit(
        db_session, tenant_id=tid, actor="alice", action="x", target="t2"
    )
    r = await client.get(
        f"/admin/tenants/{tid}/audit-log?actor=lui", headers=_ADMIN_HEADERS
    )
    items = r.json()["items"]
    assert {it["actor"] for it in items} == {"luis"}


async def test_filter_by_action_exact_vs_prefix(
    client, db_session, seed_tenants
):
    tid = seed_tenants["a"]
    await _insert_audit(
        db_session, tenant_id=tid, actor="luis", action="connector.connected", target="x"
    )
    await _insert_audit(
        db_session, tenant_id=tid, actor="luis", action="connector.disconnected", target="x"
    )
    await _insert_audit(
        db_session, tenant_id=tid, actor="luis", action="agent_config.promote", target="x"
    )
    # Exact.
    r = await client.get(
        f"/admin/tenants/{tid}/audit-log?action=connector.connected",
        headers=_ADMIN_HEADERS,
    )
    assert {it["action"] for it in r.json()["items"]} == {"connector.connected"}
    # Prefix — catches both connector.* but not agent_config.promote.
    r = await client.get(
        f"/admin/tenants/{tid}/audit-log?action_prefix=connector.",
        headers=_ADMIN_HEADERS,
    )
    actions = {it["action"] for it in r.json()["items"]}
    assert actions == {"connector.connected", "connector.disconnected"}


async def test_filter_by_target_substring(client, db_session, seed_tenants):
    tid = seed_tenants["a"]
    await _insert_audit(
        db_session, tenant_id=tid, actor="luis", action="x", target="connector:woocommerce"
    )
    await _insert_audit(
        db_session, tenant_id=tid, actor="luis", action="x", target="connector:calendly"
    )
    r = await client.get(
        f"/admin/tenants/{tid}/audit-log?target=woocommerce",
        headers=_ADMIN_HEADERS,
    )
    assert len(r.json()["items"]) == 1


async def test_filter_by_date_range(client, db_session, seed_tenants):
    tid = seed_tenants["a"]
    base = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
    await _insert_audit(
        db_session, tenant_id=tid, actor="l", action="x", target="early",
        created_at=base - timedelta(hours=2),
    )
    await _insert_audit(
        db_session, tenant_id=tid, actor="l", action="x", target="window",
        created_at=base,
    )
    await _insert_audit(
        db_session, tenant_id=tid, actor="l", action="x", target="late",
        created_at=base + timedelta(hours=2),
    )
    from urllib.parse import quote

    after = quote((base - timedelta(minutes=30)).isoformat())
    before = quote((base + timedelta(minutes=30)).isoformat())
    r = await client.get(
        f"/admin/tenants/{tid}/audit-log?after={after}&before={before}",
        headers=_ADMIN_HEADERS,
    )
    assert r.status_code == 200, r.text
    targets = {it["target"] for it in r.json()["items"]}
    assert targets == {"window"}


async def test_cursor_pagination_preserves_order(
    client, db_session, seed_tenants
):
    tid = seed_tenants["a"]
    base = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
    # 5 rows, evenly spaced. Page size 2 → expect 3 pages.
    for i in range(5):
        await _insert_audit(
            db_session,
            tenant_id=tid,
            actor="l",
            action="x",
            target=f"row-{i}",
            created_at=base + timedelta(minutes=i),
        )
    seen: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        url = f"/admin/tenants/{tid}/audit-log?limit=2"
        if cursor:
            url += f"&cursor={cursor}"
        r = await client.get(url, headers=_ADMIN_HEADERS)
        body = r.json()
        seen.extend(it["target"] for it in body["items"])
        cursor = body["next_cursor"]
        pages += 1
        if cursor is None:
            break
        assert pages < 10, "pagination did not terminate"
    # Newest first: row-4, row-3, row-2, row-1, row-0.
    assert seen == ["row-4", "row-3", "row-2", "row-1", "row-0"]


async def test_tenant_isolation(client, db_session, seed_tenants):
    """A row written under tenant A must NOT appear in tenant B's
    audit feed even if the same actor + action + target string."""
    a_id = seed_tenants["a"]
    b_id = seed_tenants["b"]
    await _insert_audit(
        db_session, tenant_id=a_id, actor="luis", action="x", target="secret-a"
    )
    await _insert_audit(
        db_session, tenant_id=b_id, actor="luis", action="x", target="secret-b"
    )
    r_a = await client.get(
        f"/admin/tenants/{a_id}/audit-log", headers=_ADMIN_HEADERS
    )
    r_b = await client.get(
        f"/admin/tenants/{b_id}/audit-log", headers=_ADMIN_HEADERS
    )
    targets_a = {it["target"] for it in r_a.json()["items"]}
    targets_b = {it["target"] for it in r_b.json()["items"]}
    assert "secret-a" in targets_a and "secret-a" not in targets_b
    assert "secret-b" in targets_b and "secret-b" not in targets_a


async def test_distinct_actions_sorted_by_frequency(
    client, db_session, seed_tenants
):
    tid = seed_tenants["a"]
    # 3× connector.connected, 2× agent_config.promote, 1× tenant.created
    for _ in range(3):
        await _insert_audit(
            db_session,
            tenant_id=tid,
            actor="l",
            action="connector.connected",
            target="x",
        )
    for _ in range(2):
        await _insert_audit(
            db_session,
            tenant_id=tid,
            actor="l",
            action="agent_config.promote",
            target="x",
        )
    await _insert_audit(
        db_session, tenant_id=tid, actor="l", action="tenant.created", target="x"
    )
    r = await client.get(
        f"/admin/tenants/{tid}/audit-log/actions", headers=_ADMIN_HEADERS
    )
    assert r.status_code == 200
    actions = r.json()
    assert actions == [
        "connector.connected",
        "agent_config.promote",
        "tenant.created",
    ]


async def test_before_after_json_round_trips(client, db_session, seed_tenants):
    tid = seed_tenants["a"]
    await _insert_audit(
        db_session,
        tenant_id=tid,
        actor="luis",
        action="agent_config.runtime_capabilities_updated",
        target="agent_config:v3",
        before={"runtime_memory_tool": False},
        after={"runtime_memory_tool": True},
    )
    r = await client.get(
        f"/admin/tenants/{tid}/audit-log", headers=_ADMIN_HEADERS
    )
    item = r.json()["items"][0]
    assert item["before_json"] == {"runtime_memory_tool": False}
    assert item["after_json"] == {"runtime_memory_tool": True}
