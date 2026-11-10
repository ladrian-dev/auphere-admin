"""El conocimiento propio de un agente y «Enseñar» — spec 047, T133 (requisitos
37.1 y 37.3; ``contracts/console-api.md`` §4).

- ``GET /clients/{ref}/agents/{agent_id}/knowledge``: las fuentes de la capa del
  agente y, aparte, cuántas tiene la del negocio (que se gestiona en Negocio);
- ``POST …/knowledge`` (archivo) · ``POST …/knowledge/url``: una fuente solo para
  este agente;
- ``DELETE …/knowledge/{doc_id}`` · ``POST …/knowledge/{doc_id}/restore``: quitar,
  con 10 minutos para restaurar;
- ``POST …/teach`` ``{text, scope: business | agent}``: se aplica al momento, con
  historial y deshacer, y vuelve a pasar las pruebas afectadas.

Una fuente de otro agente (o de otro cliente) es un 404: ni se lista ni se toca
desde aquí (garantía 9). Las respuestas nunca llevan el texto.
"""

from __future__ import annotations

import uuid
from typing import Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from nexus_api.db.models import (
    KnowledgeDocument,
    KnowledgeDocumentKind,
    KnowledgeDocumentStatus,
    KnowledgeErrorCode,
)
from nexus_api.services import knowledge_indexer as indexer
from nexus_api.services.knowledge import layers
from nexus_api.services.knowledge.teach import MAX_CHARS, layer_documents, teach
from nexus_api.services.knowledge_indexer import IndexingError

from .agent_draft_routes import agent_in_path
from .deps import ClientScope
from .knowledge import _audit, _get, _index_url, _mark, _out, indexed
from .schemas_agent_tools import KnowledgeDocumentOut, KnowledgeUrlIn

router = APIRouter(prefix="/clients/{ref}/agents/{agent_id}")


class AgentKnowledgeOut(BaseModel):
    items: list[KnowledgeDocumentOut]
    #: Las fuentes de la capa del negocio, que también ve este agente.
    business_sources: int


class TeachIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=MAX_CHARS)
    scope: Literal["business", "agent"]


def _agent(scope: ClientScope) -> uuid.UUID:
    assert scope.agent_id is not None
    return scope.agent_id


@router.get("/knowledge", response_model=AgentKnowledgeOut)
async def list_agent_knowledge(
    scope: ClientScope = Depends(agent_in_path("knowledge:read")),
) -> AgentKnowledgeOut:
    agent_id = _agent(scope)
    own = await layer_documents(scope.session, scope.tenant.id, agent_id)
    business = await scope.session.scalar(
        sa.select(sa.func.count())
        .select_from(KnowledgeDocument)
        .where(
            KnowledgeDocument.tenant_id == scope.tenant.id,
            KnowledgeDocument.agent_id.is_(None),
            KnowledgeDocument.removed_at.is_(None),
            KnowledgeDocument.status == KnowledgeDocumentStatus.INDEXED.value,
        )
    )
    return AgentKnowledgeOut(items=[_out(d) for d in own], business_sources=int(business or 0))


@router.post(
    "/knowledge",
    response_model=KnowledgeDocumentOut,
    status_code=status.HTTP_201_CREATED,
    responses={413: {"description": "File larger than 10 MB."}},
)
async def upload_agent_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=255),
    scope: ClientScope = Depends(agent_in_path("knowledge:write")),
) -> KnowledgeDocumentOut:
    data = await file.read(indexer.MAX_UPLOAD_BYTES + 1)
    if len(data) > indexer.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file exceeds 10 MB"
        )
    filename = (file.filename or "document").strip()[:255] or "document"
    mime = indexer.guess_mime(filename, file.content_type)
    doc = KnowledgeDocument(
        tenant_id=scope.tenant.id,
        agent_id=_agent(scope),
        kind=KnowledgeDocumentKind.FILE.value,
        title=(title or filename).strip()[:255] or filename,
        mime=mime,
        size_bytes=len(data),
        status=KnowledgeDocumentStatus.PENDING.value,
        created_by=scope.principal.actor,
    )
    try:
        extracted: indexer.Extracted | None = indexer.extract_text(data, mime=mime)
        error: KnowledgeErrorCode | None = None
    except IndexingError as exc:
        extracted, error = None, exc.code
    _mark(doc, extracted, error)
    scope.session.add(doc)
    await scope.session.flush()
    await indexed(scope, doc)
    _audit(scope, "knowledge.upload", doc, {"status": doc.status, "agent_id": str(doc.agent_id)})
    await scope.session.refresh(doc)
    return _out(doc)


