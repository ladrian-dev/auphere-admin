"""Documentos y webs del negocio — spec 047, T071 (historia 17, requisito 12).

Las fuentes de la capa del negocio son las filas de ``knowledge_documents`` del
cliente (el turno inyecta las indexadas, ``console_context.load_knowledge_block``).
La capa propia de cada agente (``agent_id``) llega con la ola 5; hasta entonces
todas las fuentes son del negocio.

**Indexar ya no es la petición: es un trabajo.** Subir un archivo (hasta 10 MB:
PDF, Word, fotos de cartas, TXT, MD y HTML) o añadir una web deja la fuente
``pending`` («Leyendo») y encola un ``client_read`` con el detalle en su
``progress`` (``source_id`` y ``action``). El manejador del worker llama a
:func:`index_source`, que:

1. saca el texto, sobre ``services/knowledge_indexer.py`` (sus guardas de
   direcciones públicas y de tamaño), más Word sin dependencias nuevas y las fotos
   con un modelo con visión;
2. deja la fuente ``indexed`` o ``failed`` con su motivo;
3. pasa el texto, vallado como dato (§III), por el mismo extractor que la lectura
   de la web (``reader.build_messages``/``parse_extraction``) y aplica lo hallado
   con ``reader.apply_extraction``: lo que choca con lo escrito por una persona y
   los servicios con precio quedan como **propuestas** pendientes (12.3, 12.5).

Todo lo que gasta un modelo (la extracción y la visión) corre dentro del turno de
uso del lector, en la partida «Construcción y pruebas» (12.6).

**Quitar** (12.2) borra la fila —el siguiente turno ya no la ve— y guarda una
copia en el historial de la sección ``sources``; durante 10 minutos
:func:`restore` la devuelve tal cual (``business.section_undone``). **Releer**
(12.3): «Volver a leer» y :func:`reread_due`, la pasada semanal del cron
``source_reread_cron``, que también vuelve a leer la web y las redes del cliente.
"""

from __future__ import annotations

import io
import re
import uuid
import zipfile
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final, cast
from xml.etree import ElementTree

import httpx
import sqlalchemy as sa
import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus_api.core.tenant_context import require_current_tenant, tenant_scoped_session
from nexus_api.db.models import (
    Job,
    KnowledgeDocument,
    KnowledgeDocumentKind,
    KnowledgeDocumentStatus,
    KnowledgeErrorCode,
    Tenant,
    TenantStatus,
)
from nexus_api.db.models.business import BusinessChange, BusinessProfile
from nexus_api.db.models.jobs import LIVE_JOB_STATUSES
from nexus_api.services import knowledge_indexer as indexer
from nexus_api.services.business import client_spec
from nexus_api.services.business.sections import READER, Actor, touch_section
from nexus_api.services.business.writes import write_section

log = structlog.get_logger(__name__)

