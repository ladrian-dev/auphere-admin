"""Block P — admin endpoint tests for evals.

CRUD + run trigger + promotion gate. Uses FakeTestAgentProvider (from
Bloque O) to script sandbox responses, and FakeJudgeProvider so we
never hit Anthropic.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text

from nexus_api.api.admin.agent_configs import set_test_agent_provider
from nexus_api.api.admin.evals import set_judge_provider
from nexus_api.services.evals import FakeJudgeProvider
from nexus_api.services.test_agent import FakeTestAgentProvider

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def fake_agent() -> AsyncIterator[FakeTestAgentProvider]:
    provider = FakeTestAgentProvider()
    set_test_agent_provider(provider)
    try:
        yield provider
    finally:
        set_test_agent_provider(None)


@pytest_asyncio.fixture
async def fake_judge() -> AsyncIterator[FakeJudgeProvider]:
    provider = FakeJudgeProvider()
    set_judge_provider(provider)
    try:
        yield provider
    finally:
        set_judge_provider(None)


async def _seed_active_config(db_session, tenant_id: uuid.UUID, *, version: int = 1) -> None:
    from nexus_api.db.models import AgentConfig, AgentConfigStatus

    await db_session.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
    )
    await db_session.execute(text("SET LOCAL ROLE nexus_app"))
    db_session.add(
        AgentConfig(
            tenant_id=tenant_id,
            version=version,
            status=AgentConfigStatus.ACTIVE,
            system_prompt_rendered="Sos el asistente.",
            channels=[],
            tools=["booking.check_availability"],
            policies={},
            seed_template_ref="barbershop_v1",
        )
    )
    await db_session.flush()


async def _set_eval_required(db_session, tenant_id: uuid.UUID, required: bool) -> None:
    await db_session.execute(
        text("UPDATE tenants SET eval_required = :v WHERE id = :id"),
        {"v": required, "id": str(tenant_id)},
    )
    await db_session.flush()


# ── Dataset CRUD ──────────────────────────────────────────────────────────


async def test_create_and_list_dataset(client, admin_headers, seed_tenants) -> None:
    tid = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tid}/eval-datasets",
        headers=admin_headers,
        json={"name": "regresión barbería", "description": "core flows"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "regresión barbería"
    assert body["version"] == 1
    assert body["pass_threshold"] == "0.950"

    r2 = await client.get(f"/admin/tenants/{tid}/eval-datasets", headers=admin_headers)
    assert r2.status_code == 200
    assert len(r2.json()) == 1


async def test_create_dataset_duplicate_name_409(client, admin_headers, seed_tenants) -> None:
    tid = seed_tenants["a"]
    r1 = await client.post(
        f"/admin/tenants/{tid}/eval-datasets",
        headers=admin_headers,
        json={"name": "regresión"},
    )
    assert r1.status_code == 201
    r2 = await client.post(
        f"/admin/tenants/{tid}/eval-datasets",
        headers=admin_headers,
        json={"name": "regresión"},
    )
    assert r2.status_code == 409


async def test_archive_dataset_hides_from_list(client, admin_headers, seed_tenants) -> None:
    tid = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tid}/eval-datasets",
        headers=admin_headers,
        json={"name": "x"},
    )
    dataset_id = r.json()["id"]
    arch = await client.delete(
        f"/admin/tenants/{tid}/eval-datasets/{dataset_id}", headers=admin_headers
    )
    assert arch.status_code == 204
    lst = await client.get(f"/admin/tenants/{tid}/eval-datasets", headers=admin_headers)
    assert lst.json() == []


# ── Case CRUD ─────────────────────────────────────────────────────────────


async def test_create_case_assigns_next_idx(client, admin_headers, seed_tenants) -> None:
    tid = seed_tenants["a"]
    ds = (
        await client.post(
            f"/admin/tenants/{tid}/eval-datasets",
            headers=admin_headers,
            json={"name": "ds"},
        )
    ).json()
    payload = {
        "name": "first turn",
        "user_message": "hola",
        "assertions": {"must_emit_text": True},
    }
    c1 = await client.post(
        f"/admin/tenants/{tid}/eval-datasets/{ds['id']}/cases",
        headers=admin_headers,
        json=payload,
    )
    assert c1.status_code == 201, c1.text
    assert c1.json()["idx"] == 0

    c2 = await client.post(
        f"/admin/tenants/{tid}/eval-datasets/{ds['id']}/cases",
        headers=admin_headers,
        json={**payload, "name": "second turn"},
    )
    assert c2.json()["idx"] == 1


async def test_create_case_rejects_empty_assertions(client, admin_headers, seed_tenants) -> None:
    tid = seed_tenants["a"]
    ds = (
        await client.post(
            f"/admin/tenants/{tid}/eval-datasets",
            headers=admin_headers,
            json={"name": "ds"},
        )
    ).json()
    r = await client.post(
        f"/admin/tenants/{tid}/eval-datasets/{ds['id']}/cases",
        headers=admin_headers,
        json={"name": "x", "user_message": "hola", "assertions": {}},
    )
    assert r.status_code == 400
    assert "at least one" in r.json()["detail"]


# ── Runs ──────────────────────────────────────────────────────────────────


async def test_run_dataset_passing_path(
    client, admin_headers, seed_tenants, db_session, fake_agent, fake_judge
) -> None:
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _seed_active_config(db_session, tid)

    ds = (
        await client.post(
            f"/admin/tenants/{tid}/eval-datasets",
            headers=admin_headers,
            json={"name": "core"},
        )
    ).json()
    await client.post(
        f"/admin/tenants/{tid}/eval-datasets/{ds['id']}/cases",
        headers=admin_headers,
        json={
            "name": "saludo",
            "user_message": "hola",
            "assertions": {
                "must_contain": ["asistente"],
                "must_emit_text": True,
                "judge_questions": ["¿respondió con cortesía?"],
            },
        },
    )

    r = await client.post(
        f"/admin/tenants/{tid}/eval-datasets/{ds['id']}/run",
        headers=admin_headers,
        json={},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "passed"
    assert body["case_count"] == 1
    assert body["pass_count"] == 1
    assert body["pass_rate"] == "1.000"
    assert len(body["results"]) == 1
    # Three assertion results: must_contain + must_emit_text + judge.
    assert len(body["results"][0]["assertion_results"]) == 3


async def test_run_dataset_failing_path(
    client, admin_headers, seed_tenants, db_session, fake_agent, fake_judge
) -> None:
    """A must_contain that the default Fake response doesn't satisfy → fail."""
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _seed_active_config(db_session, tid)

    ds = (
        await client.post(
            f"/admin/tenants/{tid}/eval-datasets",
            headers=admin_headers,
            json={"name": "core"},
        )
    ).json()
    await client.post(
        f"/admin/tenants/{tid}/eval-datasets/{ds['id']}/cases",
        headers=admin_headers,
        json={
            "name": "agenda",
            "user_message": "agendá",
            "assertions": {"must_contain": ["confirmado"]},  # Fake never says this
        },
    )

    r = await client.post(
        f"/admin/tenants/{tid}/eval-datasets/{ds['id']}/run",
        headers=admin_headers,
        json={},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "failed"
    assert body["fail_count"] == 1
    assert body["pass_rate"] == "0.000"


async def test_run_judge_error_marks_case_error(
    client, admin_headers, seed_tenants, db_session, fake_agent, fake_judge
) -> None:
    """If the judge raises, the assertion is recorded as ``judge_error`` and
    the case status becomes ``error`` (distinct from ``fail``)."""
    from nexus_api.services.evals.judge import JudgeError

    fake_judge.responder = lambda q, m, t: JudgeError("judge upstream 500")
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _seed_active_config(db_session, tid)

    ds = (
        await client.post(
            f"/admin/tenants/{tid}/eval-datasets",
            headers=admin_headers,
            json={"name": "judge-only"},
        )
    ).json()
    await client.post(
        f"/admin/tenants/{tid}/eval-datasets/{ds['id']}/cases",
        headers=admin_headers,
        json={
            "name": "judge",
            "user_message": "?",
            "assertions": {"judge_questions": ["¿hizo X?"]},
        },
    )

    r = await client.post(
        f"/admin/tenants/{tid}/eval-datasets/{ds['id']}/run",
        headers=admin_headers,
        json={},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["error_count"] == 1
    assert body["status"] == "error"


async def test_run_empty_dataset_400(
    client, admin_headers, seed_tenants, db_session, fake_agent, fake_judge
) -> None:
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _seed_active_config(db_session, tid)
    ds = (
        await client.post(
            f"/admin/tenants/{tid}/eval-datasets",
            headers=admin_headers,
            json={"name": "empty"},
        )
    ).json()
    r = await client.post(
        f"/admin/tenants/{tid}/eval-datasets/{ds['id']}/run",
        headers=admin_headers,
        json={},
    )
    assert r.status_code == 400


async def test_list_runs_filter_by_version(
    client, admin_headers, seed_tenants, db_session, fake_agent, fake_judge
) -> None:
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _seed_active_config(db_session, tid, version=7)
    ds = (
        await client.post(
            f"/admin/tenants/{tid}/eval-datasets",
            headers=admin_headers,
            json={"name": "x"},
        )
    ).json()
    await client.post(
        f"/admin/tenants/{tid}/eval-datasets/{ds['id']}/cases",
        headers=admin_headers,
        json={
            "name": "c",
            "user_message": "hi",
            "assertions": {"must_emit_text": True},
        },
    )
    await client.post(
        f"/admin/tenants/{tid}/eval-datasets/{ds['id']}/run",
        headers=admin_headers,
        json={},
    )
    r = await client.get(
        f"/admin/tenants/{tid}/eval-runs?agent_config_version=7",
        headers=admin_headers,
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["agent_config_version"] == 7
    assert rows[0]["status"] == "passed"


# ── Promotion gate ────────────────────────────────────────────────────────


async def test_promote_blocked_without_passing_run(
    client, admin_headers, seed_tenants, db_session, fake_agent, fake_judge
) -> None:
    """Tenant has ``eval_required=true`` but no eval_run for the candidate
    version → 409."""
    from nexus_api.db.models import AgentConfig, AgentConfigStatus

    tid = seed_tenants["a"]
    async with db_session.begin():
        await _set_eval_required(db_session, tid, True)
        # Need a STAGED version to promote (not ACTIVE).
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)}
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            AgentConfig(
                tenant_id=tid,
                version=1,
                status=AgentConfigStatus.STAGED,
                system_prompt_rendered="x",
                channels=[],
                tools=[],
                policies={},
            )
        )
        await db_session.flush()

    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/1/promote",
        headers=admin_headers,
    )
    assert r.status_code == 409
    assert "eval gate" in r.json()["detail"]


