"""Isolation guarantee — the console never crosses partners (CP-05).

The five canonical cases, each with two real partners (Facelad and
Amacrux in production — here A and B):

1. **By id** — A asks for B's client by ref: 404. Verified for reads AND
   writes (a write attempt leaves B's data untouched).
2. **By enumeration** — A's list, team, keys, audit and usage contain only
   A's rows, with and without filters, on every page.
3. **By error** — the error for "B's client" is byte-identical to the
   error for "no such client": nothing to learn from the shape.
4. **By order/filter** — a search that would match B's names returns
   nothing to A; sort and pagination cannot surface B.
5. **By timing** — B's ref and a missing ref go through the same single
   lookup; response times are indistinguishable at the granularity a
   network attacker sees (asserted with a generous bound and repeated
   samples so the test is not flaky, and structurally: both stop at the
   mapping lookup and never open a tenant scope).
"""

from __future__ import annotations

import statistics
import time
import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.models import AgentConfig, AgentConfigStatus, AuditLog, PartnerApiKey, Tenant
from tests.conftest import add_console_member

pytestmark = [pytest.mark.isolation]


async def _seed_agent(db_session, tenant_id: uuid.UUID, *, prompt: str) -> None:
    db_session.add(
        AgentConfig(
            tenant_id=tenant_id,
            version=1,
            status=AgentConfigStatus.ACTIVE,
            system_prompt_rendered=prompt,
            channels=[],
            tools=[],
            policies={},
        )
    )
    await db_session.commit()


# ── 1. by id ───────────────────────────────────────────────────────────


async def test_by_id_reads_and_writes_are_bounded(client, console_world, db_session) -> None:
    a, b = console_world["a"], console_world["b"]
    await _seed_agent(db_session, b["tenant_id"], prompt="B SECRET PROMPT")

    # Read: A cannot see B's agent.
    resp = await client.get(f"/console/clients/{b['ref']}/agent", headers=a["headers"]())
    assert resp.status_code == 404
    assert "B SECRET PROMPT" not in resp.text

    # Write: A cannot rename, pause, or stage a version on B's client.
    for method, url, body in (
        ("PATCH", f"/console/clients/{b['ref']}", {"name": "hacked"}),
        ("POST", f"/console/clients/{b['ref']}/status", {"status": "paused"}),
        ("POST", f"/console/clients/{b['ref']}/agent/versions", {"system_prompt": "pwned"}),
    ):
        r = await client.request(method, url, headers=a["headers"](), json=body)
        assert r.status_code == 404, f"{method} {url} → {r.status_code}"

    tenant_b = await db_session.get(Tenant, b["tenant_id"])
    await db_session.refresh(tenant_b)
    assert tenant_b.name == "Client B One"
    assert tenant_b.status.value == "active"
    versions = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(AgentConfig)
        .where(AgentConfig.tenant_id == b["tenant_id"])
    )
    assert versions == 1


async def test_by_id_team_and_keys_are_bounded(client, console_world, db_session) -> None:
    a, b = console_world["a"], console_world["b"]
    b_member = await add_console_member(db_session, partner_id=b["partner_id"], role="builder")
    # A (owner) tries to change B's member: not found, unchanged.
    r = await client.patch(
        f"/console/team/members/{b_member['membership_id']}/role",
        headers=a["headers"](),
        json={"role": "owner"},
    )
    assert r.status_code == 404
    r = await client.delete(
        f"/console/team/members/{b_member['membership_id']}", headers=a["headers"]()
    )
    assert r.status_code == 404
    assert (await client.get("/console/me", headers=b_member["headers"]())).json()[
        "role"
    ] == "builder"

    # Keys: A creates a key, B cannot rotate/revoke it.
    created = await client.post("/console/keys", headers=a["headers"](), json={})
    assert created.status_code == 201, created.text
    key_id = created.json()["id"]
    assert (
        await client.post(f"/console/keys/{key_id}/revoke", headers=b["headers"]())
    ).status_code == 404
    assert (
        await client.post(f"/console/keys/{key_id}/rotate", headers=b["headers"](), json={})
    ).status_code == 404
    key = await db_session.get(PartnerApiKey, uuid.UUID(key_id))
    assert key is not None and key.revoked_at is None


# ── 2. by enumeration ──────────────────────────────────────────────────


