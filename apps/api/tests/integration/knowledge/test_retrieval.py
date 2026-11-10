"""Spec 047, T131 — recuperar el conocimiento (historia 22; requisito 38).

- **Si cabe** en el presupuesto, va entero.
- **Si no**, la búsqueda híbrida, por palabras (``spanish``) y semántica (pgvector),
  fusionada por rangos y **filtrada por cliente y capa dentro de la consulta**; sin
  índice ANN: exacta sobre las filas del cliente.
- **Las fuentes** de cada respuesta quedan en ``turn_sources``.
- **Rendimiento**: menos de 30 ms p95 con 5.000 fragmentos.
"""

from __future__ import annotations

import random
import statistics
import time
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.pipeline import make_checkpoint_node
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    Conversation,
    ConversationStatus,
    Customer,
    KnowledgeChunk,
    KnowledgeChunkVector,
    TurnSource,
)
from nexus_api.services.knowledge import embeddings
from nexus_api.services.knowledge.embeddings import as_literal
from nexus_api.services.knowledge.retrieval import pick, search, search_sql

from ..business._business_world import Biz, new_business
from ._knowledge_world import Kw, add_source, fake_embedder, two_agents, vector_of

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    return await new_business(client, db_session, console_world, name="Ferretería Lumen")


@pytest.fixture
async def kw(db_session: AsyncSession, biz: Biz) -> Kw:
    return await two_agents(db_session, biz)


@pytest.fixture
def embedder() -> Any:
    embeddings.set_embedder(fake_embedder)
    yield
    embeddings.reset_embedder()


@pytest.fixture
def no_embedder() -> Any:
    embeddings.set_embedder(None)
    yield
    embeddings.reset_embedder()


TOPICS = {
    "GARANTIA": "Los taladros tienen dos años de garantía con el ticket de compra.",
    "DEVOLUCIONES": "Las devoluciones se aceptan en 30 días si el producto está sin usar.",
    "ENVIOS": "Los envíos a península tardan de 24 a 48 horas laborables.",
    "PINTURA": "La pintura plástica se mezcla en tienda en el momento, en cualquier color.",
}
#: Un tema por fragmento: cada párrafo ronda los 800 caracteres y dos no caben
#: en uno (1.200).
MANUAL = "\n\n".join(f"{key} " + " ".join([text] * 11) for key, text in TOPICS.items())


async def test_what_fits_goes_whole(db_session: AsyncSession, kw: Kw, no_embedder: Any) -> None:
    await add_source(db_session, kw.biz.tenant_id, title="Horario", text="Abrimos a las 9.")
    async with tenant_scoped_session(db_session, kw.biz.tenant_id):
        chosen = await pick(db_session, kw.biz.tenant_id, kw.recepcion, "¿a qué hora abrís?")
    assert chosen.mode == "full"
    assert chosen.docs == [("Horario", "Abrimos a las 9.")]


async def test_what_does_not_fit_is_searched_by_words(
    db_session: AsyncSession, kw: Kw, no_embedder: Any
) -> None:
    tenant = kw.biz.tenant_id
    await add_source(db_session, tenant, title="Manual", text=MANUAL)
    async with tenant_scoped_session(db_session, tenant):
        chosen = await pick(
            db_session,
            tenant,
            kw.recepcion,
            "¿Cuántos días tengo para una devolución?",
            budget=1_000,
        )
    assert chosen.mode == "search"
    assert [t.split()[0] for _, t in chosen.docs] == ["DEVOLUCIONES"], (
        "solo lo que cabe y lo más relevante"
    )
    assert sum(len(t) for _, t in chosen.docs) <= 1_000
    assert chosen.sources[0]["kind"] == "knowledge" and "chunk" in chosen.sources[0]


async def test_semantic_search_finds_by_meaning_and_fuses_ranks(
    db_session: AsyncSession, kw: Kw, embedder: Any
) -> None:
    tenant = kw.biz.tenant_id
    await add_source(db_session, tenant, title="Manual", text=MANUAL)
    async with tenant_scoped_session(db_session, tenant):
        # Ninguna palabra en común con el fragmento: solo lo encuentra el vector.
        hits = await search(db_session, tenant, kw.recepcion, "PINTURA zzz")
    assert hits and hits[0]["text"].startswith("PINTURA")


