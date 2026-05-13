"""Block Q — seed metrics endpoint."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _seed_config(
    db_session,
    tenant_id: uuid.UUID,
    *,
    seed_ref: str = "barbershop_v1",
    version: int = 1,
    status_value: str = "active",
) -> None:
    from nexus_api.db.models import AgentConfig, AgentConfigStatus

    await db_session.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
    )
    await db_session.execute(text("SET LOCAL ROLE nexus_app"))
    db_session.add(
        AgentConfig(
            tenant_id=tenant_id,
            version=version,
            status=AgentConfigStatus(status_value),
            system_prompt_rendered="x",
            channels=[],
            tools=[],
            policies={},
            seed_template_ref=seed_ref,
        )
    )
    await db_session.flush()


async def test_metrics_empty_when_no_tenants_use_seed(client, admin_headers) -> None:
    r = await client.get("/admin/seed-templates/barbershop_v1/metrics", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "barbershop_v1"
    assert body["tenant_count"] == 0
    assert body["active_count"] == 0
    assert body["eval_pass_rate_avg"] is None
    assert body["eval_pass_rate_count"] == 0


async def test_metrics_unknown_seed_404(client, admin_headers) -> None:
    r = await client.get("/admin/seed-templates/nonexistent_v1/metrics", headers=admin_headers)
    assert r.status_code == 404


async def test_metrics_counts_tenants_and_actives(
    client, admin_headers, seed_tenants, db_session
) -> None:
    """Two tenants apply ``barbershop_v1``; one is ACTIVE, one STAGED.
    Expected: ``tenant_count=2``, ``active_count=1``."""
    a = seed_tenants["a"]
    b = seed_tenants["b"]
    async with db_session.begin():
        await _seed_config(db_session, a, status_value="active", version=1)
        await _seed_config(db_session, b, status_value="staged", version=1)

    r = await client.get("/admin/seed-templates/barbershop_v1/metrics", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant_count"] == 2
    assert body["active_count"] == 1


async def test_metrics_eval_pass_rate_aggregates_per_tenant(
    client, admin_headers, seed_tenants, db_session
) -> None:
    """Two tenants use the seed; each has a passed eval_run with
    distinct pass_rate. The aggregate is the average of those two
    latest runs."""
    from datetime import UTC, datetime
    from decimal import Decimal

    from nexus_api.db.models import EvalDataset, EvalRun, EvalRunStatus

    a = seed_tenants["a"]
    b = seed_tenants["b"]
    async with db_session.begin():
        await _seed_config(db_session, a, status_value="active", version=1)
        await _seed_config(db_session, b, status_value="active", version=2)

        # One dataset per tenant — promotion gate doesn't enter into
        # this test, we just need dataset_id FKs.
        for tid in (a, b):
            await db_session.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"),
                {"t": str(tid)},
            )
            await db_session.execute(text("SET LOCAL ROLE nexus_app"))
            db_session.add(EvalDataset(tenant_id=tid, name="ds", version=1))
            await db_session.flush()
        # Fetch the dataset ids we just inserted (one per tenant).
        from sqlalchemy import select

        await db_session.execute(text("RESET ROLE"))
        await db_session.execute(text("SELECT set_config('app.tenant_id', '', true)"))
        rows = (await db_session.execute(select(EvalDataset))).scalars().all()
        a_ds = next(d.id for d in rows if d.tenant_id == a)
        b_ds = next(d.id for d in rows if d.tenant_id == b)

        # Tenant A passed eval_run with 0.9 pass_rate against version 1
        db_session.add_all(
            [
                EvalRun(
                    tenant_id=a,
                    dataset_id=a_ds,
                    dataset_version=1,
                    agent_config_version=1,
                    agent_config_status="active",
                    status=EvalRunStatus.PASSED.value,
                    case_count=10,
                    pass_count=9,
                    fail_count=1,
                    error_count=0,
                    pass_rate=Decimal("0.900"),
                    actor="test",
                    started_at=datetime.now(UTC),
                    finished_at=datetime.now(UTC),
                ),
                # Tenant B passed with 1.000 against version 2
                EvalRun(
                    tenant_id=b,
                    dataset_id=b_ds,
                    dataset_version=1,
                    agent_config_version=2,
                    agent_config_status="active",
                    status=EvalRunStatus.PASSED.value,
                    case_count=10,
                    pass_count=10,
                    fail_count=0,
                    error_count=0,
                    pass_rate=Decimal("1.000"),
                    actor="test",
                    started_at=datetime.now(UTC),
                    finished_at=datetime.now(UTC),
                ),
            ]
        )
        await db_session.flush()

    r = await client.get("/admin/seed-templates/barbershop_v1/metrics", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant_count"] == 2
    assert body["eval_pass_rate_count"] == 2
    # avg(0.9, 1.0) = 0.95
    assert body["eval_pass_rate_avg"] == "0.950"


async def test_metrics_requires_auth(client) -> None:
    r = await client.get("/admin/seed-templates/barbershop_v1/metrics")
    assert r.status_code == 401
