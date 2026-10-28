"""«Enseñar» — spec 047, T133 (requisito 37.3).

Una persona escribe algo que el agente debe saber y elige el alcance:

- ``business``: para todos los agentes del cliente (la capa del negocio);
- ``agent``: solo para este agente (su capa).

Se aplica al momento (el siguiente turno ya lo tiene), queda en la auditoría con
quién y qué capa, se deshace como cualquier fuente (10 minutos para restaurarla) y
vuelve a pasar las pruebas de los agentes que lo ven: todos con ``business``, solo
este con ``agent``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Final, Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    AuditLog,
    KnowledgeDocument,
    KnowledgeDocumentKind,
    KnowledgeDocumentStatus,
)
from nexus_api.services.knowledge.layers import KnowledgeError, bump, index_document

Scope = Literal["business", "agent"]
MAX_CHARS: Final = 5_000


def _title(text: str) -> str:
    first = text.strip().splitlines()[0] if text.strip() else ""
    return (first[:77] + "…") if len(first) > 80 else (first or "Lo que se enseñó")


async def teach(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID,
    text: str,
    scope: Scope,
    actor: str,
    origin: str | None = None,
) -> KnowledgeDocument:
    """``origin``: desde dónde (``events.md`` §4); lo pasa quien no es la consola
    del partner (una corrección desde la lite o la app, spec 047 T176)."""
    body = (text or "").strip()
    if not body:
        raise KnowledgeError("teach_empty", 422)
    if len(body) > MAX_CHARS:
        raise KnowledgeError("teach_too_long", 422)
    layer = agent_id if scope == "agent" else None
    doc = KnowledgeDocument(
        tenant_id=tenant_id,
        agent_id=layer,
        kind=KnowledgeDocumentKind.NOTE.value,
        title=_title(body),
        mime="text/plain",
        size_bytes=len(body.encode()),
        status=KnowledgeDocumentStatus.INDEXED.value,
        content_text=body,
        created_by=actor,
        indexed_at=datetime.now(UTC),
    )
    session.add(doc)
    await session.flush()
    await index_document(session, doc)
    await bump(session, tenant_id, layer)
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=actor,
            action="knowledge.taught",
            target=f"knowledge_document:{doc.id}",
            after_json={
                "scope": scope,
                "agent_id": str(agent_id),
                "chars": len(body),
                **({"origin": origin} if origin else {}),
            },
        )
    )
    await retest(session, agent_id=layer)
    return doc


async def retest(session: AsyncSession, *, agent_id: uuid.UUID | None) -> int:
    """Vuelve a pasar las pruebas de los agentes que ven el cambio: todos si es
    de la capa del negocio, solo ese si es de su capa (37.3)."""
    from nexus_api.services.business.writes import mark_tests_stale

    return await mark_tests_stale(session, sections=["knowledge"], only_agent=agent_id)


async def layer_documents(
    session: AsyncSession, tenant_id: uuid.UUID, agent_id: uuid.UUID | None
) -> list[KnowledgeDocument]:
    """Las fuentes de una capa (nulo = la del negocio), con las quitadas que aún
    se pueden restaurar."""
    layer = (
        KnowledgeDocument.agent_id.is_(None)
        if agent_id is None
        else KnowledgeDocument.agent_id == agent_id
    )
    # Lo quitado se lista mientras se puede restaurar; después, ya no.
    restorable = sa.or_(
        KnowledgeDocument.removed_at.is_(None),
        KnowledgeDocument.restore_until > sa.func.now(),
    )
    return list(
        (
            await session.scalars(
                sa.select(KnowledgeDocument)
                .where(KnowledgeDocument.tenant_id == tenant_id, layer, restorable)
                .order_by(KnowledgeDocument.created_at.desc())
            )
        ).all()
    )


__all__ = ["MAX_CHARS", "Scope", "layer_documents", "retest", "teach"]