async def test_the_filter_is_inside_the_query_and_there_is_no_ann_index(
    db_session: AsyncSession, kw: Kw, embedder: Any
) -> None:
    for semantic in (True, False):
        sql = search_sql(semantic=semantic)
        assert "c.tenant_id = :tenant" in sql
        assert "(c.agent_id IS NULL OR c.agent_id = :agent)" in sql
    semantic_sql = search_sql(semantic=True)
    assert "v.tenant_id = :tenant" in semantic_sql
    assert "(v.agent_id IS NULL OR v.agent_id = :agent)" in semantic_sql
    async with tenant_scoped_session(db_session, kw.biz.tenant_id):
        index_kinds = (
            (
                await db_session.execute(
                    sa.text(
                        "SELECT am.amname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
                        "JOIN pg_am am ON am.oid = c.relam "
                        "WHERE i.indrelid IN ('knowledge_chunks'::regclass, "
                        "'knowledge_chunk_vectors'::regclass)"
                    )
                )
            )
            .scalars()
            .all()
        )
        plan = "\n".join(
            row[0]
            for row in (
                await db_session.execute(
                    sa.text("EXPLAIN " + search_sql(semantic=True)),
                    {
                        "tenant": kw.biz.tenant_id,
                        "agent": kw.recepcion,
                        "words": "garantia",
                        "n": 50,
                        "k": 60,
                        "vector": as_literal(vector_of("GARANTIA")),
                    },
                )
            ).all()
        )
    await db_session.commit()
    assert not {"hnsw", "ivfflat"} & set(index_kinds), "sin índice ANN compartido"
    assert "hnsw" not in plan.lower() and "ivfflat" not in plan.lower()


async def test_each_answer_keeps_its_sources(db_session: AsyncSession, kw: Kw) -> None:
    tenant = kw.biz.tenant_id
    async with tenant_scoped_session(db_session, tenant):
        customer = Customer(tenant_id=tenant, identifier="34600111000", preferences={})
        db_session.add(customer)
        await db_session.flush()
        from nexus_api.db.models import Channel, ChannelType

        channel = Channel(
            tenant_id=tenant,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"+3491{uuid.uuid4().int % 10**7:07d}",
            config={},
        )
        db_session.add(channel)
        await db_session.flush()
        conversation = Conversation(
            tenant_id=tenant,
            channel_id=channel.id,
            customer_id=customer.id,
            status=ConversationStatus.OPEN,
        )
        db_session.add(conversation)
        await db_session.flush()
        conv_id = conversation.id
    await db_session.commit()
    sources = [{"kind": "knowledge", "ref": str(uuid.uuid4()), "chunk": 2}]
    checkpoint = make_checkpoint_node()
    await checkpoint(
        {
            "tenant_id": str(tenant),
            "conversation_id": str(conv_id),
            "agent_id": str(kw.recepcion),
            "response": "La garantía es de dos años.",
            "tool_calls": [],
            "knowledge_sources": sources,
        }  # type: ignore[arg-type]
    )
    async with tenant_scoped_session(db_session, tenant):
        saved = (await db_session.scalars(sa.select(TurnSource))).all()
    await db_session.commit()
    assert len(saved) == 1
    assert saved[0].sources == sources and saved[0].agent_id == kw.recepcion


async def test_search_takes_under_30_ms_p95_with_5000_chunks(
    db_session: AsyncSession, kw: Kw, embedder: Any
) -> None:
    tenant = kw.biz.tenant_id
    doc_id = await add_source(db_session, tenant, title="Catálogo", text="Catálogo base.")
    rnd = random.Random(47)
    words = ["tornillo", "taladro", "pintura", "brocha", "llave", "martillo", "cable", "lija"]
    async with tenant_scoped_session(db_session, tenant):
        for start in range(0, 5_000, 500):
            chunks = [
                KnowledgeChunk(
                    id=uuid.uuid4(),
                    tenant_id=tenant,
                    document_id=doc_id,
                    agent_id=None,
                    ordinal=1 + n,
                    text=" ".join(rnd.choice(words) for _ in range(40)) + f" referencia {n}",
                )
                for n in range(start, start + 500)
            ]
            db_session.add_all(chunks)
            await db_session.flush()
            db_session.add_all(
                KnowledgeChunkVector(
                    chunk_id=c.id,
                    tenant_id=tenant,
                    document_id=doc_id,
                    agent_id=None,
                    embedding=[rnd.uniform(-1, 1) for _ in range(1024)],
                )
                for c in chunks
            )
            await db_session.flush()
        await db_session.execute(sa.text("ANALYZE knowledge_chunks"))
        await db_session.execute(sa.text("ANALYZE knowledge_chunk_vectors"))
    await db_session.commit()
    timings: list[float] = []
    async with tenant_scoped_session(db_session, tenant):
        await search(db_session, tenant, kw.recepcion, "taladro y brocha")  # calienta la caché
        for word in words * 3:
            begin = time.perf_counter()
            await search(db_session, tenant, kw.recepcion, f"necesito {word}")
            timings.append((time.perf_counter() - begin) * 1000)
    await db_session.commit()
    p95 = statistics.quantiles(timings, n=20)[18]
    assert p95 < 30, f"p95 = {p95:.1f} ms con 5.000 fragmentos"
