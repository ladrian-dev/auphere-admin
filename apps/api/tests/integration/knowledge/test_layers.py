"""Spec 047, T130 — el conocimiento en dos capas (historia 22; requisito 37).

- **Las dos capas**: la del negocio la ven todos los agentes; la propia, solo el
  suyo.
- **Garantía 9**: un agente no recupera, no cita y no recibe en su prompt lo propio
  de un hermano, ni entero ni por la búsqueda, ni en la memoria propia, ni desde la
  consola.
- **«Enseñar»** pide el alcance, se aplica al momento, queda en el historial, se
  deshace durante 10 minutos y vuelve a pasar las pruebas de quien lo ve.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.memory.postgres_memory_tool import NexusPostgresMemoryTool
from nexus_worker.runtime.console_context import load_knowledge_block, load_knowledge_for_turn
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import AuditLog, KnowledgeDocument, KnowledgeRevision
from nexus_api.db.models.agent_spec import AgentTestRun
from nexus_api.services.knowledge.retrieval import pick
from nexus_api.services.testing.suites import add_test, ensure_suite

from ..business._business_world import Biz, new_business
from ._knowledge_world import Kw, add_source, two_agents

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

SECRET = "El descuento mayorista es del 18 % a partir de 50 unidades."


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    return await new_business(client, db_session, console_world, name="Ferretería Lumen")


@pytest.fixture
async def kw(db_session: AsyncSession, biz: Biz) -> Kw:
    world = await two_agents(db_session, biz)
    await add_source(
        db_session, biz.tenant_id, title="Horario", text="Abrimos de lunes a sábado de 9 a 20."
    )
    await add_source(
        db_session,
        biz.tenant_id,
        title="Mayoristas",
        text=SECRET,
        agent_id=world.ventas,
    )
    await add_source(
        db_session,
        biz.tenant_id,
        title="Citas",
        text="Las citas de taller se piden con un día de antelación.",
        agent_id=world.recepcion,
    )
    return world


def _url(biz: Biz, agent_id: uuid.UUID) -> str:
    return f"/console/clients/{biz.ref}/agents/{agent_id}"


async def test_each_agent_sees_the_business_and_its_own_never_a_siblings(
    db_session: AsyncSession, kw: Kw
) -> None:
    tenant = kw.biz.tenant_id
    block, sources = await load_knowledge_for_turn(
        tenant, kw.recepcion, "¿Hay descuento mayorista?"
    )
    assert "Abrimos de lunes a sábado" in block and "citas de taller" in block
    assert SECRET not in block, "lo propio de Ventas no entra en el prompt de Recepción"
    assert {s["layer"] for s in sources} == {"business", "agent"}

    ventas, _ = await load_knowledge_for_turn(tenant, kw.ventas, "¿Hay descuento mayorista?")
    assert SECRET in ventas and "citas de taller" not in ventas

    # Por la búsqueda (no cabe): ni con la pregunta exacta sale lo de un hermano.
    async with tenant_scoped_session(db_session, tenant):
        searched = await pick(db_session, tenant, kw.recepcion, SECRET, budget=40)
    assert searched.mode == "search"
    assert all("mayorista" not in text for _, text in searched.docs)

    # El bloque de siempre (el Companion y lo de antes) es solo la capa del negocio.
    business_only = await load_knowledge_block(tenant)
    assert SECRET not in business_only and "citas de taller" not in business_only


async def test_own_memory_is_only_the_agents(db_session: AsyncSession, kw: Kw) -> None:
    from anthropic.types.beta import (
        BetaMemoryTool20250818CreateCommand,
        BetaMemoryTool20250818ViewCommand,
    )

    tenant = kw.biz.tenant_id
    ventas = NexusPostgresMemoryTool(tenant_id=tenant, customer_id=None, agent_id=kw.ventas)
    recepcion = NexusPostgresMemoryTool(tenant_id=tenant, customer_id=None, agent_id=kw.recepcion)
    shared = NexusPostgresMemoryTool(tenant_id=tenant, customer_id=None)
    created = await ventas.create(
        BetaMemoryTool20250818CreateCommand(
            command="create", path="/memories/precios.md", file_text="Tarifa B2B secreta"
        )
    )
    assert "created" in str(created)
    for other in (recepcion, shared):
        seen = await other.view(
            BetaMemoryTool20250818ViewCommand(command="view", path="/memories/precios.md")
        )
        assert "Tarifa B2B" not in str(seen), "la memoria propia no la ve nadie más"
    mine = await ventas.view(
        BetaMemoryTool20250818ViewCommand(command="view", path="/memories/precios.md")
    )
    assert "Tarifa B2B" in str(mine)
    # Recepción puede tener su propio archivo con el mismo nombre: no chocan.
    again = await recepcion.create(
        BetaMemoryTool20250818CreateCommand(
            command="create", path="/memories/precios.md", file_text="Precios de taller"
        )
    )
    assert "created" in str(again)


async def test_the_console_never_reaches_a_siblings_source(
    client: Any, db_session: AsyncSession, kw: Kw
) -> None:
    biz = kw.biz
    own = await client.get(f"{_url(biz, kw.recepcion)}/knowledge", headers=biz.headers())
    assert own.status_code == 200, own.text
    assert [d["title"] for d in own.json()["items"]] == ["Citas"]
    assert own.json()["business_sources"] == 1
    async with tenant_scoped_session(db_session, biz.tenant_id):
        secret_id = await db_session.scalar(
            sa.select(KnowledgeDocument.id).where(KnowledgeDocument.title == "Mayoristas")
        )
    await db_session.commit()
    sibling = await client.delete(
        f"{_url(biz, kw.recepcion)}/knowledge/{secret_id}", headers=biz.headers()
    )
    assert sibling.status_code == 404
    business = await client.get(f"/console/clients/{biz.ref}/knowledge", headers=biz.headers())
    assert [d["title"] for d in business.json()["items"]] == ["Horario"], (
        "Negocio enseña la capa del negocio"
    )


async def test_teach_asks_the_scope_applies_now_and_undoes(
    client: Any, db_session: AsyncSession, kw: Kw
) -> None:
    biz = kw.biz
    async with tenant_scoped_session(db_session, biz.tenant_id):
        for agent_id in (kw.recepcion, kw.ventas):
            suite = await ensure_suite(db_session, agent_id)
            await add_test(
                db_session,
                suite,
                {"name": "Horario", "first_message": "¿Abrís el domingo?", "criteria": []},
                kind="case",
                by="test",
            )
    await db_session.commit()

    no_scope = await client.post(
        f"{_url(biz, kw.ventas)}/teach", json={"text": "Algo"}, headers=biz.headers()
    )
    assert no_scope.status_code == 422, "«Enseñar» pide el alcance"

    taught = await client.post(
        f"{_url(biz, kw.ventas)}/teach",
        json={"text": "Los pedidos de más de 200 € van con envío gratis.", "scope": "agent"},
        headers=biz.headers(),
    )
    assert taught.status_code == 201, taught.text
    assert taught.json()["agent_id"] == str(kw.ventas) and taught.json()["kind"] == "note"
    block, _ = await load_knowledge_for_turn(biz.tenant_id, kw.ventas, "envío")
    assert "envío gratis" in block, "se aplica al momento"
    other, _ = await load_knowledge_for_turn(biz.tenant_id, kw.recepcion, "envío")
    assert "envío gratis" not in other

    async with tenant_scoped_session(db_session, biz.tenant_id):
        runs = (await db_session.scalars(sa.select(AgentTestRun.agent_id))).all()
        audit = await db_session.scalar(
            sa.select(AuditLog).where(AuditLog.action == "knowledge.taught")
        )
        rev = await db_session.scalar(
            sa.select(KnowledgeRevision.rev).where(KnowledgeRevision.agent_id == kw.ventas)
        )
    await db_session.commit()
    assert list(runs) == [kw.ventas], "vuelven a pasar las pruebas de quien lo ve, y solo esas"
    assert audit is not None and audit.after_json["scope"] == "agent"
    assert rev == 2, "la revisión de la capa sube"

    doc_id = taught.json()["id"]
    removed = await client.delete(
        f"{_url(biz, kw.ventas)}/knowledge/{doc_id}", headers=biz.headers()
    )
    assert removed.status_code == 204
    gone, _ = await load_knowledge_for_turn(biz.tenant_id, kw.ventas, "envío")
    assert "envío gratis" not in gone
    back = await client.post(
        f"{_url(biz, kw.ventas)}/knowledge/{doc_id}/restore", headers=biz.headers()
    )
    assert back.status_code == 200 and back.json()["removed_at"] is None

    await client.delete(f"{_url(biz, kw.ventas)}/knowledge/{doc_id}", headers=biz.headers())
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(
            sa.update(KnowledgeDocument)
            .where(KnowledgeDocument.id == uuid.UUID(doc_id))
            .values(restore_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    await db_session.commit()
    late = await client.post(
        f"{_url(biz, kw.ventas)}/knowledge/{doc_id}/restore", headers=biz.headers()
    )
    assert late.status_code == 409 and late.json()["detail"]["code"] == "undo_window_closed"

    business = await client.post(
        f"{_url(biz, kw.ventas)}/teach",
        json={"text": "Cerramos el 15 de agosto.", "scope": "business"},
        headers=biz.headers(),
    )
    assert business.json()["agent_id"] is None
    seen_by_both = [
        "15 de agosto" in (await load_knowledge_for_turn(biz.tenant_id, a, "agosto"))[0]
        for a in (kw.recepcion, kw.ventas)
    ]
    assert seen_by_both == [True, True]