@router.post(
    "/knowledge/url", response_model=KnowledgeDocumentOut, status_code=status.HTTP_201_CREATED
)
async def add_agent_url(
    body: KnowledgeUrlIn, scope: ClientScope = Depends(agent_in_path("knowledge:write"))
) -> KnowledgeDocumentOut:
    doc = KnowledgeDocument(
        tenant_id=scope.tenant.id,
        agent_id=_agent(scope),
        kind=KnowledgeDocumentKind.URL.value,
        title=(body.title or body.url).strip()[:255],
        source_url=body.url,
        mime="text/html",
        size_bytes=0,
        status=KnowledgeDocumentStatus.PENDING.value,
        created_by=scope.principal.actor,
    )
    await _index_url(doc, body.url, title_override=body.title)
    scope.session.add(doc)
    await scope.session.flush()
    await indexed(scope, doc)
    _audit(scope, "knowledge.add_url", doc, {"status": doc.status, "agent_id": str(doc.agent_id)})
    await scope.session.refresh(doc)
    return _out(doc)


@router.delete("/knowledge/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_agent_document(
    doc_id: uuid.UUID, scope: ClientScope = Depends(agent_in_path("knowledge:write"))
) -> None:
    doc = await _get(scope, doc_id, agent_id=_agent(scope))
    _audit(scope, "knowledge.delete", doc, {"agent_id": str(doc.agent_id)})
    await layers.remove(scope.session, doc, actor=scope.principal.actor)


@router.post("/knowledge/{doc_id}/restore", response_model=KnowledgeDocumentOut)
async def restore_agent_document(
    doc_id: uuid.UUID, scope: ClientScope = Depends(agent_in_path("knowledge:write"))
) -> KnowledgeDocumentOut:
    doc = await _get(scope, doc_id, agent_id=_agent(scope), removed=True)
    try:
        await layers.restore(scope.session, doc)
    except layers.KnowledgeError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code}) from None
    _audit(scope, "knowledge.restore", doc, {"agent_id": str(doc.agent_id)})
    await scope.session.refresh(doc)
    return _out(doc)


@router.post("/knowledge/{doc_id}/reindex", response_model=KnowledgeDocumentOut)
async def reindex_agent_document(
    doc_id: uuid.UUID, scope: ClientScope = Depends(agent_in_path("knowledge:write"))
) -> KnowledgeDocumentOut:
    """«Volver a leer» una fuente del agente (12.3): una URL se vuelve a pedir;
    un archivo se vuelve a trocear desde su texto."""
    doc = await _get(scope, doc_id, agent_id=_agent(scope))
    if doc.kind == KnowledgeDocumentKind.URL.value and doc.source_url:
        await _index_url(doc, doc.source_url, title_override=doc.title)
    elif doc.content_text:
        _mark(
            doc,
            indexer.Extracted(text=doc.content_text, mime=doc.mime, size_bytes=doc.size_bytes),
            None,
        )
    else:
        _mark(doc, None, KnowledgeErrorCode(doc.error_code or "empty"))
    await scope.session.flush()
    await indexed(scope, doc)
    _audit(scope, "knowledge.reindex", doc, {"status": doc.status, "agent_id": str(doc.agent_id)})
    await scope.session.refresh(doc)
    return _out(doc)


@router.post("/teach", response_model=KnowledgeDocumentOut, status_code=status.HTTP_201_CREATED)
async def teach_agent(
    body: TeachIn, scope: ClientScope = Depends(agent_in_path("knowledge:write"))
) -> KnowledgeDocumentOut:
    """«Enseñar» (37.3): el alcance lo elige la persona; se deshace quitando la
    fuente que crea (10 minutos para restaurarla)."""
    try:
        doc = await teach(
            scope.session,
            tenant_id=scope.tenant.id,
            agent_id=_agent(scope),
            text=body.text,
            scope=body.scope,
            actor=scope.principal.actor,
        )
    except layers.KnowledgeError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code}) from None
    await scope.session.refresh(doc)
    return _out(doc)


__all__ = ["router"]
