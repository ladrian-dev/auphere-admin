"""Requisito 13 — ocho actos nuevos en el vocabulario, y la persona como actor.

Se lee de la base (migración 0112), no de una constante: lo que importa es lo
que la auditoría puede escribir de verdad.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio

EXPECTED = {
    "teammate.created",
    "teammate.updated",
    "teammate.archived",
    "local_policy.ceiling_changed",
    "local_policy.pref_changed",
    "local_exec.allowed_once",
    "local_exec.allowed_by_policy",
    "local_exec.denied_by_policy",
}


async def test_the_eight_actions_exist_and_the_actor_is_always_the_person(db_session):
    rows = (
        await db_session.execute(
            text(
                "SELECT action, category, summary_es, summary_en FROM console_audit_vocabulary "
                "WHERE action LIKE 'teammate.%' OR action LIKE 'local_policy.%' OR action LIKE 'local_exec.%'"
            )
        )
    ).all()
    actions = {r.action for r in rows}
    assert actions >= EXPECTED
    for r in rows:
        if r.action in EXPECTED:
            assert r.summary_es.startswith("{actor}"), r.action
            assert r.summary_en.startswith("{actor}"), r.action
            assert "{teammate}" not in r.summary_es.split(" ")[0]
            assert r.category == "teammates"