MAX_UPLOAD_BYTES: Final = indexer.MAX_UPLOAD_BYTES
DOCX_MIME: Final = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
IMAGE_MIMES: Final = frozenset({"image/jpeg", "image/png", "image/webp"})
_EXTRA_EXT: Final[dict[str, str]] = {
    ".docx": DOCX_MIME,
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_DOCX_XML_MAX: Final = 40 * 1024 * 1024
#: Quitar se deshace durante este rato (§IV, research parte 7).
RESTORE_WINDOW: Final = timedelta(minutes=10)
#: Una web se vuelve a leer a la semana de leída.
REREAD_AFTER: Final = timedelta(days=7)
#: ``knowledge_documents.error_code`` → el motivo que enseña la consola.
FAILURE_OF: Final[dict[str, str]] = {
    KnowledgeErrorCode.FETCH_FAILED.value: "unreachable",
    KnowledgeErrorCode.UNSUPPORTED_TYPE.value: "no_text",
    KnowledgeErrorCode.EMPTY.value: "no_text",
    KnowledgeErrorCode.TOO_LARGE.value: "too_large",
}

ADDED_ACTION: Final = "source.added"
REMOVED_ACTION: Final = "source.removed"
REREAD_ACTION: Final = "source.reread"

#: El texto de una foto, del modelo con visión: ``(bytes, mime) → texto``.
Vision = Callable[[bytes, str], Awaitable[str]]
Extract = Callable[[list[dict[str, str]]], Awaitable[str]]


class SourceError(Exception):
    """Un no con nombre: ``code`` cerrado y el HTTP que le toca."""

    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def source_mime(filename: str | None, declared: str | None) -> str | None:
    """El tipo de un archivo subido, si es uno que se sabe leer."""
    base = (declared or "").split(";", 1)[0].strip().lower()
    if base in indexer.SUPPORTED_MIMES or base in IMAGE_MIMES or base == DOCX_MIME:
        return base
    lower = (filename or "").lower()
    for ext, mime in _EXTRA_EXT.items():
        if lower.endswith(ext):
            return mime
    guessed = indexer.guess_mime(filename, declared)
    return guessed if guessed in indexer.SUPPORTED_MIMES else None


def docx_text(data: bytes) -> str:
    """El texto de un Word (``word/document.xml``), sin dependencias nuevas."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            # Una bomba de compresión no se descomprime: el texto de un Word cabe de sobra.
            if z.getinfo("word/document.xml").file_size > _DOCX_XML_MAX:
                raise indexer.IndexingError(KnowledgeErrorCode.TOO_LARGE)
            xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise indexer.IndexingError(KnowledgeErrorCode.UNSUPPORTED_TYPE) from exc
    # Sin DTD ni entidades: un Word de verdad no las trae, y así no hay expansión.
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise indexer.IndexingError(KnowledgeErrorCode.UNSUPPORTED_TYPE)
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise indexer.IndexingError(KnowledgeErrorCode.UNSUPPORTED_TYPE) from exc
    paragraphs = ["".join(t.text or "" for t in p.iter(f"{ns}t")) for p in root.iter(f"{ns}p")]
    return indexer.clean_text("\n\n".join(p for p in paragraphs if p.strip()))


# ── lo que enseña la consola ───────────────────────────────────────────────────


def failure_of(doc: KnowledgeDocument) -> str | None:
    if doc.status != KnowledgeDocumentStatus.FAILED.value:
        return None
    return FAILURE_OF.get(doc.error_code or "", "unreachable")


async def list_sources(session: AsyncSession) -> list[KnowledgeDocument]:
    rows = (
        await session.scalars(
            sa.select(KnowledgeDocument)
            .where(KnowledgeDocument.tenant_id == require_current_tenant())
            .order_by(KnowledgeDocument.created_at.desc(), KnowledgeDocument.id)
        )
    ).all()
    return list(rows)


@dataclass(frozen=True)
class Removed:
    id: uuid.UUID
    title: str
    kind: str
    restore_until: datetime
    change_id: uuid.UUID


def _removed_of(row: BusinessChange) -> dict[str, Any] | None:
    snapshot = (row.after or {}).get("removed")
    return snapshot if isinstance(snapshot, dict) and snapshot.get("id") else None


async def removed_sources(session: AsyncSession, *, now: datetime | None = None) -> list[Removed]:
    """Lo quitado que aún se puede recuperar."""
    now = now or datetime.now(UTC)
    rows = (
        await session.scalars(
            sa.select(BusinessChange)
            .where(
                BusinessChange.tenant_id == require_current_tenant(),
                BusinessChange.section == "sources",
                BusinessChange.undone_at.is_(None),
                BusinessChange.at > now - RESTORE_WINDOW,
            )
            .order_by(BusinessChange.at.desc())
        )
    ).all()
    out: list[Removed] = []
    seen: set[str] = set()
    for row in rows:
        snap = _removed_of(row)
        if snap is None or snap["id"] in seen:
            continue
        seen.add(snap["id"])
        if await session.get(KnowledgeDocument, uuid.UUID(snap["id"])) is not None:
            continue
        out.append(
            Removed(
                id=uuid.UUID(snap["id"]),
                title=str(snap.get("title") or ""),
                kind=str(snap.get("kind") or "file"),
                restore_until=row.at + RESTORE_WINDOW,
                change_id=row.id,
            )
        )
    return out


# ── añadir, releer, quitar y recuperar ─────────────────────────────────────────


async def _view(session: AsyncSession) -> dict[str, Any]:
    return await client_spec.section_view(session, "sources")


async def _new_job(
    session: AsyncSession, doc: KnowledgeDocument, *, action: str, created_by: str | None
) -> Job:
    from nexus_api.services.jobs import create_job

    job = await create_job(session, kind="client_read", created_by=created_by)
    job.progress = {
        "step": None,
        "blocks": [],
        "source_id": str(doc.id),
        "action": action,
    }
    await session.flush()
    return job


async def _write(
    session: AsyncSession,
    *,
    actor: Actor,
    before: dict[str, Any],
    after: dict[str, Any],
    pointers: Sequence[str],
    audit_action: str,
    audit_actor: str | None,
    kind: str = "edit",
    undo_of: uuid.UUID | None = None,
) -> None:
    documents = after.get("documents") or []
    await write_section(
        session,
        "sources",
        actor=actor,
        before=before,
        after=after,
        pointers=pointers,
        kind=kind,
        state="complete" if documents else "pending",
        audit_actor=audit_actor,
        audit_action=audit_action,
        undo_of=undo_of,
    )


async def add_file(
    session: AsyncSession,
    *,
    filename: str,
    declared_type: str | None,
    data: bytes,
    tenant_slug: str,
    actor: Actor,
    audit_actor: str | None = None,
    created_by: str | None = None,
) -> tuple[KnowledgeDocument, Job]:
    """Un archivo del negocio: se guarda, queda «Leyendo» y se encola su lectura."""
    from nexus_api.services.media_storage import get_media_storage

    if len(data) > MAX_UPLOAD_BYTES:
        raise SourceError("too_large", 413)
    mime = source_mime(filename, declared_type)
    if mime is None:
        raise SourceError("unsupported_type", 415)
    title = (filename or "documento").strip()[:255] or "documento"
    stored = await get_media_storage().put_outbound(
        tenant_slug=tenant_slug, content=data, content_type=mime, filename=title
    )
    before = await _view(session)
    doc = KnowledgeDocument(
        tenant_id=require_current_tenant(),
        kind=KnowledgeDocumentKind.FILE.value,
        title=title,
        source_url=None,
        s3_key=stored.key,
        mime=mime,
        size_bytes=len(data),
        status=KnowledgeDocumentStatus.PENDING.value,
        created_by=audit_actor,
    )
    session.add(doc)
    await session.flush()
    await _write(
        session,
        actor=actor,
        before=before,
        after=await _view(session),
        pointers=[f"/documents/{doc.id}"],
        audit_action=ADDED_ACTION,
        audit_actor=audit_actor,
    )
    return doc, await _new_job(session, doc, action="index", created_by=created_by)


_URL = re.compile(r"^https?://[^\s]{1,2040}$", re.IGNORECASE)


async def add_url(
    session: AsyncSession,
    *,
    url: str,
    title: str | None,
    actor: Actor,
    audit_actor: str | None = None,
    created_by: str | None = None,
) -> tuple[KnowledgeDocument, Job]:
    """Una web del negocio. Las guardas (dirección pública, tamaño) se aplican al
    leerla, en el trabajo."""
    clean = url.strip()
    if not _URL.match(clean):
        raise SourceError("invalid_url", 422)
    before = await _view(session)
    doc = KnowledgeDocument(
        tenant_id=require_current_tenant(),
        kind=KnowledgeDocumentKind.URL.value,
        title=((title or "").strip() or clean)[:255],
        source_url=clean,
        mime="text/html",
        size_bytes=0,
        status=KnowledgeDocumentStatus.PENDING.value,
        created_by=audit_actor,
    )
    session.add(doc)
    await session.flush()
    await _write(
        session,
        actor=actor,
        before=before,
        after=await _view(session),
        pointers=[f"/documents/{doc.id}"],
        audit_action=ADDED_ACTION,
        audit_actor=audit_actor,
    )
    return doc, await _new_job(session, doc, action="index", created_by=created_by)


async def _get(session: AsyncSession, doc_id: uuid.UUID) -> KnowledgeDocument:
    doc = await session.get(KnowledgeDocument, doc_id)
    if doc is None or doc.tenant_id != require_current_tenant():
        raise SourceError("unknown_source", 404)
    return doc


async def _live_job(session: AsyncSession, source_id: uuid.UUID) -> Job | None:
    job: Job | None = await session.scalar(
        sa.select(Job)
        .where(
            Job.tenant_id == require_current_tenant(),
            Job.kind == "client_read",
            Job.status.in_(LIVE_JOB_STATUSES),
            Job.progress["source_id"].astext == str(source_id),
        )
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    return job


async def reread(
    session: AsyncSession,
    doc_id: uuid.UUID,
    *,
    actor: Actor,
    audit_actor: str | None = None,
    created_by: str | None = None,
) -> tuple[KnowledgeDocument, Job, bool]:
    """«Volver a leer». Una lectura en marcha no se lanza dos veces:
    ``(fuente, trabajo, creado)``."""
    from nexus_api.db.models import AuditLog

    doc = await _get(session, doc_id)
    live = await _live_job(session, doc.id)
    if live is not None:
        return doc, live, False
    doc.status = KnowledgeDocumentStatus.PENDING.value
    session.add(
        AuditLog(
            tenant_id=doc.tenant_id,
            actor=audit_actor or "system:source_reread",
            action=REREAD_ACTION,
            target=f"knowledge_document:{doc.id}",
            after_json={"title": doc.title, "kind": doc.kind, "origin": actor.origin},
        )
    )
    await session.flush()
    return doc, await _new_job(session, doc, action="reread", created_by=created_by), True


_SNAPSHOT_FIELDS: Final[tuple[str, ...]] = (
    "kind",
    "title",
    "source_url",
    "s3_key",
    "mime",
    "size_bytes",
    "status",
    "error_code",
    "chunk_count",
    "content_text",
    "created_by",
)


async def remove(
    session: AsyncSession,
    doc_id: uuid.UUID,
    *,
    actor: Actor,
    audit_actor: str | None = None,
) -> datetime:
    """Quita la fuente: el siguiente mensaje ya no la usa. Devuelve hasta
    cuándo se puede recuperar."""
    doc = await _get(session, doc_id)
    before = await _view(session)
    snapshot: dict[str, Any] = {"id": str(doc.id)}
    for name in _SNAPSHOT_FIELDS:
        snapshot[name] = getattr(doc, name)
    snapshot["indexed_at"] = doc.indexed_at.isoformat() if doc.indexed_at else None
    snapshot["created_at"] = doc.created_at.isoformat() if doc.created_at else None
    await session.delete(doc)
    await session.flush()
    after = await _view(session)
    await _write(
        session,
        actor=actor,
        before=before,
        after={**after, "removed": snapshot},
        pointers=[],
        audit_action=REMOVED_ACTION,
        audit_actor=audit_actor,
    )
    return datetime.now(UTC) + RESTORE_WINDOW


async def restore(
    session: AsyncSession,
    doc_id: uuid.UUID,
    *,
    actor: Actor,
    audit_actor: str | None = None,
    now: datetime | None = None,
) -> KnowledgeDocument:
    """Devuelve una fuente quitada hace menos de 10 minutos, tal como estaba."""
    now = now or datetime.now(UTC)
    tenant_id = require_current_tenant()
    if await session.get(KnowledgeDocument, doc_id) is not None:
        raise SourceError("not_removed", 409)
    rows = (
        await session.scalars(
            sa.select(BusinessChange)
            .where(
                BusinessChange.tenant_id == tenant_id,
                BusinessChange.section == "sources",
                BusinessChange.undone_at.is_(None),
                BusinessChange.after["removed"]["id"].astext == str(doc_id),
            )
            .order_by(BusinessChange.at.desc())
            .limit(1)
            .with_for_update()
        )
    ).all()
    if not rows:
        raise SourceError("unknown_source", 404)
    (change,) = rows
    if change.at + RESTORE_WINDOW < now:
        raise SourceError("undo_window_closed", 409)
    snap = _removed_of(change) or {}
    before = await _view(session)
    doc = KnowledgeDocument(
        id=doc_id,
        tenant_id=tenant_id,
        **{name: snap.get(name) for name in _SNAPSHOT_FIELDS},
        indexed_at=datetime.fromisoformat(snap["indexed_at"]) if snap.get("indexed_at") else None,
    )
    if snap.get("created_at"):
        doc.created_at = datetime.fromisoformat(snap["created_at"])
    session.add(doc)
    await session.flush()
    await _write(
        session,
        actor=actor,
        before=before,
        after=await _view(session),
        pointers=[f"/documents/{doc.id}"],
        audit_action="business.section_undone",
        audit_actor=audit_actor,
        kind="undo",
        undo_of=change.id,
    )
    change.undone_at = now
    change.undone_by = actor.id
    await session.flush()
    return doc


# ── el trabajo: leer una fuente (lo llama el manejador ``client_read``) ────────


@dataclass(frozen=True)
class SourceTarget:
    source_id: uuid.UUID
    action: str


async def source_job_target(
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
) -> SourceTarget | None:
    """Si el ``client_read`` es de una fuente, cuál; ``None`` si es la lectura
    de la web y las redes del cliente."""
    from nexus_api.db.base import get_sessionmaker

    sm = sessionmaker or get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        progress = await session.scalar(
            sa.select(Job.progress).where(Job.tenant_id == tenant_id, Job.id == job_id)
        )
    data: dict[str, Any] = dict(progress or {})
    raw = data.get("source_id")
    if not raw:
        return None
    try:
        return SourceTarget(
            source_id=uuid.UUID(str(raw)), action=str(data.get("action") or "index")
        )
    except ValueError:
        return None


class SourceReadFailed(Exception):
    """La fuente no se pudo leer: ``code`` es el motivo que enseña la consola."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


async def _text_of(
    doc: KnowledgeDocument,
    *,
    action: str,
    http: httpx.AsyncClient,
    vision: Vision | None,
) -> tuple[str, str, int, str | None]:
    """``(texto, mime, tamaño, título)`` de la fuente. ``IndexingError`` con su código."""
    from nexus_api.services.media_storage import MediaStorageError, get_media_storage

    if doc.kind == KnowledgeDocumentKind.URL.value and doc.source_url:
        fetched = await indexer.fetch_url(doc.source_url, client=http)
        return (
            fetched.extracted.text,
            fetched.extracted.mime,
            fetched.extracted.size_bytes,
            fetched.title,
        )
    if action == "reread" and doc.content_text and doc.mime not in IMAGE_MIMES:
        return doc.content_text, doc.mime, doc.size_bytes, None
    if not doc.s3_key:
        if doc.content_text:
            return doc.content_text, doc.mime, doc.size_bytes, None
        raise indexer.IndexingError(KnowledgeErrorCode.EMPTY)
    try:
        data, _ctype = await get_media_storage().get_object(doc.s3_key)
    except (MediaStorageError, KeyError, OSError) as exc:
        raise indexer.IndexingError(KnowledgeErrorCode.FETCH_FAILED) from exc
    if len(data) > MAX_UPLOAD_BYTES:
        raise indexer.IndexingError(KnowledgeErrorCode.TOO_LARGE)
    if doc.mime in IMAGE_MIMES:
        if vision is None:
            raise indexer.IndexingError(KnowledgeErrorCode.UNSUPPORTED_TYPE)
        text = indexer.clean_text(await vision(data, doc.mime))
        if not text.strip():
            raise indexer.IndexingError(KnowledgeErrorCode.EMPTY)
        return text[: indexer.MAX_CONTENT_CHARS], doc.mime, len(data), None
    if doc.mime == DOCX_MIME:
        text = docx_text(data)
        if not text.strip():
            raise indexer.IndexingError(KnowledgeErrorCode.EMPTY)
        return text[: indexer.MAX_CONTENT_CHARS], doc.mime, len(data), None
    extracted = indexer.extract_text(data, mime=doc.mime)
    return extracted.text, extracted.mime, extracted.size_bytes, None


async def index_source(
    *,
    tenant_id: uuid.UUID,
    target: SourceTarget,
    http: httpx.AsyncClient,
    extract: Extract,
    vision: Vision | None = None,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, Any]:
    """Lee una fuente, la indexa y propone lo que encuentre (ver el módulo).
    Devuelve el resultado del trabajo (cuentas y códigos, nunca el texto).
    ``SourceReadFailed`` si no se pudo leer."""
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.services.business import reader
    from nexus_api.services.business.profile import business_language

    sm = sessionmaker or get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        doc = await session.get(KnowledgeDocument, target.source_id)
        if doc is None:
            # La quitaron mientras esperaba: no hay nada que leer.
            return {"source_id": str(target.source_id), "status": "gone"}
        profile = await session.get(BusinessProfile, tenant_id)
        country = profile.country if profile else None
        price_currency = profile.price_currency if profile else None
        session.expunge(doc)

    try:
        text, mime, size, title = await _text_of(
            doc, action=target.action, http=http, vision=vision
        )
    except indexer.IndexingError as exc:
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            row = await session.get(KnowledgeDocument, target.source_id)
            if row is not None:
                row.status = KnowledgeDocumentStatus.FAILED.value
                row.error_code = exc.code.value
                row.chunk_count = 0
        raise SourceReadFailed(FAILURE_OF.get(exc.code.value, "unreachable")) from exc

    async with sm() as session, tenant_scoped_session(session, tenant_id):
        row = await session.get(KnowledgeDocument, target.source_id)
        if row is None:
            return {"source_id": str(target.source_id), "status": "gone"}
        row.content_text = text
        row.mime = mime
        row.size_bytes = size
        row.chunk_count = indexer.count_chunks(text)
        row.status = KnowledgeDocumentStatus.INDEXED.value
        row.error_code = None
        row.indexed_at = datetime.now(UTC)
        if title and row.kind == KnowledgeDocumentKind.URL.value and row.title == row.source_url:
            row.title = title[:255]
        await touch_section(session, "sources", actor=READER, state="complete", changed=False)

    is_web = doc.kind == KnowledgeDocumentKind.URL.value
    language = business_language(country)
    page = reader.Page(url=doc.source_url or f"documento:{doc.title}", title=doc.title, text=text)
    found: dict[str, int] = {}
    applied = suggested = 0
    translated: str | None = None
    try:
        raw = await extract(
            reader.build_messages(
                [reader.SourcePage(source="web" if is_web else "document", page=page)],
                language=language,
            )
        )
    except Exception as exc:
        # El texto ya está leído y el agente lo usa; solo no se propone nada.
        log.warning("sources.extract_failed", tenant_id=str(tenant_id), error=type(exc).__name__)
        raw = None
    if raw is not None:
        extraction = reader.parse_extraction(raw, price_currency=price_currency)
        translated = (
            extraction.source_language
            if extraction.source_language and extraction.source_language != language
            else None
        )
        found = extraction.found()
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            outcome = await reader.apply_extraction(
                session,
                extraction,
                source="web" if is_web else "document",
                source_url=doc.source_url,
                translated_from=translated,
            )
        applied, suggested = outcome.applied, outcome.suggested
    log.info(
        "sources.read",
        tenant_id=str(tenant_id),
        source_id=str(target.source_id),
        action=target.action,
        applied=applied,
        suggested=suggested,
    )
    return {
        "source_id": str(target.source_id),
        "status": "read",
        "action": target.action,
        "found": found,
        "applied": applied,
        "suggested": suggested,
        "translated_from": translated,
    }


# ── la lectura de la web y las redes del cliente (la tarjeta del Panel) ───────


def _site_read() -> sa.ColumnElement[bool]:
    """Un ``client_read`` de la web y las redes del cliente, no de una fuente."""
    return cast(sa.ColumnElement[bool], Job.progress["source_id"].astext.is_(None))


async def latest_site_read(session: AsyncSession) -> Job | None:
    """El último ``client_read`` de la web y las redes (no el de una fuente),
    con la caducidad perezosa de ``services/jobs.get_job``."""
    from nexus_api.services import jobs as jobs_service

    job_id = await session.scalar(
        sa.select(Job.id)
        .where(Job.tenant_id == require_current_tenant(), Job.kind == "client_read", _site_read())
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(1)
    )
    return None if job_id is None else await jobs_service.get_job(session, job_id)


async def request_site_read(session: AsyncSession, *, created_by: str | None) -> tuple[Job, bool]:
    """«Volver a leer» la web y las redes: la lectura viva si ya hay una; si no,
    una nueva. ``reader.NothingToRead`` sin web ni redes."""
    from nexus_api.services.business.reader import NothingToRead, readable
    from nexus_api.services.jobs import create_job

    live = await latest_site_read(session)
    if live is not None and live.status in LIVE_JOB_STATUSES:
        return live, False
    site, networks = await readable(session)
    if site is None and not networks:
        raise NothingToRead
    return await create_job(session, kind="client_read", created_by=created_by), True


# ── la pasada semanal (cron ``source_reread_cron``) ────────────────────────────


#: Los clientes que se releen: ni archivados ni en pausa.
_REREAD_STATUSES: Final = (TenantStatus.ACTIVE, TenantStatus.PROVISIONING)


async def _due_in_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, *, now: datetime
) -> list[Job]:
    from nexus_api.services.business.reader import readable
    from nexus_api.services.jobs import create_job

    created: list[Job] = []
    cutoff = now - REREAD_AFTER
    webs = (
        await session.scalars(
            sa.select(KnowledgeDocument).where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.kind == KnowledgeDocumentKind.URL.value,
                KnowledgeDocument.status != KnowledgeDocumentStatus.PENDING.value,
                sa.func.coalesce(KnowledgeDocument.indexed_at, KnowledgeDocument.updated_at)
                < cutoff,
            )
        )
    ).all()
    for doc in webs:
        if await _live_job(session, doc.id) is not None:
            continue
        doc.status = KnowledgeDocumentStatus.PENDING.value
        created.append(await _new_job(session, doc, action="reread", created_by=None))
    # La web y las redes del propio cliente (la lectura del alta), a la semana.
    last = await session.scalar(
        sa.select(Job)
        .where(
            Job.tenant_id == tenant_id,
            Job.kind == "client_read",
            _site_read(),
        )
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    if last is not None and last.status not in LIVE_JOB_STATUSES and last.created_at < cutoff:
        site, networks = await readable(session)
        if site or networks:
            created.append(await create_job(session, kind="client_read", created_by=None))
    return created


async def reread_due(redis: Redis, *, now: datetime | None = None, limit: int = 500) -> int:
    """Una pasada: encola la relectura de las webs leídas hace más de una semana
    (y de la web y las redes de cada cliente). Devuelve cuántas encoló."""
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.services.jobs import enqueue_job

    now = now or datetime.now(UTC)
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        tenant_ids = list(
            (
                await session.scalars(
                    sa.select(Tenant.id)
                    .where(Tenant.status.in_(_REREAD_STATUSES))
                    .order_by(Tenant.id)
                    .limit(limit)
                )
            ).all()
        )
    total = 0
    for tenant_id in tenant_ids:
        try:
            async with sm() as session, tenant_scoped_session(session, tenant_id):
                jobs = await _due_in_tenant(session, tenant_id, now=now)
        except Exception as exc:  # un cliente que falla no para la pasada
            log.warning("sources.reread_failed", tenant_id=str(tenant_id), error=type(exc).__name__)
            continue
        for job in jobs:
            try:
                await enqueue_job(redis, job)
            except Exception as exc:
                log.warning("sources.reread_enqueue_failed", error=type(exc).__name__)
        total += len(jobs)
    if total:
        log.info("sources.reread_due", jobs=total)
    return total


__all__ = [
    "ADDED_ACTION",
    "DOCX_MIME",
    "IMAGE_MIMES",
    "MAX_UPLOAD_BYTES",
    "REMOVED_ACTION",
    "REREAD_ACTION",
    "REREAD_AFTER",
    "RESTORE_WINDOW",
    "Removed",
    "SourceError",
    "SourceReadFailed",
    "SourceTarget",
    "Vision",
    "add_file",
    "add_url",
    "docx_text",
    "failure_of",
    "index_source",
    "latest_site_read",
    "list_sources",
    "remove",
    "removed_sources",
    "request_site_read",
    "reread",
    "reread_due",
    "restore",
    "source_job_target",
    "source_mime",
]