async def test_promote_allowed_with_passing_run(
    client, admin_headers, seed_tenants, db_session, fake_agent, fake_judge
) -> None:
    """End-to-end: enable eval_required, stage v1, run evals that pass,
    promote works."""
    from nexus_api.db.models import AgentConfig, AgentConfigStatus

    tid = seed_tenants["a"]
    async with db_session.begin():
        await _set_eval_required(db_session, tid, True)
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)}
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            AgentConfig(
                tenant_id=tid,
                version=1,
                status=AgentConfigStatus.STAGED,
                system_prompt_rendered="Sos el asistente.",
                channels=[],
                tools=[],
                policies={},
            )
        )
        await db_session.flush()

    ds = (
        await client.post(
            f"/admin/tenants/{tid}/eval-datasets",
            headers=admin_headers,
            json={"name": "gate"},
        )
    ).json()
    await client.post(
        f"/admin/tenants/{tid}/eval-datasets/{ds['id']}/cases",
        headers=admin_headers,
        json={
            "name": "c",
            "user_message": "hi",
            "assertions": {"must_emit_text": True},
        },
    )
    run = await client.post(
        f"/admin/tenants/{tid}/eval-datasets/{ds['id']}/run",
        headers=admin_headers,
        json={"agent_config_version": 1},
    )
    assert run.status_code == 201, run.text
    assert run.json()["status"] == "passed"

    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/1/promote",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"


