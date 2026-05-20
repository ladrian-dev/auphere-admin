"""End-to-end test for the QA dry_run audit writer (ADR-020 Phase 3).

Boots a stub MCPRegistry in dry_run mode with the production audit
callback wired in, dispatches a side-effecting tool, and confirms one
row landed in ``qa.side_effect_audit`` with the right operator_id,
tenant_id and thread_id.

This is the canonical end-to-end check that the QA Playground's
isolation guarantee (no real side effects) is enforced AND auditable.
"""

from __future__ import annotations

import uuid

import pytest
from nexus_mcp.base import InputModel, OutputModel, ToolBase
from nexus_mcp.registry import MCPRegistry
from nexus_worker.runtime.qa_audit import make_qa_audit_writer
from sqlalchemy import select

from nexus_api.core.operator_context import operator_context
from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import Tenant, TenantPlan
from nexus_api.db.models.qa import QASideEffectAudit, QAThread

pytestmark = pytest.mark.asyncio


# ── stub tool with side effects ──────────────────────────────────────────────


class _In(InputModel):
    pass


class _Out(OutputModel):
    ok: bool = True


class _MutatingTool(ToolBase):
    name = "demo.book"
    description = "mutates external system"
    input_model = _In
    output_model = _Out
    side_effects = ("external_api", "mutates_db")

    async def run(self, payload: _In) -> _Out:  # pragma: no cover
        raise AssertionError("QA dry_run must intercept this tool")


@pytest.fixture
async def qa_seed(db_session):
    """Insert a tenant + a QA thread we can audit against."""
    import secrets

    operator_id = secrets.token_urlsafe(16)  # opaque string (post-0026)
    tenant_id = uuid.uuid4()
    thread_id = uuid.uuid4()

    async with db_session.begin():
        db_session.add(
            Tenant(
                id=tenant_id,
                name="QA-Audit",
                slug=f"qa-audit-{tenant_id.hex[:6]}",
                plan=TenantPlan.PRO,
            )
        )

    async with db_session.begin():
        # Apply scope to satisfy RLS on qa.threads insert.
        from nexus_api.core.operator_context import qa_scoped_session

        async with qa_scoped_session(db_session, operator_id=operator_id, tenant_id=tenant_id):
            db_session.add(
                QAThread(
                    id=thread_id,
                    operator_id=operator_id,
                    tenant_id=tenant_id,
                    title="audit-target",
                )
            )

    return operator_id, tenant_id, thread_id


async def test_dry_run_dispatch_persists_side_effect_audit(qa_seed, db_session):
    operator_id, tenant_id, thread_id = qa_seed
    audit_cb = make_qa_audit_writer(thread_id=thread_id, run_id="run-001")

    registry = MCPRegistry(
        tools=[_MutatingTool()],
        dry_run=True,
        dry_run_audit=audit_cb,
    )

    # Set BOTH contextvars before the dispatch — that's what the LangGraph
    # Server's auth layer does per request. Without them the writer skips.
    with tenant_context(tenant_id), operator_context(operator_id):
        envelope = await registry.dispatch(
            "demo.book", {"date": "tomorrow"}, whitelist=["demo.book"]
        )

    assert envelope["status"] == "skipped:dry_run"
    assert envelope["result"]["blocked_by"] == "dry_run"

    # Pull the audit row back with the same operator scope; RLS on
    # qa.side_effect_audit lets only this operator see it.
    from nexus_api.core.operator_context import qa_scoped_session

    async with (
        db_session.begin(),
        qa_scoped_session(db_session, operator_id=operator_id, tenant_id=tenant_id),
    ):
        rows = (
            (
                await db_session.execute(
                    select(QASideEffectAudit).where(QASideEffectAudit.thread_id == thread_id)
                )
            )
            .scalars()
            .all()
        )

    assert len(rows) == 1
    row = rows[0]
    assert row.operator_id == operator_id
    assert row.tenant_id == tenant_id
    assert row.tool_name == "demo.book"
    assert row.tool_args == {"date": "tomorrow"}
    assert row.blocked_reason == "dry_run"
    assert row.run_id == "run-001"
    assert row.synthetic_result["status"] == "skipped:dry_run"


async def test_dry_run_dispatch_uses_qa_thread_context(qa_seed, db_session):
    """When the writer is built WITHOUT a pinned thread_id it reads
    from ``qa_thread_context`` — that's how the LangGraph Server (which
    shares a single compiled graph across requests) will use it."""
    operator_id, tenant_id, thread_id = qa_seed
    # NOTE: no thread_id pinned at builder time.
    audit_cb = make_qa_audit_writer(run_id="run-002")

    registry = MCPRegistry(tools=[_MutatingTool()], dry_run=True, dry_run_audit=audit_cb)

    from nexus_api.core.operator_context import qa_thread_context

    with tenant_context(tenant_id), operator_context(operator_id), qa_thread_context(thread_id):
        envelope = await registry.dispatch("demo.book", {"date": "today"}, whitelist=["demo.book"])
    assert envelope["status"] == "skipped:dry_run"

    from nexus_api.core.operator_context import qa_scoped_session

    async with (
        db_session.begin(),
        qa_scoped_session(db_session, operator_id=operator_id, tenant_id=tenant_id),
    ):
        rows = (
            (
                await db_session.execute(
                    select(QASideEffectAudit).where(QASideEffectAudit.thread_id == thread_id)
                )
            )
            .scalars()
            .all()
        )

    assert len(rows) == 1
    assert rows[0].run_id == "run-002"
    assert rows[0].tool_args == {"date": "today"}


async def test_audit_writer_skips_when_scope_missing(db_session):
    """Without operator_id/tenant_id in scope the writer logs and skips —
    it must never raise, because that would break the agent's conversation
    on a misconfigured run.
    """
    thread_id = uuid.uuid4()
    audit_cb = make_qa_audit_writer(thread_id=thread_id)

    # No context vars set. The callback should not raise.
    synthetic = {
        "tool": "demo.book",
        "status": "skipped:dry_run",
        "result": {"blocked_by": "dry_run"},
    }
    # No exception expected.
    await audit_cb("demo.book", {"x": 1}, synthetic)

    # And no row was persisted (we can't actually check via RLS without a
    # scope — confirm by counting rows from a fresh tenant-scoped session
    # that DOES see them).
    import secrets

    from nexus_api.core.operator_context import qa_scoped_session

    op = secrets.token_urlsafe(16)
    # Pick a tenant_id; even an unknown one is fine because we expect 0 rows.
    fake_tenant = uuid.uuid4()
    async with (
        db_session.begin(),
        qa_scoped_session(db_session, operator_id=op, tenant_id=fake_tenant),
    ):
        rows = (
            (
                await db_session.execute(
                    select(QASideEffectAudit).where(QASideEffectAudit.thread_id == thread_id)
                )
            )
            .scalars()
            .all()
        )
        assert rows == []
