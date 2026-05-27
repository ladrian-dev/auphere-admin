"""Block P — admin endpoint tests for evals.

CRUD + run trigger + promotion gate. Roadmap E2: the runner now drives
the REAL compiled pipeline, so the run tests inject an
``InMemoryProvider``-backed ``LLMRouter`` via ``set_eval_llm_router``
(scripted: classify → ``info``, handler → a fixed text reply). The judge
is still faked via ``set_judge_provider``. No call ever reaches LiteLLM.

The trigger endpoint went async (202 + asyncio.create_task) to survive
prod proxy timeouts on real-sized datasets. The run-related tests
exercise that shape: POST returns immediately with ``status=pending``
and an empty ``results`` list, then ``_await_run_terminal`` polls
``GET /eval-runs/{id}`` until the run reaches a terminal status, then
the assertions run against the polled detail.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text

from nexus_api.api.admin.evals import set_judge_provider
from nexus_api.services.evals import FakeJudgeProvider, set_eval_llm_router

pytestmark = pytest.mark.asyncio


_TERMINAL = {"passed", "failed", "error"}


async def _await_run_terminal(
    client: Any,
    tid: uuid.UUID,
    run_id: str,
    headers: dict,
    *,
    timeout_s: float = 5.0,
    poll_s: float = 0.05,
) -> dict:
    """Poll ``GET /eval-runs/{id}`` until ``status`` is terminal.

    Mirrors the polling shape the admin UI uses. Fast tight loop because
    the fake judge + in-memory router resolve in microseconds; the
    background ``asyncio.create_task`` just needs the event loop to come
    back around.
    """
    deadline = asyncio.get_event_loop().time() + timeout_s
    while True:
        r = await client.get(
            f"/admin/tenants/{tid}/eval-runs/{run_id}",
            headers=headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        if body["status"] in _TERMINAL:
            return body
        if asyncio.get_event_loop().time() >= deadline:
            raise AssertionError(
                f"eval run {run_id} did not reach terminal in {timeout_s}s — "
                f"last status={body['status']!r} body={body!r}"
            )
        await asyncio.sleep(poll_s)


@pytest_asyncio.fixture
async def eval_router() -> AsyncIterator[object]:
    """Inject an in-memory LLM router into the eval driver.

    classify always returns the ``info`` intent; every handler reply is
    a fixed courteous text. No tool calls are scripted, so the ReAct
    loop terminates on the first iteration with that text."""
    from nexus_worker.runtime.llm import InMemoryProvider, LLMRouter

    provider = InMemoryProvider()

    def responder(call: object) -> str:
        if getattr(call, "role", "") == "classify":
            return "info"
        return "Hola, soy el asistente. ¿En qué te puedo ayudar?"

    provider.responder = responder
    router = LLMRouter(
        provider=provider,
        classify_model="t/classify",
        respond_model="t/respond",
        fallback_model="t/fallback",
    )
    set_eval_llm_router(router)
    try:
        yield provider
    finally:
        set_eval_llm_router(None)


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
    client, admin_headers, seed_tenants, db_session, eval_router, fake_judge
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
    assert r.status_code == 202, r.text
    pending = r.json()
    assert pending["status"] == "pending"
    assert pending["results"] == []
    body = await _await_run_terminal(client, tid, pending["id"], admin_headers)
    assert body["status"] == "passed"
    assert body["case_count"] == 1
    assert body["pass_count"] == 1
    assert body["pass_rate"] == "1.000"
    assert len(body["results"]) == 1
    # Three assertion results: must_contain + must_emit_text + judge.
    assert len(body["results"][0]["assertion_results"]) == 3
    # The transcript carries the real pipeline output.
    transcript = body["results"][0]["transcript"]
    assert transcript["intent"] == "info"
    assert "asistente" in transcript["assistant_message"].lower()


async def test_run_dataset_failing_path(
    client, admin_headers, seed_tenants, db_session, eval_router, fake_judge
) -> None:
    """A must_contain the scripted reply doesn't satisfy → fail."""
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
            "assertions": {"must_contain": ["confirmado"]},  # the reply never says this
        },
    )

    r = await client.post(
        f"/admin/tenants/{tid}/eval-datasets/{ds['id']}/run",
        headers=admin_headers,
        json={},
    )
    assert r.status_code == 202, r.text
    body = await _await_run_terminal(client, tid, r.json()["id"], admin_headers)
    assert body["status"] == "failed"
    assert body["fail_count"] == 1
    assert body["pass_rate"] == "0.000"


async def test_run_judge_error_marks_case_error(
    client, admin_headers, seed_tenants, db_session, eval_router, fake_judge
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
    assert r.status_code == 202, r.text
    body = await _await_run_terminal(client, tid, r.json()["id"], admin_headers)
    assert body["error_count"] == 1
    assert body["status"] == "error"


async def test_run_judge_unknown_marks_case_error(
    client, admin_headers, seed_tenants, db_session, eval_router, fake_judge
) -> None:
    """E2.2 — an ``unknown`` verdict is not a pass: the case lands on
    ``error`` so the operator sees the eval was inconclusive."""
    from nexus_api.services.evals.judge import JudgeReply

    fake_judge.responder = lambda q, m, t: JudgeReply(
        verdict="unknown", reason="sin evidencia", raw="{}"
    )
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _seed_active_config(db_session, tid)

    ds = (
        await client.post(
            f"/admin/tenants/{tid}/eval-datasets",
            headers=admin_headers,
            json={"name": "judge-unknown"},
        )
    ).json()
    await client.post(
        f"/admin/tenants/{tid}/eval-datasets/{ds['id']}/cases",
        headers=admin_headers,
        json={
            "name": "ambiguo",
            "user_message": "?",
            "assertions": {"judge_questions": ["¿hizo X?"]},
        },
    )

    r = await client.post(
        f"/admin/tenants/{tid}/eval-datasets/{ds['id']}/run",
        headers=admin_headers,
        json={},
    )
    assert r.status_code == 202, r.text
    body = await _await_run_terminal(client, tid, r.json()["id"], admin_headers)
    assert body["error_count"] == 1
    assert body["status"] == "error"
    kinds = {a["kind"] for a in body["results"][0]["assertion_results"]}
    assert "judge_unknown" in kinds


async def test_run_empty_dataset_400(
    client, admin_headers, seed_tenants, db_session, eval_router, fake_judge
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
    client, admin_headers, seed_tenants, db_session, eval_router, fake_judge
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
    triggered = await client.post(
        f"/admin/tenants/{tid}/eval-datasets/{ds['id']}/run",
        headers=admin_headers,
        json={},
    )
    assert triggered.status_code == 202
    await _await_run_terminal(client, tid, triggered.json()["id"], admin_headers)
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
    client, admin_headers, seed_tenants, db_session, eval_router, fake_judge
) -> None:
    """Tenant has ``eval_required=true`` but no eval_run for the candidate
    version → 409."""
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
    )
    assert r.status_code == 409
    assert "eval gate" in r.json()["detail"]


async def test_promote_allowed_with_passing_run(
    client, admin_headers, seed_tenants, db_session, eval_router, fake_judge
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
    assert run.status_code == 202, run.text
    final = await _await_run_terminal(client, tid, run.json()["id"], admin_headers)
    assert final["status"] == "passed"

    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/1/promote",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"


async def test_promote_override_with_reason(
    client, admin_headers, seed_tenants, db_session, eval_router, fake_judge
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
    client, admin_headers, seed_tenants, db_session, eval_router, fake_judge
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
