"""El mundo de las pruebas del conocimiento — spec 047, T130 y T131.

Un cliente con dos agentes publicados (Recepción y Ventas), fuentes en la capa
del negocio y en la de cada uno, y un embedder de mentira determinista: la misma
palabra clave da el mismo vector, así la búsqueda semántica se puede comprobar.
"""

from __future__ import annotations

import hashlib
import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import KnowledgeDocument, KnowledgeDocumentKind, KnowledgeDocumentStatus
from nexus_api.services.knowledge import layers

from ..business._business_world import Biz, seed_agent

DIM = 1024


def vector_of(text: str) -> list[float]:
    """Un vector por palabra «clave» (la primera en mayúsculas del texto), de
    norma 1: dos textos con la misma clave quedan a distancia 0."""
    key = next((w for w in text.split() if w.isupper() and len(w) > 2), text[:12])
    seed = hashlib.sha256(key.encode()).digest()
    raw = [((seed[i % 32] + i * 7) % 251) - 125 for i in range(DIM)]
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [x / norm for x in raw]


async def fake_embedder(texts: Sequence[str]) -> list[list[float]]:
    return [vector_of(t) for t in texts]


@dataclass
class Kw:
    biz: Biz
    recepcion: uuid.UUID
    ventas: uuid.UUID


async def two_agents(db_session: Any, biz: Biz) -> Kw:
    recepcion, _ = await seed_agent(
        db_session, biz.tenant_id, name="Recepción", prompt="Recepción."
    )
    ventas, _ = await seed_agent(db_session, biz.tenant_id, name="Ventas", prompt="Ventas.")
    await db_session.commit()
    return Kw(biz=biz, recepcion=recepcion, ventas=ventas)


async def add_source(
    db_session: Any,
    tenant_id: uuid.UUID,
    *,
    title: str,
    text: str,
    agent_id: uuid.UUID | None = None,
) -> uuid.UUID:
    async with tenant_scoped_session(db_session, tenant_id):
        doc = KnowledgeDocument(
            tenant_id=tenant_id,
            agent_id=agent_id,
            kind=KnowledgeDocumentKind.NOTE.value,
            title=title,
            mime="text/plain",
            size_bytes=len(text),
            status=KnowledgeDocumentStatus.INDEXED.value,
            content_text=text,
            indexed_at=datetime.now(UTC),
        )
        db_session.add(doc)
        await db_session.flush()
        await layers.index_document(db_session, doc)
        await layers.bump(db_session, tenant_id, agent_id)
        doc_id = doc.id
    await db_session.commit()
    return doc_id