async def test_by_enumeration_lists_contain_only_own_rows(
    client, console_world, db_session
) -> None:
    a, b = console_world["a"], console_world["b"]
    # Give B more clients so a leak would be visible.
    from nexus_api.db.models import PartnerTenant, TenantPlan

    for i in range(3):
        tid = uuid.uuid4()
        db_session.add(
            Tenant(id=tid, name=f"B extra {i}", slug=f"b-extra-{tid.hex[:6]}", plan=TenantPlan.PRO)
        )
        await db_session.flush()
        db_session.add(
            PartnerTenant(
                partner_id=b["partner_id"], external_client_ref=f"b-extra-{i}", tenant_id=tid
            )
        )
    await add_console_member(db_session, partner_id=b["partner_id"], role="analyst")
    await db_session.commit()

    page = (await client.get("/console/clients?limit=1", headers=a["headers"]())).json()
    assert page["total"] == 1
    assert [c["external_client_ref"] for c in page["items"]] == [a["ref"]]
    page2 = (await client.get("/console/clients?limit=1&offset=1", headers=a["headers"]())).json()
    assert page2["items"] == []

    team = (await client.get("/console/team", headers=a["headers"]())).json()
    assert [m["email"] for m in team["members"]] == ["owner-a@example.com"]

    keys = (await client.get("/console/keys", headers=a["headers"]())).json()
    assert keys == []

    usage = (await client.get("/console/usage", headers=a["headers"]())).json()
    assert {bkt["external_client_ref"] for bkt in usage["buckets"]} <= {a["ref"]}


async def test_by_enumeration_audit_only_shows_own_partner(
    client, console_world, db_session
) -> None:
    a, b = console_world["a"], console_world["b"]
    db_session.add_all(
        [
            AuditLog(
                tenant_id=b["tenant_id"],
                actor="console:owner-b@example.com",
                action="console.client.update",
                target=f"tenant:{b['tenant_id']}",
                after_json={"name": "B private"},
            ),
            AuditLog(
                tenant_id=None,
                actor="console:owner-b@example.com",
                action="console.member.invite",
                target=f"partner:{b['partner_id']}",
                after_json={"email": "secret@b.example", "role": "admin"},
            ),
            AuditLog(
                tenant_id=a["tenant_id"],
                actor="console:owner-a@example.com",
                action="console.client.update",
                target=f"tenant:{a['tenant_id']}",
                after_json={"name": "A visible"},
            ),
        ]
    )
    await db_session.commit()
    resp = await client.get("/console/audit", headers=a["headers"]())
    assert resp.status_code == 200
    body = resp.text
    assert "owner-a@example.com" in body
    assert "owner-b" not in body
    assert "secret@b.example" not in body
    assert "B private" not in body


# ── 3. by error ────────────────────────────────────────────────────────


async def test_by_error_shapes_are_identical(client, console_world) -> None:
    a, b = console_world["a"], console_world["b"]
    foreign = await client.get(f"/console/clients/{b['ref']}", headers=a["headers"]())
    missing = await client.get("/console/clients/nope", headers=a["headers"]())
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert set(foreign.headers) - {"date"} == set(missing.headers) - {"date"}


# ── 4. by order / filter ───────────────────────────────────────────────


async def test_by_filter_search_cannot_surface_other_partner(client, console_world) -> None:
    a = console_world["a"]
    for query in ("Client B", "client-b-1", "B One"):
        resp = await client.get(f"/console/clients?q={query}", headers=a["headers"]())
        assert resp.status_code == 200
        assert resp.json()["items"] == [], query
    for sort in ("name", "created_at", "updated_at", "status"):
        for order in ("asc", "desc"):
            resp = await client.get(
                f"/console/clients?sort={sort}&order={order}", headers=a["headers"]()
            )
            refs = [c["external_client_ref"] for c in resp.json()["items"]]
            assert refs == [a["ref"]]
    resp = await client.get("/console/audit?client=client-b-1", headers=a["headers"]())
    assert resp.status_code == 200 and resp.json()["items"] == []
    resp = await client.get("/console/usage?client=client-b-1", headers=a["headers"]())
    assert resp.status_code == 200 and resp.json()["buckets"] == []


# ── 5. by timing ───────────────────────────────────────────────────────


async def test_by_timing_foreign_and_missing_refs_are_indistinguishable(
    client, console_world, db_session
) -> None:
    """Both stop at the ``partner_tenants`` lookup — no tenant scope is
    opened, so nothing later can add work proportional to B's data. The
    timing assertion is a sanity check with a wide margin, not the proof;
    the proof is structural (same code path) and the identical body."""
    a, b = console_world["a"], console_world["b"]
    await _seed_agent(db_session, b["tenant_id"], prompt="x" * 100_000)

    async def _sample(ref: str, n: int = 12) -> list[float]:
        out = []
        for _ in range(n):
            t0 = time.perf_counter()
            r = await client.get(f"/console/clients/{ref}/agent", headers=a["headers"]())
            out.append(time.perf_counter() - t0)
            assert r.status_code == 404
        return out

    foreign = _sample(b["ref"])
    missing = _sample(f"missing-{uuid.uuid4().hex[:6]}")
    f_med = statistics.median(await foreign)
    m_med = statistics.median(await missing)
    # Same order of magnitude: neither path touches the tenant's rows.
    assert max(f_med, m_med) < 4 * max(min(f_med, m_med), 0.001), (f_med, m_med)
