"""``/console/clients/{ref}/knowledge`` — the client's documents and URLs
(CP-15).

v1 pipeline, synchronous in the request: receive → extract text
(``services/knowledge_indexer.py``) → store ``content_text`` → status
``indexed`` (or ``failed`` + ``error_code``). The worker injects the
indexed texts into the system prompt (``knowledge_context``), so a
document uploaded here shows up in the next answer without a vector
store. Only ``content_text`` is stored — no binary, no S3 in v1
(``s3_key`` reserved); a re-index of a file re-parses nothing new, it
re-counts chunks from the stored text; a re-index of a URL re-fetches.

Permission family ``knowledge:*``. Responses never carry the text.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from nexus_api.db.models import (
    AuditLog,
    KnowledgeDocument,
    KnowledgeDocumentKind,
    KnowledgeDocumentStatus,
    KnowledgeErrorCode,
)
from nexus_api.services import knowledge_indexer as indexer
from nexus_api.services.knowledge_indexer import IndexingError

from .deps import ClientScope, client_scope
from .schemas_agent_tools import KnowledgeDocumentOut, KnowledgeListOut, KnowledgeUrlIn

router = APIRouter(prefix="/clients/{ref}/knowledge")

#: What the worker injects at most (characters, over all indexed docs).
PROMPT_CHAR_CAP = 20_000


def _out(doc: KnowledgeDocument) -> KnowledgeDocumentOut:
    return KnowledgeDocumentOut.model_validate(doc, from_attributes=True)


def _mark(
    doc: KnowledgeDocument, extracted: indexer.Extracted | None, error: KnowledgeErrorCode | None
) -> None:
    if extracted is not None:
        doc.content_text = extracted.text
        doc.mime = extracted.mime
        doc.size_bytes = extracted.size_bytes
        doc.chunk_count = extracted.chunk_count
        doc.status = KnowledgeDocumentStatus.INDEXED.value
        doc.error_code = None
        doc.indexed_at = datetime.now(UTC)
    else:
        doc.status = KnowledgeDocumentStatus.FAILED.value
        doc.error_code = error.value if error else KnowledgeErrorCode.FETCH_FAILED.value
        doc.chunk_count = 0


def _audit(scope: ClientScope, action: str, doc: KnowledgeDocument, after: dict[str, Any]) -> None:
    scope.session.add(
        AuditLog(
            tenant_id=scope.tenant.id,
            actor=scope.principal.actor,
            action=action,
            target=f"knowledge_document:{doc.id}",
            after_json={"title": doc.title, "kind": doc.kind, **after},
        )
    )


@router.get("", response_model=KnowledgeListOut)
async def list_documents(
    scope: ClientScope = Depends(client_scope("knowledge:read")),
) -> KnowledgeListOut:
    rows = (
        await scope.session.scalars(
            sa.select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
        )
    ).all()
    indexed_chars = await scope.session.scalar(
        sa.select(
            sa.func.coalesce(sa.func.sum(sa.func.length(KnowledgeDocument.content_text)), 0)
        ).where(KnowledgeDocument.status == KnowledgeDocumentStatus.INDEXED.value)
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
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=255),
    scope: ClientScope = Depends(client_scope("knowledge:write")),
) -> KnowledgeDocumentOut:
    """Multipart upload (PDF / TXT / MD / HTML, ≤ 10 MB). Indexed inline."""
    data = await file.read(indexer.MAX_UPLOAD_BYTES + 1)
    if len(data) > indexer.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file exceeds 10 MB"
        )
    filename = (file.filename or "document").strip()[:255] or "document"
    mime = indexer.guess_mime(filename, file.content_type)
    doc = KnowledgeDocument(
        tenant_id=scope.tenant.id,
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
    _audit(scope, "knowledge.upload", doc, {"status": doc.status, "error_code": doc.error_code})
    await scope.session.refresh(doc)
    return _out(doc)


@router.post("/url", response_model=KnowledgeDocumentOut, status_code=status.HTTP_201_CREATED)
async def add_url(
    body: KnowledgeUrlIn,
    scope: ClientScope = Depends(client_scope("knowledge:write")),
) -> KnowledgeDocumentOut:
    """Fetch a public http(s) URL and index its text. A failed fetch is
    a ``failed`` document with an explainable ``error_code`` (201, not an
    error): the partner sees it in the table and can re-index later."""
    doc = KnowledgeDocument(
        tenant_id=scope.tenant.id,
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
    _audit(scope, "knowledge.add_url", doc, {"status": doc.status, "error_code": doc.error_code})
    await scope.session.refresh(doc)
    return _out(doc)


async def _index_url(doc: KnowledgeDocument, url: str, *, title_override: str | None) -> None:
    try:
        fetched = await indexer.fetch_url(url)
    except IndexingError as exc:
        _mark(doc, None, exc.code)
        return
    _mark(doc, fetched.extracted, None)
    if not title_override and fetched.title:
        doc.title = fetched.title[:255]


async def _get(scope: ClientScope, doc_id: uuid.UUID) -> KnowledgeDocument:
    doc = await scope.session.get(KnowledgeDocument, doc_id)
    if doc is None:  # RLS: another tenant's id is simply not there
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return doc


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: uuid.UUID,
    scope: ClientScope = Depends(client_scope("knowledge:write")),
) -> None:
    doc = await _get(scope, doc_id)
    _audit(scope, "knowledge.delete", doc, {})
    await scope.session.delete(doc)
    await scope.session.flush()


@router.post("/{doc_id}/reindex", response_model=KnowledgeDocumentOut)
async def reindex_document(
    doc_id: uuid.UUID,
    scope: ClientScope = Depends(client_scope("knowledge:write")),
) -> KnowledgeDocumentOut:
    """URL: re-fetch. File: re-derive from the stored text (no binary is
    kept in v1), so a failed file needs a re-upload — reported as-is."""
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
    _audit(scope, "knowledge.reindex", doc, {"status": doc.status, "error_code": doc.error_code})
    await scope.session.refresh(doc)
    return _out(doc)


__all__ = ["PROMPT_CHAR_CAP", "router"]
