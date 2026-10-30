"""La suite de pruebas de cada agente — spec 047, T086 (requisito 21; research D18).

Cada agente tiene una suite con tres tipos de prueba:

- **del caso** (``case``): las genera el constructor desde la descripción, 8 por
  defecto;
- **del sector** (``sector``): las 12 de la batería común de su nicho
  (``sector_test_catalog``), cada una con ``sector@versión#clave``;
- **añadidas** (``person``, ``conversation``, ``correction``): por personas, o
  desde conversaciones y correcciones.

Cambiar el borrador, la ficha o el conocimiento marca las afectadas como
desactualizadas (``stale``, requisito 21.7); una prueba del sector puede marcarse
«No aplica» con su razón (21.6) y entonces no cuenta para la puerta.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models.agent_spec import AgentTest, AgentTestSuite

#: Las secciones de la ficha que afectan a cada prueba por defecto (21.7). Una
#: prueba sin ``expected_state`` que las nombre queda afectada por cualquiera.
SECTION_TOUCHES: Final[dict[str, frozenset[str]]] = {
    "hours": frozenset({"hours", "answered_from", "booking"}),
    "special_dates": frozenset({"hours", "answered_from", "booking"}),
    "services": frozenset({"booking", "price", "services"}),
    "locations": frozenset({"address", "locations"}),
    "policies": frozenset({"policy", "booking"}),
    "faqs": frozenset({"faq"}),
}


async def get_suite(session: AsyncSession, agent_id: uuid.UUID) -> AgentTestSuite | None:
    return (
        await session.scalars(
            sa.select(AgentTestSuite).where(
                AgentTestSuite.tenant_id == require_current_tenant(),
                AgentTestSuite.agent_id == agent_id,
            )
        )
    ).first()


async def ensure_suite(session: AsyncSession, agent_id: uuid.UUID) -> AgentTestSuite:
    suite = await get_suite(session, agent_id)
    if suite is None:
        suite = AgentTestSuite(
            id=uuid.uuid4(), tenant_id=require_current_tenant(), agent_id=agent_id, revision=1
        )
        session.add(suite)
        await session.flush()
    return suite


async def list_tests(
    session: AsyncSession, suite: AgentTestSuite, *, archived: bool = False
) -> list[AgentTest]:
    stmt = sa.select(AgentTest).where(
        AgentTest.tenant_id == suite.tenant_id, AgentTest.suite_id == suite.id
    )
    if not archived:
        stmt = stmt.where(AgentTest.archived_at.is_(None))
    order = sa.case({"case": 0, "sector": 1}, value=AgentTest.kind, else_=2)
    return list(
        (await session.scalars(stmt.order_by(order, AgentTest.created_at, AgentTest.name))).all()
    )


def _test_row(suite: AgentTestSuite, item: Mapping[str, Any], *, kind: str, by: str) -> AgentTest:
    return AgentTest(
        id=uuid.uuid4(),
        tenant_id=suite.tenant_id,
        suite_id=suite.id,
        kind=kind,
        name=str(item["name"])[:120],
        persona=str(item.get("persona") or ""),
        first_message=str(item["first_message"])[:2000],
        plan=str(item.get("plan") or ""),
        expected_state=dict(item.get("expected_state") or {}),
        criteria=list(item.get("criteria") or []),
        critical=bool(item.get("critical", False)),
        sector_test_ref=item.get("sector_test_ref"),
        # Spec 047, enmienda (58.4): salió de la guía generada para este cliente.
        generated_guide_id=item.get("generated_guide_id"),
        # Spec 047, enmienda del 2026-10-30 (65.8): lo marca el sistema al añadirla.
        not_applicable_reason=item.get("not_applicable_reason") or None,
        created_by_kind=by,
    )


async def replace_case_tests(
    session: AsyncSession, suite: AgentTestSuite, tests: Sequence[Mapping[str, Any]]
) -> list[AgentTest]:
    """Las pruebas del caso de un borrador nuevo sustituyen a las anteriores del
    caso (se archivan, no se borran)."""
    now = datetime.now(UTC)
    await session.execute(
        sa.update(AgentTest)
        .where(
            AgentTest.tenant_id == suite.tenant_id,
            AgentTest.suite_id == suite.id,
            AgentTest.kind == "case",
            AgentTest.archived_at.is_(None),
        )
        .values(archived_at=now)
    )
    rows = [_test_row(suite, item, kind="case", by="builder") for item in tests]
    session.add_all(rows)
    await bump(session, suite)
    await session.flush()
    return rows


async def add_test(
    session: AsyncSession,
    suite: AgentTestSuite,
    item: Mapping[str, Any],
    *,
    kind: str = "person",
    by: str = "partner_member",
) -> AgentTest:
    row = _test_row(suite, item, kind=kind, by=by)
    session.add(row)
    await bump(session, suite)
    await session.flush()
    return row


async def bump(session: AsyncSession, suite: AgentTestSuite) -> None:
    suite.revision = (suite.revision or 0) + 1
    suite.updated_at = datetime.now(UTC)


async def mark_stale(
    session: AsyncSession,
    agent_id: uuid.UUID,
    *,
    sections: Sequence[str] | None = None,
) -> int:
    """Marca como desactualizadas las pruebas afectadas (21.7). Sin secciones
    (cambió el borrador o el conocimiento), todas las vivas del agente."""
    suite = await get_suite(session, agent_id)
    if suite is None:
        return 0
    tests = await list_tests(session, suite)
    touched = 0
    keys: frozenset[str] | None = None
    if sections:
        keys = frozenset().union(*(SECTION_TOUCHES.get(s, frozenset({s})) for s in sections))
    for test in tests:
        if test.stale:
            continue
        state_keys = set((test.expected_state or {}).keys())
        crit_keys = {str(c.get("key")) for c in test.criteria or [] if isinstance(c, Mapping)}
        if keys is None or not state_keys | crit_keys or (state_keys | crit_keys) & keys:
            test.stale = True
            touched += 1
    if touched:
        await session.flush()
    return touched


async def mark_client_stale(session: AsyncSession, *, sections: Sequence[str]) -> int:
    """Una escritura de la ficha marca las pruebas afectadas de **todos** los
    agentes del cliente (la ficha es de todos)."""
    from nexus_api.db.models import Agent

    total = 0
    for agent_id in (
        await session.scalars(
            sa.select(Agent.id).where(Agent.tenant_id == require_current_tenant())
        )
    ).all():
        total += await mark_stale(session, agent_id, sections=sections)
    return total


__all__ = [
    "SECTION_TOUCHES",
    "add_test",
    "bump",
    "ensure_suite",
    "get_suite",
    "list_tests",
    "mark_client_stale",
    "mark_stale",
    "replace_case_tests",
]
