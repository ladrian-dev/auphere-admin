"""Guarantee 9 — QA Playground concurrent isolation under load (ADR-020 Fase 6).

The feature spec demands 100 runs × 5 operators × 5 tenants → 0 leaks RLS +
0 side-effects ejecutados, hit through the **HTTP surface** that real
operators see (not the DB directly). This file complements
``test_8_qa_thread_isolation_by_operator.py`` (DB-level) by exercising the
``/qa/threads`` router end-to-end with concurrent traffic and verifies:

  (a) Each operator sees EXACTLY their own threads (count + ids match).
  (b) Zero leaks: no operator ever sees a thread with ``operator_id`` ≠
      its own across listing AND detail GETs.
  (c) Cross-operator INSERT (forging ``operator_id``) is rejected by the
      policy's ``WITH CHECK`` clause at the DB layer — this path is
      unreachable from the API (the handler stamps ``operator_id`` from
      the verified header), so the spoof has to be synthesised against
      the DB directly. We keep it here because the spec lists it as the
      third concurrent-isolation assertion and it belongs next to (a)+(b).

Marked ``isolation + slow`` — CI runs the isolation suite even when slow.

Pool sizing: ``pool_size=10, max_overflow=20`` (apps/api/src/nexus_api/db/base.py)
gives 30 max connections. We cap inflight requests at 24 with a semaphore
to leave headroom for the FastAPI request handling.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from collections import defaultdict

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from nexus_api.db.models import Tenant, TenantPlan
from nexus_api.db.models.qa import QAThread

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation, pytest.mark.slow]


# ── tunables ────────────────────────────────────────────────────────────────

NUM_OPERATORS = 5
NUM_TENANTS = 5
NUM_RUNS = 100
MAX_INFLIGHT = 24


# ── helpers ─────────────────────────────────────────────────────────────────


def _hdrs(operator_id: uuid.UUID, admin_headers: dict[str, str]) -> dict[str, str]:
    return {**admin_headers, "X-Operator-Id": str(operator_id)}


async def _seed_tenants(db_session, n: int) -> list[uuid.UUID]:
    ids = [uuid.uuid4() for _ in range(n)]
    async with db_session.begin():
        db_session.add_all(
            [
                Tenant(
                    id=t,
                    name=f"QA-Conc-{i}",
                    slug=f"qa-conc-{t.hex[:8]}",
                    plan=TenantPlan.PRO,
                )
                for i, t in enumerate(ids)
            ]
        )
    return ids


# ── tests ───────────────────────────────────────────────────────────────────


async def test_qa_concurrent_100_runs_zero_leaks(client, admin_headers, db_session):
    """100 concurrent thread creations × 5 ops × 5 tenants, then verify
    every operator's list/detail view is RLS-clean.
    """
    tenants = await _seed_tenants(db_session, NUM_TENANTS)
    operators = [uuid.uuid4() for _ in range(NUM_OPERATORS)]

    rng = random.Random(20260519)
    pairs: list[tuple[uuid.UUID, uuid.UUID, int]] = [
        (rng.choice(operators), rng.choice(tenants), i) for i in range(NUM_RUNS)
    ]

    sem = asyncio.Semaphore(MAX_INFLIGHT)

    async def create_one(op: uuid.UUID, tenant: uuid.UUID, i: int) -> tuple[
        uuid.UUID, uuid.UUID, str
    ]:
        async with sem:
            r = await client.post(
                "/qa/threads",
                json={"tenant_id": str(tenant), "title": f"run-{i:03d}"},
                headers=_hdrs(op, admin_headers),
            )
        assert r.status_code == 201, (
            f"create failed op={op} tenant={tenant} status={r.status_code} body={r.text}"
        )
        body = r.json()
        # The handler MUST stamp the verified operator id, not anything from the body.
        assert body["operator_id"] == str(op)
        assert body["tenant_id"] == str(tenant)
        return op, tenant, body["id"]

    created = await asyncio.gather(*(create_one(op, t, i) for (op, t, i) in pairs))

    expected_ids: dict[uuid.UUID, set[str]] = defaultdict(set)
    for op, _t, tid in created:
        expected_ids[op].add(tid)

    # Sanity: each operator created at least one (with 100 picks across 5 the
    # probability of any operator getting zero is < 1e-9).
    for op in operators:
        assert len(expected_ids[op]) > 0, f"operator {op} got zero runs — RNG drift?"

    # (a) + (b): each operator lists per tenant; only own threads visible.
    leaks: list[tuple[uuid.UUID, dict]] = []

    async def verify_one(op: uuid.UUID) -> tuple[uuid.UUID, set[str]]:
        seen: set[str] = set()
        for tenant in tenants:
            r = await client.get(
                f"/qa/threads?tenant_id={tenant}&limit=200",
                headers=_hdrs(op, admin_headers),
            )
            assert r.status_code == 200
            for t in r.json():
                if t["operator_id"] != str(op):
                    leaks.append((op, t))
                seen.add(t["id"])
        # Also exercise detail GET on a sample of own threads (round-trip).
        for tid in list(expected_ids[op])[:5]:
            r = await client.get(
                f"/qa/threads/{tid}", headers=_hdrs(op, admin_headers)
            )
            assert r.status_code == 200, f"own thread {tid} not visible to creator"
            assert r.json()["operator_id"] == str(op)
        # Cross-operator detail GET: should 404 (RLS hides → not found).
        other = next(o for o in operators if o != op)
        sample_other = next(iter(expected_ids[other]), None)
        if sample_other is not None:
            r = await client.get(
                f"/qa/threads/{sample_other}",
                headers=_hdrs(op, admin_headers),
            )
            assert r.status_code == 404, (
                f"LEAK via detail GET: op {op} read thread of {other}"
            )
        return op, seen

    sweeps = await asyncio.gather(*(verify_one(op) for op in operators))

    assert not leaks, f"RLS leaks detected: {leaks[:3]}"

    for op, seen in sweeps:
        assert seen == expected_ids[op], (
            f"operator {op} expected {len(expected_ids[op])} ids, saw {len(seen)} "
            f"(missing={expected_ids[op] - seen}, extra={seen - expected_ids[op]})"
        )

    # (c) WITH CHECK rejection of forged operator_id (DB layer — the HTTP
    # path never exposes this attack surface because the handler ignores
    # the body operator_id and stamps the verified header value).
    forger = operators[0]
    victim = operators[1]
    async with db_session.begin():
        await db_session.execute(
            text("SELECT set_config('app.operator_id', :o, true)"),
            {"o": str(forger)},
        )
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": str(tenants[0])},
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            QAThread(
                operator_id=victim,
                tenant_id=tenants[0],
                title="forged-by-op-A-pretending-to-be-op-B",
            )
        )
        with pytest.raises((IntegrityError, ProgrammingError)):
            await db_session.flush()


async def test_qa_concurrent_repeats_stable(client, admin_headers, db_session):
    """Smaller, faster variant focused on robustness across repeated bursts.

    The spec asks for 3 consecutive green runs of the 100×5×5 case. CI runs
    that one via the test above; this lighter variant catches the common
    failure mode where the FIRST burst is clean but a SECOND burst (with
    leftover engine state, half-released connections) leaks. We run 3
    bursts of 25 in the same test and assert each completes cleanly.
    """
    tenants = await _seed_tenants(db_session, 3)
    operators = [uuid.uuid4() for _ in range(3)]
    sem = asyncio.Semaphore(MAX_INFLIGHT)

    async def create(op: uuid.UUID, tenant: uuid.UUID, label: str) -> str:
        async with sem:
            r = await client.post(
                "/qa/threads",
                json={"tenant_id": str(tenant), "title": label},
                headers=_hdrs(op, admin_headers),
            )
        assert r.status_code == 201
        return r.json()["id"]

    rng = random.Random(7)
    per_op: dict[uuid.UUID, set[str]] = defaultdict(set)

    for burst in range(3):
        pairs = [
            (rng.choice(operators), rng.choice(tenants), f"b{burst}-{i}")
            for i in range(25)
        ]
        ids = await asyncio.gather(*(create(op, t, lbl) for (op, t, lbl) in pairs))
        for (op, _t, _lbl), tid in zip(pairs, ids):
            per_op[op].add(tid)

        # After each burst, verify each operator sees the right cumulative set.
        for op in operators:
            r = await client.get(
                f"/qa/threads?limit=200", headers=_hdrs(op, admin_headers)
            )
            assert r.status_code == 200
            visible = {t["id"] for t in r.json()}
            assert per_op[op].issubset(visible), (
                f"burst {burst}: operator {op} lost rows between bursts "
                f"(missing={per_op[op] - visible})"
            )
            # No foreign rows.
            for t in r.json():
                assert t["operator_id"] == str(op), (
                    f"burst {burst}: LEAK op={op} saw thread of {t['operator_id']}"
                )
