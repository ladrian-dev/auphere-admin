"""Las dos capas del conocimiento — spec 047, T133 (requisitos 37.1, 37.2 y 37.3).

Una fuente es **del negocio** (``agent_id`` nulo: la ven todos sus agentes) o
**propia de un agente**. Un agente ve las del negocio y las suyas; las de un
hermano, nunca, por ninguna vía (garantía 9): la consulta filtra por cliente y por
capa dentro de sí misma, no después.

Indexar parte el texto en fragmentos con su capa y, si hay modelo, su embedding.
Quitar no borra: se puede restaurar durante 10 minutos. Cada cambio sube la
revisión de su capa.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    KnowledgeChunk,
    KnowledgeChunkVector,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeRevision,
)
from nexus_api.services.knowledge.embeddings import embed
from nexus_api.services.knowledge_indexer import CHUNK_CHARS

RESTORE_WINDOW: Final = timedelta(minutes=10)


class KnowledgeError(Exception):
    def __init__(self, code: str, status: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def visible(agent_id: uuid.UUID | None) -> sa.ColumnElement[bool]:
    """La condición de capa que va **dentro** de cada consulta: las del negocio y,
    con agente, las suyas."""
    if agent_id is None:
        return KnowledgeDocument.agent_id.is_(None)
    return sa.or_(KnowledgeDocument.agent_id.is_(None), KnowledgeDocument.agent_id == agent_id)


async def visible_documents(
    session: AsyncSession, tenant_id: uuid.UUID, agent_id: uuid.UUID | None
) -> list[KnowledgeDocument]:
    return list(
        (
            await session.scalars(
                sa.select(KnowledgeDocument)
                .where(
                    KnowledgeDocument.tenant_id == tenant_id,
                    KnowledgeDocument.status == KnowledgeDocumentStatus.INDEXED.value,
                    KnowledgeDocument.removed_at.is_(None),
                    visible(agent_id),
                )
                .order_by(
                    KnowledgeDocument.agent_id.is_not(None),
                    KnowledgeDocument.created_at,
                    KnowledgeDocument.id,
                )
            )
        ).all()
    )


def split(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Fragmentos de hasta ``size`` caracteres, cortando por párrafos y, si un
    párrafo no cabe, por frases."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    out: list[str] = []
    current = ""
    for paragraph in paragraphs:
        pieces = [paragraph]
        if len(paragraph) > size:
            pieces = [s.strip() for s in re.split(r"(?<=[.!?])\s+", paragraph) if s.strip()]
        for piece in pieces:
            while len(piece) > size:
                out.append(piece[:size])
                piece = piece[size:]
            if current and len(current) + 2 + len(piece) > size:
                out.append(current)
                current = piece
            else:
                current = f"{current}\n\n{piece}" if current else piece
    if current:
        out.append(current)
    return out


async def index_document(session: AsyncSession, doc: KnowledgeDocument) -> int:
    """Rehace los fragmentos de una fuente con su capa. Devuelve cuántos."""
    await session.execute(
        sa.delete(KnowledgeChunk).where(
            KnowledgeChunk.tenant_id == doc.tenant_id, KnowledgeChunk.document_id == doc.id
        )
    )
    if doc.status != KnowledgeDocumentStatus.INDEXED.value or not doc.content_text:
        return 0
    pieces = split(doc.content_text)
    vectors = await embed(pieces)
    for ordinal, piece in enumerate(pieces):
        chunk = KnowledgeChunk(
            id=uuid.uuid4(),
            tenant_id=doc.tenant_id,
            document_id=doc.id,
            agent_id=doc.agent_id,
            ordinal=ordinal,
            text=piece,
        )
        session.add(chunk)
        if vectors:
            await session.flush()
            session.add(
                KnowledgeChunkVector(
                    chunk_id=chunk.id,
                    tenant_id=doc.tenant_id,
                    document_id=doc.id,
                    agent_id=doc.agent_id,
                    embedding=vectors[ordinal],
                )
            )
    doc.chunk_count = len(pieces)
    await session.flush()
    return len(pieces)


async def bump(session: AsyncSession, tenant_id: uuid.UUID, agent_id: uuid.UUID | None) -> int:
    """Sube la revisión de una capa (nulo = la del negocio)."""
    stmt = (
        sa.dialects.postgresql.insert(KnowledgeRevision)
        .values(tenant_id=tenant_id, agent_id=agent_id, rev=1)
        .on_conflict_do_update(
            constraint="uq_knowledge_revisions_layer",
            set_={"rev": KnowledgeRevision.rev + 1, "updated_at": sa.func.now()},
        )
        .returning(KnowledgeRevision.rev)
    )
    return int((await session.execute(stmt)).scalar_one())


async def remove(session: AsyncSession, doc: KnowledgeDocument, *, actor: str) -> None:
    """Quitar una fuente: deja de usarse desde el siguiente turno y se puede
    restaurar durante 10 minutos (37.3)."""
    if doc.removed_at is not None:
        return
    now = datetime.now(UTC)
    doc.removed_at = now
    doc.removed_by = actor
    doc.restore_until = now + RESTORE_WINDOW
    await bump(session, doc.tenant_id, doc.agent_id)
    await session.flush()


async def restore(session: AsyncSession, doc: KnowledgeDocument) -> None:
    if doc.removed_at is None:
        return
    if doc.restore_until is None or doc.restore_until < datetime.now(UTC):
        raise KnowledgeError("undo_window_closed")
    doc.removed_at = None
    doc.removed_by = None
    doc.restore_until = None
    await bump(session, doc.tenant_id, doc.agent_id)
    await session.flush()


__all__ = [
    "RESTORE_WINDOW",
    "KnowledgeError",
    "bump",
    "index_document",
    "remove",
    "restore",
    "split",
    "visible",
    "visible_documents",
]
