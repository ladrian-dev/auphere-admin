"""``/console/clients/{ref}/business`` — la ficha entera, su procedencia, su
historial, sus propuestas, sus fuentes y el ClientSpec (spec 047, de la T069 a la T072).

``contracts/console-api.md`` §3. Las secciones con servicio propio (sedes,
horario, fechas especiales, servicios, políticas, preguntas y datos básicos)
tienen sus rutas en ``api/console/business.py``; aquí vive lo que es de toda la
ficha:

- ``GET /``: el ClientSpec, el estado y la revisión de cada sección, la
  procedencia de cada dato (con el nombre de quien lo escribió) y las propuestas
  pendientes;
- ``PUT /links``: la web y las redes, con ``If-Match`` (412 por sección);
- ``POST /sections/{section}/confirm``: «Es correcto» sobre lo leído (13.2);
- ``GET /history`` y ``POST /history/{change_id}/undo`` (13.3);
- ``POST /suggestions/{suggestion_id}/decide`` (5.8, 13.2, 18.2);
- ``GET|POST /sources``, ``POST /sources/{id}/reread|remove|restore`` (12);
- ``GET /export`` y ``POST /import?dry_run=`` (8.3).

Todas pasan por ``client_scope``: el cliente sale del ``{ref}`` del partner del
principal y la transacción lleva su RLS. Las que encolan un trabajo abren su
propia transacción y encolan **después** de confirmarla. Ninguna respuesta lleva
cuerpos de mensaje, teléfonos de clientes finales ni costes.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import sqlalchemy as sa
import structlog
from fastapi import (
    APIRouter,
    Body,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile as StarletteUploadFile

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import KnowledgeDocument, Tenant
from nexus_api.db.models.business import SECTIONS, BusinessSection
from nexus_api.services import console_v2
from nexus_api.services.business import client_spec, history, provenance, sources, suggestions
from nexus_api.services.business.profile_edits import InvalidField, NoBusinessProfile, put_links
from nexus_api.services.business.sections import INITIAL_STATES, Actor
from nexus_api.services.business.writes import (
    SectionRevisionConflict,
    WriteContext,
    current_revision,
)
from nexus_api.services.jobs import enqueue_job

from .agent_draft_routes import etag, parse_revision
from .deps import ClientRef, ClientScope, client_scope, resolve_mapping
from .schemas_business_records import (
    BusinessRecordOut,
    ChangeOut,
    ConfirmOut,
    DecideIn,
    DecideOut,
    HistoryOut,
    ImportOpOut,
    ImportOut,
    LinkOut,
    LinksIn,
    LinksOut,
    PersonOut,
    ProblemOut,
    ProvenanceOut,
    RemovedSourceOut,
    SectionOut,
    SourceAcceptedOut,
    SourceOut,
    SourceRemovedOut,
    SourcesOut,
    SourceUrlIn,
    SuggestionOut,
    UndoOut,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/clients/{ref}/business")

_WRITE = "clients:write"
_READ = "clients:read"


def _actor(principal: ConsolePrincipal) -> Actor:
    return Actor(kind="partner_member", id=principal.user_id, origin="console")


def _error(code: int, name: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=code, detail={"code": name, **extra})


def _expected(if_match: str | None, principal: ConsolePrincipal) -> int | None:
    """La revisión leída. La consola nueva siempre la manda; sin ella, ``428``."""
    revision = parse_revision(if_match)
    if revision is None and console_v2.console_version(principal.partner) == "v2":
        raise _error(status.HTTP_428_PRECONDITION_REQUIRED, "revision_required")
    return revision


async def _conflict(session: AsyncSession, exc: SectionRevisionConflict) -> HTTPException:
    value = await client_spec.section_view(session, exc.section)
    return HTTPException(
        status_code=status.HTTP_412_PRECONDITION_FAILED,
        detail={
            "code": "revision_conflict",
            "section": exc.section,
            "current": exc.current,
            "value": json.loads(json.dumps(value, default=str)),
            "changes": [_public_change(exc.section, c) for c in exc.changes],
        },
        headers={"ETag": etag(exc.current)},
    )


def _public_change(section: str, change: dict[str, Any]) -> dict[str, Any]:
    out = dict(change)
    if section == "sources":
        for key in ("before", "after"):
            if isinstance(out.get(key), dict):
                out[key] = {k: v for k, v in out[key].items() if k != "removed"}
    return out


def _allowed(principal: ConsolePrincipal) -> list[Any]:
    return ["edit", "import", "undo", "decide"] if _WRITE in principal.permissions else []


async def _ensure_profile(session: AsyncSession) -> None:
    """La ficha de un cliente de antes de la 047 nace la primera vez que se
    abre, marcada «Migrado» (``hours.ensure_profile``)."""
    try:
        from nexus_api.services.business.hours import ensure_profile
    except ImportError:  # pragma: no cover - el servicio de horario es de esta ola
        return
    await ensure_profile(session)


@asynccontextmanager
async def _scoped(
    session: AsyncSession, principal: ConsolePrincipal, ref: str
) -> AsyncIterator[ClientScope]:
    """``client_scope`` a mano, para las rutas que encolan tras confirmar."""
    mapping = await resolve_mapping(session, principal, ref)
    async with tenant_scoped_session(session, mapping.tenant_id):
        tenant = await session.get(Tenant, mapping.tenant_id)
        assert tenant is not None  # la FK lo garantiza
        yield ClientScope(principal=principal, mapping=mapping, tenant=tenant, session=session)


# ── la ficha entera ────────────────────────────────────────────────────────────


@router.get("", response_model=BusinessRecordOut)
async def get_business(
    response: Response, scope: ClientScope = Depends(client_scope(_READ))
) -> BusinessRecordOut:
    session = scope.session
    await _ensure_profile(session)
    try:
        spec = await client_spec.export_document(session, provenance=False)
    except LookupError as exc:
        raise _error(status.HTTP_404_NOT_FOUND, "no_business_profile") from exc
    _parsed, problems = client_spec.validate_document(spec)
    prov = await provenance.provenance_map(session, partner_id=scope.principal.partner.id)
    rows = {
        r.section: r
        for r in (
            await session.scalars(
                sa.select(BusinessSection).where(BusinessSection.tenant_id == scope.tenant.id)
            )
        ).all()
    }
    names = await provenance.people_names(
        scope.principal.partner.id,
        scope.tenant.id,
        [(r.updated_by_kind, r.updated_by_id) for r in rows.values()],
    )
    open_suggestions = await suggestions.pending(session)
    per_section: dict[str, int] = {}
    suggestion_out: list[SuggestionOut] = []
    for s in open_suggestions:
        section = suggestions.section_of(s.pointer)
        per_section[section] = per_section.get(section, 0) + 1
        suggestion_out.append(
            SuggestionOut(
                id=s.id,
                pointer=s.pointer,
                section=section,  # type: ignore[arg-type]
                proposed_value=s.proposed_value,
                current_value=s.current_value,
                source=s.source,  # type: ignore[arg-type]
                source_url=s.source_url,
                translated_from=s.translated_from,
                created_at=s.created_at,
            )
        )
    sections: list[SectionOut] = []
    for name in SECTIONS:
        row = rows.get(name)
        who = provenance.person(
            row.updated_by_kind if row else None, row.updated_by_id if row else None, names
        )
        sections.append(
            SectionOut(
                section=name,  # type: ignore[arg-type]
                state=(row.state if row else INITIAL_STATES[name]),  # type: ignore[arg-type]
                revision=row.revision if row else 0,
                updated_at=row.updated_at if row else None,
                updated_by=PersonOut(kind=who.kind, id=who.id, name=who.name) if who else None,  # type: ignore[arg-type]
                origin=row.updated_origin if row else None,  # type: ignore[arg-type]
                pending_suggestions=per_section.get(name, 0),
            )
        )
    response.headers["Cache-Control"] = "no-store"
    return BusinessRecordOut(
        spec=spec,
        valid=not problems,
        problems=[ProblemOut(pointer=p.pointer, code=p.code) for p in problems],
        sections=sections,
        provenance={
            pointer: ProvenanceOut(
                source=entry["source"],
                by=PersonOut(kind=entry["by"].kind, id=entry["by"].id, name=entry["by"].name)
                if entry.get("by")
                else None,
                origin=entry["origin"],
                at=entry["at"],
                source_url=entry.get("source_url"),
                translated_from=entry.get("translated_from"),
                review=entry["review"],
            )
            for pointer, entry in prov.items()
        },
        suggestions=suggestion_out,
        allowed=_allowed(scope.principal),
    )


# ── la web y las redes ─────────────────────────────────────────────────────────


@router.put(
    "/links",
    response_model=LinksOut,
    responses={
        412: {"description": "revision_conflict"},
        422: {"description": "invalid_link"},
        428: {"description": "revision_required"},
    },
)
async def update_links(
    body: LinksIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(client_scope(_WRITE)),
) -> LinksOut:
    """Requisito 12.4: la lista entera, con su enlace y su usuario."""
    expected = _expected(if_match, scope.principal)
    await _ensure_profile(scope.session)
    try:
        await put_links(
            scope.session,
            [link.model_dump() for link in body.links],
            actor=_actor(scope.principal),
            expected_revision=expected,
            audit_actor=scope.principal.actor,
        )
    except SectionRevisionConflict as exc:
        raise await _conflict(scope.session, exc) from exc
    except InvalidField as exc:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, exc.code, field=exc.field) from exc
    except NoBusinessProfile as exc:
        raise _error(status.HTTP_404_NOT_FOUND, "no_business_profile") from exc
    revision = await current_revision(scope.session, "links")
    links = (await client_spec.section_view(scope.session, "links"))["links"]
    response.headers["ETag"] = etag(revision)
    return LinksOut(links=[LinkOut(**link) for link in links], revision=revision)


# ── «Es correcto» ──────────────────────────────────────────────────────────────


@router.post("/sections/{section}/confirm", response_model=ConfirmOut)
async def confirm_section(
    section: str, scope: ClientScope = Depends(client_scope(_WRITE))
) -> ConfirmOut:
    """Requisito 13.2: lo leído de la sección pasa a escrito por quien confirma."""
    if section not in SECTIONS:
        raise _error(status.HTTP_404_NOT_FOUND, "unknown_section")
    confirmed = await provenance.confirm_section(
        scope.session, section, actor=_actor(scope.principal)
    )
    row = await scope.session.get(BusinessSection, (scope.tenant.id, section))
    return ConfirmOut(
        section=section,  # type: ignore[arg-type]
        state=(row.state if row else INITIAL_STATES[section]),  # type: ignore[arg-type]
        revision=row.revision if row else 0,
        confirmed=confirmed,
    )


# ── historial y deshacer ───────────────────────────────────────────────────────


@router.get("/history", response_model=HistoryOut)
async def get_history(
    section: str | None = Query(default=None, max_length=16),
    limit: int = Query(default=50, ge=1, le=200),
    scope: ClientScope = Depends(client_scope(_READ)),
) -> HistoryOut:
    if section is not None and section not in SECTIONS:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown_section")
    views = await history.list_history(scope.session, section=section, limit=limit)
    names = await provenance.people_names(
        scope.principal.partner.id,
        scope.tenant.id,
        [(v.row.actor_kind, v.row.actor_id) for v in views],
    )
    items: list[ChangeOut] = []
    for v in views:
        row = v.row
        who = provenance.person(row.actor_kind, row.actor_id, names)
        public = _public_change(row.section, {"before": row.before, "after": row.after})
        items.append(
            ChangeOut(
                id=row.id,
                section=row.section,  # type: ignore[arg-type]
                kind=row.kind,  # type: ignore[arg-type]
                at=row.at,
                by=PersonOut(kind=who.kind, id=who.id, name=who.name) if who else None,  # type: ignore[arg-type]
                origin=row.origin,  # type: ignore[arg-type]
                before=public["before"],
                after=public["after"],
                undone_at=row.undone_at,
                undo_of=row.undo_of,
                undoable=v.undoable,
            )
        )
    return HistoryOut(items=items)


@router.post(
    "/history/{change_id}/undo",
    response_model=UndoOut,
    responses={409: {"description": "already_undone | undo_not_available"}, 412: {}},
)
async def undo_change(
    change_id: uuid.UUID, scope: ClientScope = Depends(client_scope(_WRITE))
) -> UndoOut:
    """Requisito 13.3: deshacer el último cambio de una sección."""
    try:
        written = await history.undo(
            scope.session,
            change_id,
            ctx=WriteContext(actor=_actor(scope.principal), audit_actor=scope.principal.actor),
        )
    except LookupError as exc:
        raise _error(status.HTTP_404_NOT_FOUND, "unknown_change") from exc
    except history.AlreadyUndone as exc:
        raise _error(status.HTTP_409_CONFLICT, "already_undone") from exc
    except history.UndoNotAvailable as exc:
        raise _error(status.HTTP_409_CONFLICT, "undo_not_available") from exc
    except SectionRevisionConflict as exc:
        raise await _conflict(scope.session, exc) from exc
    except InvalidField as exc:
        raise _error(status.HTTP_409_CONFLICT, "undo_not_available", field=exc.field) from exc
    if written is None:
        section = await scope.session.scalar(
            sa.text("SELECT section FROM business_changes WHERE id = :id"), {"id": change_id}
        )
        return UndoOut(section=section)
    return UndoOut(section=written.section, revision=written.revision, change_id=written.change_id)  # type: ignore[arg-type]


# ── propuestas ─────────────────────────────────────────────────────────────────


@router.post(
    "/suggestions/{suggestion_id}/decide",
    response_model=DecideOut,
    responses={409: {"description": "already_decided"}, 422: {"description": "invalid_value"}},
)
async def decide_suggestion(
    suggestion_id: uuid.UUID,
    body: DecideIn,
    scope: ClientScope = Depends(client_scope(_WRITE)),
) -> DecideOut:
    """Aceptar, editar o descartar un dato leído o sugerido."""
    try:
        decided = await suggestions.decide(
            scope.session,
            suggestion_id,
            body.decision,
            actor=_actor(scope.principal),
            value=body.value,
            audit_actor=scope.principal.actor,
        )
    except LookupError as exc:
        raise _error(status.HTTP_404_NOT_FOUND, "unknown_suggestion") from exc
    except suggestions.AlreadyDecided as exc:
        raise _error(status.HTTP_409_CONFLICT, "already_decided") from exc
    except suggestions.InvalidValue as exc:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_value",
            problems=client_spec.problems_out(exc.problems),
        ) from exc
    except suggestions.SectionNotWritable as exc:
        raise _error(status.HTTP_409_CONFLICT, "section_not_writable", section=exc.section) from exc
    except InvalidField as exc:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_value", field=exc.field
        ) from exc
    except SectionRevisionConflict as exc:
        raise await _conflict(scope.session, exc) from exc
    return DecideOut(
        suggestion_id=decided.suggestion_id,
        decision=decided.decision,  # type: ignore[arg-type]
        section=decided.section,  # type: ignore[arg-type]
        revision=decided.written.revision if decided.written else None,
    )


# ── documentos y webs ──────────────────────────────────────────────────────────


def _source_out(doc: KnowledgeDocument) -> SourceOut:
    return SourceOut(
        id=doc.id,
        kind="file" if doc.kind == "file" else "web",
        title=doc.title,
        url=doc.source_url,
        status=client_spec.document_status(doc.status),  # type: ignore[arg-type]
        failure=sources.failure_of(doc),  # type: ignore[arg-type]
        size_bytes=int(doc.size_bytes or 0),
        read_at=doc.indexed_at if doc.status == "indexed" else None,
        created_at=doc.created_at,
    )


def _source_error(exc: sources.SourceError) -> HTTPException:
    return _error(exc.status, exc.code)


@router.get("/sources", response_model=SourcesOut)
async def list_sources(scope: ClientScope = Depends(client_scope(_READ))) -> SourcesOut:
    docs = await sources.list_sources(scope.session)
    removed = await sources.removed_sources(scope.session)
    allowed: list[Any] = (
        ["add", "remove", "reread"] if _WRITE in scope.principal.permissions else []
    )
    return SourcesOut(
        items=[_source_out(d) for d in docs],
        removed=[
            RemovedSourceOut(
                id=r.id,
                kind="file" if r.kind == "file" else "web",
                title=r.title,
                restore_until=r.restore_until,
            )
            for r in removed
        ],
        max_bytes=sources.MAX_UPLOAD_BYTES,
        allowed=allowed,
    )


@router.post(
    "/sources",
    response_model=SourceAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        413: {"description": "too_large: más de 10 MB"},
        415: {"description": "unsupported_type"},
        422: {"description": "invalid_url"},
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "file": {"type": "string", "format": "binary"},
                            "title": {"type": "string", "maxLength": 255},
                        },
                        "required": ["file"],
                    }
                },
                "application/json": {"schema": SourceUrlIn.model_json_schema()},
            }
        }
    },
)
async def add_source(
    request: Request,
    ref: str = ClientRef,
    principal: ConsolePrincipal = Depends(require_console_principal(_WRITE)),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> SourceAcceptedOut:
    """Requisito 12.1: un archivo (multipart, hasta 10 MB) o una web (``{url}``).
    Responde «Leyendo» y la lee el trabajo."""
    mapping = await resolve_mapping(session, principal, ref)
    ctype = request.headers.get("content-type", "")
    upload: StarletteUploadFile | None = None
    title: str | None = None
    url_body: SourceUrlIn | None = None
    if ctype.startswith("multipart/form-data"):
        form = await request.form(max_files=1, max_fields=4)
        raw_file = form.get("file")
        if not isinstance(raw_file, StarletteUploadFile):
            raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "file_required")
        upload = raw_file
        raw_title = form.get("title")
        title = raw_title if isinstance(raw_title, str) else None
    else:
        try:
            url_body = SourceUrlIn.model_validate(await request.json())
        except (ValidationError, ValueError) as exc:
            raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_url") from exc
    data = await upload.read(sources.MAX_UPLOAD_BYTES + 1) if upload is not None else b""
    try:
        async with tenant_scoped_session(session, mapping.tenant_id):
            tenant = await session.get(Tenant, mapping.tenant_id)
            assert tenant is not None
            await _ensure_profile(session)
            if upload is not None:
                doc, job = await sources.add_file(
                    session,
                    filename=(title or upload.filename or "documento"),
                    declared_type=upload.content_type,
                    data=data,
                    tenant_slug=tenant.slug,
                    actor=_actor(principal),
                    audit_actor=principal.actor,
                    created_by=principal.user_id,
                )
            else:
                assert url_body is not None
                doc, job = await sources.add_url(
                    session,
                    url=url_body.url,
                    title=url_body.title,
                    actor=_actor(principal),
                    audit_actor=principal.actor,
                    created_by=principal.user_id,
                )
            out = SourceAcceptedOut(source=_source_out(doc), job_id=job.id)
    except sources.SourceError as exc:
        raise _source_error(exc) from exc
    await _enqueue(redis, job)
    return out


async def _enqueue(redis: Redis, job: Any) -> None:
    try:
        await enqueue_job(redis, job)
    except Exception as exc:
        # La fila es la verdad: un trabajo que nadie oyó caduca y se relee.
        log.warning("console.business.source_enqueue_failed", error=type(exc).__name__)


@router.post(
    "/sources/{source_id}/reread",
    response_model=SourceAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reread_source(
    source_id: uuid.UUID,
    ref: str = ClientRef,
    principal: ConsolePrincipal = Depends(require_console_principal(_WRITE)),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> SourceAcceptedOut:
    """«Volver a leer» (12.3): los cambios llegan como propuestas."""
    try:
        async with _scoped(session, principal, ref):
            doc, job, created = await sources.reread(
                session,
                source_id,
                actor=_actor(principal),
                audit_actor=principal.actor,
                created_by=principal.user_id,
            )
            out = SourceAcceptedOut(source=_source_out(doc), job_id=job.id)
    except sources.SourceError as exc:
        raise _source_error(exc) from exc
    if created:
        await _enqueue(redis, job)
    return out


@router.post("/sources/{source_id}/remove", response_model=SourceRemovedOut)
async def remove_source(
    source_id: uuid.UUID, scope: ClientScope = Depends(client_scope(_WRITE))
) -> SourceRemovedOut:
    """Requisito 12.2: deja de usarse desde el siguiente mensaje; 10 min para deshacer."""
    try:
        until = await sources.remove(
            scope.session,
            source_id,
            actor=_actor(scope.principal),
            audit_actor=scope.principal.actor,
        )
    except sources.SourceError as exc:
        raise _source_error(exc) from exc
    return SourceRemovedOut(id=source_id, restore_until=until)


@router.post("/sources/{source_id}/restore", response_model=SourceOut)
async def restore_source(
    source_id: uuid.UUID, scope: ClientScope = Depends(client_scope(_WRITE))
) -> SourceOut:
    try:
        doc = await sources.restore(
            scope.session,
            source_id,
            actor=_actor(scope.principal),
            audit_actor=scope.principal.actor,
        )
    except sources.SourceError as exc:
        raise _source_error(exc) from exc
    return _source_out(doc)


# ── el ClientSpec ──────────────────────────────────────────────────────────────


@router.get("/export", response_class=JSONResponse)
async def export_spec(scope: ClientScope = Depends(client_scope(_READ))) -> JSONResponse:
    """El ClientSpec v1 (``client-spec.schema.json``), con su procedencia."""
    await _ensure_profile(scope.session)
    try:
        doc = await client_spec.export_document(scope.session)
    except LookupError as exc:
        raise _error(status.HTTP_404_NOT_FOUND, "no_business_profile") from exc
    return JSONResponse(
        content=json.loads(json.dumps(doc, default=str)),
        headers={
            "Content-Disposition": f'attachment; filename="{scope.ref}-clientspec.json"',
            "Cache-Control": "no-store",
        },
    )


@router.post(
    "/import",
    response_model=ImportOut,
    responses={422: {"description": "invalid_document"}},
)
async def import_spec(
    document: dict[str, Any] = Body(...),
    dry_run: bool = Query(default=False),
    scope: ClientScope = Depends(client_scope(_WRITE)),
) -> ImportOut:
    """Importar **no escribe nada**: cada cambio queda como propuesta pendiente
    de una persona. Con ``dry_run``, solo lo que propondría."""
    await _ensure_profile(scope.session)
    try:
        proposal = await suggestions.propose_import(scope.session, document, dry_run=dry_run)
    except LookupError as exc:
        raise _error(status.HTTP_404_NOT_FOUND, "no_business_profile") from exc
    if proposal.problems:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_document",
            problems=client_spec.problems_out(proposal.problems),
        )
    return ImportOut(
        dry_run=dry_run,
        base_hash=proposal.base_hash,
        ops=[
            ImportOpOut(op=o["op"], path=o["path"], value=o["value"], current=o["current"])
            for o in proposal.ops
        ],
        problems=[],
        created=proposal.created,
    )


__all__ = ["router"]
