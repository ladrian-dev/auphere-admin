"""``/console/knowledge`` — the partner playbook (Fase 3 RAG).

Permission family ``playbook:*``. The client's KB stays at
``/console/clients/{ref}/knowledge`` with ``knowledge:*``. Responses
never carry ``content_text``. The body never carries ``partner_id``.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from nexus_api.db.models import (
    AuditLog,
    KnowledgeDocumentKind,
    KnowledgeDocumentStatus,
    KnowledgeErrorCode,
    PartnerKnowledgeDocument,
)
from nexus_api.services import knowledge_indexer as indexer
from nexus_api.services.knowledge_indexer import IndexingError

from .deps import PartnerScope, partner_scope
from .knowledge import PROMPT_CHAR_CAP, _mark
from .schemas_agent_tools import KnowledgeDocumentOut, KnowledgeListOut, KnowledgeUrlIn

router = APIRouter(prefix="/knowledge")


def _out(doc: PartnerKnowledgeDocument) -> KnowledgeDocumentOut:
    return KnowledgeDocumentOut.model_validate(doc, from_attributes=True)


def _audit(
    scope: PartnerScope, action: str, doc: PartnerKnowledgeDocument, after: dict[str, Any]
) -> None:
    scope.session.add(
        AuditLog(
            tenant_id=None,
            actor=scope.principal.actor,
            action=action,
            target=f"partner_knowledge_document:{doc.id}",
            after_json={"title": doc.title, "kind": doc.kind, **after},
        )
    )


@router.get("", response_model=KnowledgeListOut)
async def list_playbook(
    scope: PartnerScope = Depends(partner_scope("playbook:read")),
) -> KnowledgeListOut:
    rows = (
        await scope.session.scalars(
            sa.select(PartnerKnowledgeDocument).order_by(PartnerKnowledgeDocument.created_at.desc())
        )
    ).all()
    indexed_chars = await scope.session.scalar(
        sa.select(
            sa.func.coalesce(sa.func.sum(sa.func.length(PartnerKnowledgeDocument.content_text)), 0)
        ).where(PartnerKnowledgeDocument.status == KnowledgeDocumentStatus.INDEXED.value)
    )
    return KnowledgeListOut(
        items=[_out(r) for r in rows],
        total=len(rows),
        indexed_chars=int(indexed_chars or 0),
        prompt_char_cap=PROMPT_CHAR_CAP,
    )


@router.post(
    "",
    response_model=KnowledgeDocumentOut,
    status_code=status.HTTP_201_CREATED,
    responses={413: {"description": "File larger than 10 MB."}},
)
async def upload_playbook(
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=255),
    scope: PartnerScope = Depends(partner_scope("playbook:write")),
) -> KnowledgeDocumentOut:
    data = await file.read(indexer.MAX_UPLOAD_BYTES + 1)
    if len(data) > indexer.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file exceeds 10 MB"
        )
    filename = (file.filename or "document").strip()[:255] or "document"
    mime = indexer.guess_mime(filename, file.content_type)
    doc = PartnerKnowledgeDocument(
        partner_id=scope.principal.partner.id,
        kind=KnowledgeDocumentKind.FILE.value,
        title=(title or filename).strip()[:255] or filename,
        source_url=None,
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
    _audit(scope, "playbook.upload", doc, {"status": doc.status, "error_code": doc.error_code})
    await scope.session.refresh(doc)
    return _out(doc)


@router.post("/url", response_model=KnowledgeDocumentOut, status_code=status.HTTP_201_CREATED)
async def add_playbook_url(
    body: KnowledgeUrlIn,
    scope: PartnerScope = Depends(partner_scope("playbook:write")),
) -> KnowledgeDocumentOut:
    doc = PartnerKnowledgeDocument(
        partner_id=scope.principal.partner.id,
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
    _audit(scope, "playbook.add_url", doc, {"status": doc.status, "error_code": doc.error_code})
    await scope.session.refresh(doc)
    return _out(doc)


async def _index_url(
    doc: PartnerKnowledgeDocument, url: str, *, title_override: str | None
) -> None:
    try:
        fetched = await indexer.fetch_url(url)
    except IndexingError as exc:
        _mark(doc, None, exc.code)
        return
    _mark(doc, fetched.extracted, None)
    if not title_override and fetched.title:
        doc.title = fetched.title[:255]


async def _get(scope: PartnerScope, doc_id: uuid.UUID) -> PartnerKnowledgeDocument:
    doc = await scope.session.get(PartnerKnowledgeDocument, doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return doc


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playbook(
    doc_id: uuid.UUID,
    scope: PartnerScope = Depends(partner_scope("playbook:write")),
) -> None:
    doc = await _get(scope, doc_id)
    _audit(scope, "playbook.delete", doc, {})
    await scope.session.delete(doc)
    await scope.session.flush()


@router.post("/{doc_id}/reindex", response_model=KnowledgeDocumentOut)
async def reindex_playbook(
    doc_id: uuid.UUID,
    scope: PartnerScope = Depends(partner_scope("playbook:write")),
) -> KnowledgeDocumentOut:
    doc = await _get(scope, doc_id)
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
    _audit(scope, "playbook.reindex", doc, {"status": doc.status, "error_code": doc.error_code})
    await scope.session.refresh(doc)
    return _out(doc)


__all__ = ["router"]