async def test_promote_override_with_reason(
    client, admin_headers, seed_tenants, db_session, fake_agent, fake_judge
) -> None:
    from sqlalchemy import select

    from nexus_api.db.models import AgentConfig, AgentConfigStatus, AuditLog

    tid = seed_tenants["a"]
    async with db_session.begin():
        await _set_eval_required(db_session, tid, True)
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)}
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            AgentConfig(
                tenant_id=tid,
                version=1,
                status=AgentConfigStatus.STAGED,
                system_prompt_rendered="x",
                channels=[],
                tools=[],
                policies={},
            )
        )
        await db_session.flush()

    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/1/promote",
        headers=admin_headers,
        json={"override": True, "reason": "incidente en prod, rollback rápido"},
    )
    assert r.status_code == 200, r.text
    # Audit row was written.
    rows = (
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.action == "agent_config.promote.override")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_promote_override_requires_reason(
    client, admin_headers, seed_tenants, db_session, fake_agent, fake_judge
) -> None:
    from nexus_api.db.models import AgentConfig, AgentConfigStatus

    tid = seed_tenants["a"]
    async with db_session.begin():
        await _set_eval_required(db_session, tid, True)
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)}
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            AgentConfig(
                tenant_id=tid,
                version=1,
                status=AgentConfigStatus.STAGED,
                system_prompt_rendered="x",
                channels=[],
                tools=[],
                policies={},
            )
        )
        await db_session.flush()

    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/1/promote",
        headers=admin_headers,
        json={"override": True, "reason": ""},
    )
    assert r.status_code == 400


async def test_promote_unchanged_when_eval_required_false(
    client, admin_headers, seed_tenants, db_session
) -> None:
    """The gate is opt-in; with the flag off, promote behaves like
    before — no run required."""
    from nexus_api.db.models import AgentConfig, AgentConfigStatus

    tid = seed_tenants["a"]
    async with db_session.begin():
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)}
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            AgentConfig(
                tenant_id=tid,
                version=1,
                status=AgentConfigStatus.STAGED,
                system_prompt_rendered="x",
                channels=[],
                tools=[],
                policies={},
            )
        )
        await db_session.flush()

    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/1/promote",
        headers=admin_headers,
    )
    assert r.status_code == 200
