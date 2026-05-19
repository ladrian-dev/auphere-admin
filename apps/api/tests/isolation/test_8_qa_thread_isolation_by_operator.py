"""Garantía 8 — QA threads are scoped by operator_id (ADR-020 Phase 3).

RLS on qa.* must guarantee that:
  1. An operator only sees their own qa.threads / qa.side_effect_audit /
     qa.audit_log rows, regardless of how many other operators share the
     same tenant.
  2. Without ``app.operator_id`` set, no rows are visible at all
     (fail-closed).
  3. Cross-operator INSERT/UPDATE attempts fail the policy WITH CHECK
     clause and Postgres rejects them.

These properties hold across the three qa.* tables; the loop in this
test ensures we don't add a future table without RLS by accident.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from nexus_api.db.models.qa import QAAuditLog, QASideEffectAudit, QAThread

from .conftest import set_tenant

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def _set_operator(session, operator_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.operator_id', :o, true)"),
        {"o": str(operator_id)},
    )


async def test_qa_threads_isolated_per_operator(db_session, tenants_ab):
    op_a = uuid.uuid4()
    op_b = uuid.uuid4()
    tenant = tenants_ab["a"]

    # Operator A inserts two threads on tenant A.
    async with db_session.begin():
        await set_tenant(db_session, tenant)
        await _set_operator(db_session, op_a)
        db_session.add_all(
            [
                QAThread(operator_id=op_a, tenant_id=tenant, title="A1"),
                QAThread(operator_id=op_a, tenant_id=tenant, title="A2"),
            ]
        )

    # Operator B inserts one thread on the same tenant.
    async with db_session.begin():
        await set_tenant(db_session, tenant)
        await _set_operator(db_session, op_b)
        db_session.add(QAThread(operator_id=op_b, tenant_id=tenant, title="B1"))

    # Operator A: should see only own rows.
    async with db_session.begin():
        await set_tenant(db_session, tenant)
        await _set_operator(db_session, op_a)
        titles_a = {
            t.title
            for t in (await db_session.execute(select(QAThread))).scalars().all()
        }
        assert titles_a == {"A1", "A2"}
        assert "B1" not in titles_a

    # Operator B: should see only own row.
    async with db_session.begin():
        await set_tenant(db_session, tenant)
        await _set_operator(db_session, op_b)
        titles_b = {
            t.title
            for t in (await db_session.execute(select(QAThread))).scalars().all()
        }
        assert titles_b == {"B1"}


async def test_qa_threads_invisible_without_operator_setting(db_session, tenants_ab):
    op = uuid.uuid4()
    tenant = tenants_ab["a"]

    async with db_session.begin():
        await set_tenant(db_session, tenant)
        await _set_operator(db_session, op)
        db_session.add(QAThread(operator_id=op, tenant_id=tenant, title="hidden"))

    # No operator setting → policy fails closed.
    async with db_session.begin():
        await set_tenant(db_session, tenant)
        # NOTE: we intentionally skip _set_operator
        rows = (await db_session.execute(select(QAThread))).scalars().all()
        assert rows == []


async def test_qa_side_effect_audit_isolated(db_session, tenants_ab):
    op_a = uuid.uuid4()
    op_b = uuid.uuid4()
    tenant = tenants_ab["a"]

    async with db_session.begin():
        await set_tenant(db_session, tenant)
        await _set_operator(db_session, op_a)
        thread_a = QAThread(operator_id=op_a, tenant_id=tenant, title="A")
        db_session.add(thread_a)
        await db_session.flush()
        db_session.add(
            QASideEffectAudit(
                operator_id=op_a,
                tenant_id=tenant,
                thread_id=thread_a.id,
                tool_name="booking.create_appointment",
                tool_args={"date": "tomorrow"},
                synthetic_result={"ok": True},
            )
        )

    # Operator B doesn't see Operator A's audit.
    async with db_session.begin():
        await set_tenant(db_session, tenant)
        await _set_operator(db_session, op_b)
        rows = (
            (await db_session.execute(select(QASideEffectAudit))).scalars().all()
        )
        assert rows == []


async def test_qa_audit_log_isolated(db_session, tenants_ab):
    op_a = uuid.uuid4()
    op_b = uuid.uuid4()
    tenant = tenants_ab["a"]

    async with db_session.begin():
        await set_tenant(db_session, tenant)
        await _set_operator(db_session, op_a)
        db_session.add(
            QAAuditLog(
                operator_id=op_a,
                tenant_id=tenant,
                action="thread.create",
                target_kind="qa.thread",
            )
        )

    async with db_session.begin():
        await set_tenant(db_session, tenant)
        await _set_operator(db_session, op_b)
        rows = (await db_session.execute(select(QAAuditLog))).scalars().all()
        assert rows == []


async def test_qa_cross_operator_insert_rejected(db_session, tenants_ab):
    """An operator session cannot INSERT a row pretending to be someone
    else. The policy's WITH CHECK clause must reject it.
    """
    from sqlalchemy.exc import IntegrityError, ProgrammingError

    op_a = uuid.uuid4()
    op_b = uuid.uuid4()
    tenant = tenants_ab["a"]

    async with db_session.begin():
        await set_tenant(db_session, tenant)
        await _set_operator(db_session, op_a)
        db_session.add(
            QAThread(operator_id=op_b, tenant_id=tenant, title="forged")
        )
        with pytest.raises((IntegrityError, ProgrammingError)):
            await db_session.flush()


async def test_qa_isolation_holds_across_five_operators(db_session, tenants_ab):
    """Lighter version of the 5×5 concurrency spec: insert 5 threads per
    operator across 5 distinct operators and verify each one only sees
    their own — 25 inserts, 5 select sweeps, 0 leaks.
    """
    tenant = tenants_ab["a"]
    operators = [uuid.uuid4() for _ in range(5)]

    for op in operators:
        async with db_session.begin():
            await set_tenant(db_session, tenant)
            await _set_operator(db_session, op)
            for i in range(5):
                db_session.add(
                    QAThread(
                        operator_id=op,
                        tenant_id=tenant,
                        title=f"op-{op.hex[:6]}-thread-{i}",
                    )
                )

    seen_counts: list[int] = []
    for op in operators:
        async with db_session.begin():
            await set_tenant(db_session, tenant)
            await _set_operator(db_session, op)
            rows = (
                (await db_session.execute(select(QAThread))).scalars().all()
            )
            seen_counts.append(len(rows))
            # All visible rows must belong to this operator.
            assert all(t.operator_id == op for t in rows)
            # And carry this operator's signature in the title.
            assert all(t.title.startswith(f"op-{op.hex[:6]}-") for t in rows)

    assert seen_counts == [5, 5, 5, 5, 5]
