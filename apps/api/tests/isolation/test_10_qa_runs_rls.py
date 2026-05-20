"""Garantía 10 — qa.runs is scoped by operator_id (ADR-021 Fase 1).

The new ``qa.runs`` table tracks streaming agent turns. RLS by
``operator_id`` must hold for the same reason ``qa.threads`` does: an
operator must never see another operator's run lifecycle, even on the
same tenant.

This file complements ``test_8_qa_thread_isolation_by_operator.py`` (the
``qa.threads`` / ``qa.side_effect_audit`` / ``qa.audit_log`` coverage)
and ``test_9_qa_concurrent_isolation.py`` (concurrent HTTP traffic).
"""

from __future__ import annotations

import secrets
import uuid

import pytest
from sqlalchemy import select, text

from nexus_api.db.models.qa import (
    QA_RUN_STATUS_COMPLETED,
    QA_RUN_STATUS_RUNNING,
    QARun,
    QAThread,
)

from .conftest import set_tenant

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


def _op_id() -> str:
    return secrets.token_urlsafe(16)


async def _set_operator(session, operator_id: str) -> None:
    await session.execute(
        text("SELECT set_config('app.operator_id', :o, true)"),
        {"o": operator_id},
    )


async def test_qa_runs_isolated_per_operator(db_session, tenants_ab):
    op_a = _op_id()
    op_b = _op_id()
    tenant = tenants_ab["a"]

    # Op A creates a thread + two runs.
    async with db_session.begin():
        await set_tenant(db_session, tenant)
        await _set_operator(db_session, op_a)
        thread_a = QAThread(operator_id=op_a, tenant_id=tenant, title="A1")
        db_session.add(thread_a)
        await db_session.flush()
        db_session.add_all(
            [
                QARun(
                    thread_id=thread_a.id,
                    operator_id=op_a,
                    status=QA_RUN_STATUS_RUNNING,
                ),
                QARun(
                    thread_id=thread_a.id,
                    operator_id=op_a,
                    status=QA_RUN_STATUS_COMPLETED,
                ),
            ]
        )

    # Op B sees zero rows under their scope.
    async with db_session.begin():
        await set_tenant(db_session, tenant)
        await _set_operator(db_session, op_b)
        rows = (await db_session.execute(select(QARun))).scalars().all()
        assert rows == []

    # Op A sees exactly the two it inserted.
    async with db_session.begin():
        await set_tenant(db_session, tenant)
        await _set_operator(db_session, op_a)
        rows = (await db_session.execute(select(QARun))).scalars().all()
        assert len(rows) == 2
        assert all(r.operator_id == op_a for r in rows)


async def test_qa_runs_fail_closed_without_operator_scope(db_session, tenants_ab):
    """No ``app.operator_id`` set → no rows visible. Defends against a
    missing scope helper somewhere in the call chain."""
    op_a = _op_id()
    tenant = tenants_ab["a"]

    async with db_session.begin():
        await set_tenant(db_session, tenant)
        await _set_operator(db_session, op_a)
        thread_a = QAThread(operator_id=op_a, tenant_id=tenant, title="A1")
        db_session.add(thread_a)
        await db_session.flush()
        db_session.add(
            QARun(
                thread_id=thread_a.id,
                operator_id=op_a,
                status=QA_RUN_STATUS_RUNNING,
            )
        )

    # No operator scope.
    async with db_session.begin():
        await set_tenant(db_session, tenant)
        await db_session.execute(text("SELECT set_config('app.operator_id', '', true)"))
        rows = (await db_session.execute(select(QARun))).scalars().all()
        assert rows == []


async def test_cross_operator_insert_blocked_by_with_check(db_session, tenants_ab):
    """Forging ``operator_id`` to look like another operator must fail
    the policy's WITH CHECK clause at the DB layer. This is the last
    line of defence — the handler stamps operator_id from the verified
    header, so this path is unreachable from the API. We test the DB
    direction to keep that promise enforced at the storage layer."""
    op_a = _op_id()
    op_b = _op_id()
    tenant = tenants_ab["a"]

    # Create a thread owned by op_a (with normal scope).
    async with db_session.begin():
        await set_tenant(db_session, tenant)
        await _set_operator(db_session, op_a)
        thread_a = QAThread(operator_id=op_a, tenant_id=tenant, title="A1")
        db_session.add(thread_a)
        await db_session.flush()
        thread_a_id = thread_a.id

    # Try to insert a run with operator_id=op_b while the GUC says op_a.
    # The WITH CHECK clause should reject — the row's operator_id does not
    # match the session's app.operator_id.
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):
        async with db_session.begin():
            await set_tenant(db_session, tenant)
            await _set_operator(db_session, op_a)
            db_session.add(
                QARun(
                    id=uuid.uuid4(),
                    thread_id=thread_a_id,
                    operator_id=op_b,  # FORGED
                    status=QA_RUN_STATUS_RUNNING,
                )
            )
            await db_session.flush()
