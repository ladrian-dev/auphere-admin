"""Garantía 9 sobre el conocimiento y la memoria — spec 047, T130 (requisitos
37.2, 37.4 y 37.5).

Adversarial: Ventas tiene un dato propio y una memoria propia; Recepción, del
mismo cliente, intenta llegar a ellos por todas las vías que tiene el turno:

- el bloque entero (cuando cabe);
- la búsqueda híbrida, por palabras y por vector, con la pregunta exacta y el
  vector exacto del dato;
- la memoria propia (ver, crear en la misma ruta);
- la consola, con el id del documento de su hermano.

Lo declaran ``AGENT_TABLES`` de ``test_44_agent_within_client.py``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.memory.postgres_memory_tool import NexusPostgresMemoryTool
from nexus_worker.runtime.console_context import load_knowledge_for_turn
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import KnowledgeDocument
from nexus_api.services.knowledge import embeddings
from nexus_api.services.knowledge.retrieval import pick, search
from tests.integration.business._business_world import Biz, new_business
from tests.integration.knowledge._knowledge_world import (
    Kw,
    add_source,
    fake_embedder,
    two_agents,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

SECRET = "MAYORISTA El descuento mayorista es del 18 % a partir de 50 unidades."


@pytest.fixture
async def kw(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Kw:
    embeddings.set_embedder(fake_embedder)
    biz: Biz = await new_business(client, db_session, console_world, name="Ferretería Lumen")
    world = await two_agents(db_session, biz)
    await add_source(db_session, biz.tenant_id, title="Horario", text="HORARIO Abrimos a las 9.")
    await add_source(
        db_session, biz.tenant_id, title="Mayoristas", text=SECRET, agent_id=world.ventas
    )
    yield world
    embeddings.reset_embedder()


async def test_a_siblings_knowledge_never_reaches_the_prompt_nor_the_search(
    db_session: AsyncSession, kw: Kw
) -> None:
    tenant = kw.biz.tenant_id
    block, sources = await load_knowledge_for_turn(tenant, kw.recepcion, SECRET)
    assert "mayorista" not in block.lower()
    async with tenant_scoped_session(db_session, tenant):
        secret_id = await db_session.scalar(
            sa.select(KnowledgeDocument.id).where(KnowledgeDocument.title == "Mayoristas")
        )
        assert str(secret_id) not in {s["ref"] for s in sources}
        # La pregunta exacta y el vector exacto del dato: ni por palabras ni por
        # semántica sale de la capa de Ventas.
        hits = await search(db_session, tenant, kw.recepcion, SECRET)
        forced = await pick(db_session, tenant, kw.recepcion, SECRET, budget=10)
        own = await search(db_session, tenant, kw.ventas, SECRET)
    await db_session.commit()
    assert all(h["document_id"] != secret_id for h in hits)
    assert all("mayorista" not in t.lower() for _, t in forced.docs)
    assert own and own[0]["document_id"] == secret_id, "Ventas sí lo encuentra: la prueba muerde"


async def test_own_memory_is_never_a_siblings(kw: Kw) -> None:
    from anthropic.types.beta import (
        BetaMemoryTool20250818CreateCommand,
        BetaMemoryTool20250818ViewCommand,
    )

    tenant = kw.biz.tenant_id
    ventas = NexusPostgresMemoryTool(tenant_id=tenant, customer_id=None, agent_id=kw.ventas)
    recepcion = NexusPostgresMemoryTool(tenant_id=tenant, customer_id=None, agent_id=kw.recepcion)
    await ventas.create(
        BetaMemoryTool20250818CreateCommand(
            command="create", path="/memories/clientes.md", file_text="Lista VIP de Ventas"
        )
    )
    file = await recepcion.view(
        BetaMemoryTool20250818ViewCommand(command="view", path="/memories/clientes.md")
    )
    assert "VIP" not in str(file) and "does not exist" in str(file)
    listing = await recepcion.view(
        BetaMemoryTool20250818ViewCommand(command="view", path="/memories")
    )
    assert "clientes.md" not in str(listing), "ni siquiera ve que existe"
    mine = await ventas.view(
        BetaMemoryTool20250818ViewCommand(command="view", path="/memories/clientes.md")
    )
    assert "VIP" in str(mine), "Ventas sí la ve: la prueba muerde"


async def test_the_console_never_hands_a_siblings_source(
    client: Any, db_session: AsyncSession, kw: Kw
) -> None:
    biz = kw.biz
    async with tenant_scoped_session(db_session, biz.tenant_id):
        secret_id = await db_session.scalar(
            sa.select(KnowledgeDocument.id).where(KnowledgeDocument.title == "Mayoristas")
        )
    await db_session.commit()
    base = f"/console/clients/{biz.ref}/agents/{kw.recepcion}/knowledge"
    listed = await client.get(base, headers=biz.headers())
    assert str(secret_id) not in listed.text
    for method, path in (
        ("DELETE", f"{base}/{secret_id}"),
        ("POST", f"{base}/{secret_id}/restore"),
    ):
        resp = await client.request(method, path, headers=biz.headers())
        assert resp.status_code == 404, f"{method} {path}"
    unknown = await client.delete(f"{base}/{uuid.uuid4()}", headers=biz.headers())
    assert unknown.status_code == 404, "el de un hermano y uno que no existe dicen lo mismo"
