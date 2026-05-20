"""QA Playground counters (ADR-020 Fase 6, Bloque E).

The hardening pass introduces 4 named counters that alerts hook into:

  - ``qa.thread.created``     bumped by ``POST /qa/threads``
  - ``qa.side_effect.blocked`` bumped by the dry-run audit callback
  - ``qa.audit.write_failed``  bumped when persistence fails
  - ``qa.run.duration_ms.{sum,count}`` reserved for the runtime
    (Phase 5 cierre) — not asserted here.

This test exercises the first 3 end-to-end. The histograms wait for the
runtime live wiring; documented as TODO in ``docs/qa-playground/alerts.md``.
"""

from __future__ import annotations

import uuid

import pytest

from nexus_api.core.metrics import (
    QA_AUDIT_WRITE_FAILED,
    QA_SIDE_EFFECT_BLOCKED,
    QA_THREAD_CREATED,
    counters,
)
from nexus_api.core.operator_context import operator_context
from nexus_api.core.tenant_context import tenant_context
from nexus_mcp.base import InputModel, OutputModel, ToolBase
from nexus_mcp.registry import MCPRegistry
from nexus_worker.runtime.qa_audit import make_qa_audit_writer

pytestmark = pytest.mark.asyncio


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_counters():
    """Each test starts from a clean slate. We can't isolate the global
    ``Counters`` instance per test without rewiring; calling ``reset``
    is the cheapest correct option.
    """
    counters.reset()
    yield
    counters.reset()


@pytest.fixture
async def tenant_id(db_session) -> uuid.UUID:
    from nexus_api.db.models import Tenant, TenantPlan

    tid = uuid.uuid4()
    async with db_session.begin():
        db_session.add(
            Tenant(
                id=tid,
                name="QA-M",
                slug=f"qa-m-{tid.hex[:8]}",
                plan=TenantPlan.PRO,
            )
        )
    return tid


# ── tests ───────────────────────────────────────────────────────────────────


async def test_qa_thread_created_counter_bumps_per_post(
    client, admin_headers, tenant_id
):
    import secrets

    op = secrets.token_urlsafe(16)
    h = {**admin_headers, "X-Operator-Id": op}

    assert counters.get(QA_THREAD_CREATED) == 0

    for _ in range(3):
        r = await client.post(
            "/qa/threads",
            json={"tenant_id": str(tenant_id), "title": "metric"},
            headers=h,
        )
        assert r.status_code == 201

    assert counters.get(QA_THREAD_CREATED) == 3
    # Per-tenant + per-operator label rollups (used by alert routers).
    assert counters.get(f"{QA_THREAD_CREATED}:tenant={tenant_id}") == 3
    assert counters.get(f"{QA_THREAD_CREATED}:operator={op}") == 3


class _NoSideEffectsIn(InputModel):
    pass


class _NoSideEffectsOut(OutputModel):
    ok: bool = True


class _WriteIn(InputModel):
    pass


class _WriteOut(OutputModel):
    ok: bool = True


class _MutatingTool(ToolBase):
    name = "qa_metrics.write"
    description = "side-effecting stub for metrics test"
    input_model = _WriteIn
    output_model = _WriteOut
    side_effects = ("mutates_db",)

    async def run(self, payload: _WriteIn) -> _WriteOut:  # pragma: no cover
        raise AssertionError("dry_run must not invoke this")


async def test_qa_side_effect_blocked_counter_bumps_per_intercept(tenant_id, db_session):
    """Two consecutive dispatches of a side-effecting tool under dry_run
    must bump the counter by 2 (global + per-tool label).
    """
    from nexus_api.db.models.qa import QAThread
    from nexus_api.core.operator_context import (
        qa_scoped_session,
        qa_thread_context,
    )

    import secrets

    operator_id = secrets.token_urlsafe(16)
    thread_id = uuid.uuid4()
    async with db_session.begin():
        async with qa_scoped_session(
            db_session, operator_id=operator_id, tenant_id=tenant_id
        ):
            db_session.add(
                QAThread(
                    id=thread_id,
                    operator_id=operator_id,
                    tenant_id=tenant_id,
                    title="metrics-target",
                )
            )

    audit_cb = make_qa_audit_writer(thread_id=thread_id, run_id="run-m")
    reg = MCPRegistry(
        tools=[_MutatingTool()], dry_run=True, dry_run_audit=audit_cb
    )

    assert counters.get(QA_SIDE_EFFECT_BLOCKED) == 0
    with tenant_context(tenant_id), operator_context(operator_id), qa_thread_context(
        thread_id
    ):
        for _ in range(2):
            r = await reg.dispatch(
                "qa_metrics.write", {}, whitelist=["qa_metrics.write"]
            )
            assert r["status"] == "skipped:dry_run"

    assert counters.get(QA_SIDE_EFFECT_BLOCKED) == 2
    assert counters.get(f"{QA_SIDE_EFFECT_BLOCKED}:tool=qa_metrics.write") == 2


async def test_qa_audit_write_failed_counter_bumps_on_persist_error(monkeypatch):
    """If the audit persistence path raises (e.g. DB down, RLS denied),
    the counter must bump and the dispatch must still return the
    synthetic envelope — that contract is enforced by other tests; here
    we only assert the counter side.
    """
    import nexus_worker.runtime.qa_audit as qa_audit_mod

    async def _boom(*args, **kwargs):
        raise RuntimeError("synthesised qa.side_effect_audit insert failure")

    # Force the inner session-open path to explode. Monkeypatching
    # ``get_sessionmaker`` is the smallest scoped change.
    monkeypatch.setattr(qa_audit_mod, "get_sessionmaker", lambda: _BoomSM())

    audit_cb = make_qa_audit_writer(thread_id=uuid.uuid4(), run_id="run-m")
    # Provide scope so the writer reaches the persistence step.
    import secrets

    with tenant_context(uuid.uuid4()), operator_context(secrets.token_urlsafe(16)):
        await audit_cb(
            "qa_metrics.write",
            {},
            {"tool": "qa_metrics.write", "status": "skipped:dry_run", "result": {}},
        )

    assert counters.get(QA_AUDIT_WRITE_FAILED) == 1
    assert counters.get(f"{QA_AUDIT_WRITE_FAILED}:tool=qa_metrics.write") == 1


class _BoomSM:
    """Tiny shim so the writer hits the failure path inside the
    ``async with`` opener instead of failing at ``get_sessionmaker()``
    (which it catches at a different layer).
    """

    def __call__(self):
        return _BoomSession()


class _BoomSession:
    async def __aenter__(self):
        raise RuntimeError("session refused to open")

    async def __aexit__(self, *_a):
        return False
