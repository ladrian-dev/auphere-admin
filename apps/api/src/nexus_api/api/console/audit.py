"""``/console/audit`` — the partner's audit trail (CP-28 backend).

Rows from ``audit_log`` that belong to the partner: every row of any of
its clients (``tenant_id IN partner_tenants``) plus the platform-level
rows the console itself writes about the partner (team, keys, alerts —
written with ``tenant_id NULL`` and ``target = partner:<id>``). Nothing
else can match: the filter is built from the principal, not from input.

Each row is rendered into a one-line human summary in the requested
language (``?lang=es|en``) from ``console_audit_vocabulary`` (migration
0084) — cached in-process for :data:`VOCAB_TTL_S`; an action without
vocabulary falls back to "{actor} · {action} · {target}". The raw payloads
(``before``/``after``) stay inside.

``audit_log`` is RLS-forced per tenant, so the cross-client read runs
under the reporting role (``services/console_reporting.py``); the tenant
filter is the boundary. ``GET /audit/export.csv`` streams the same query.
"""

from __future__ import annotations

import base64
import csv
import io
import re
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.db.models import AuditLog, PartnerMembership, PartnerTenant
from nexus_api.services.console_reporting import csv_safe, partner_mappings, reporting_transaction

from .schemas import AuditEntryOut, AuditPageOut
from .schemas_home_usage import AuditVocabularyEntryOut, AuditVocabularyOut

router = APIRouter(prefix="/audit")

VOCAB_TTL_S = 300.0
_LANGS = ("es", "en")


@dataclass(frozen=True)
class VocabEntry:
    action: str
    category: str
    severity: str
    summary_es: str
    summary_en: str

    def summary(self, lang: str) -> str:
        return self.summary_es if lang == "es" else self.summary_en


_vocab_cache: dict[str, VocabEntry] | None = None
_vocab_at: float = 0.0


async def load_vocabulary(session: AsyncSession, *, force: bool = False) -> dict[str, VocabEntry]:
    """``console_audit_vocabulary`` → in-process cache (per replica)."""
    global _vocab_cache, _vocab_at
    now = time.monotonic()
    if not force and _vocab_cache is not None and now - _vocab_at < VOCAB_TTL_S:
        return _vocab_cache
    async with session.begin():
        rows = (
            await session.execute(
                sa.text(
                    "SELECT action, category, severity, summary_es, summary_en "
                    "FROM console_audit_vocabulary"
                )
            )
        ).all()
    _vocab_cache = {
        r[0]: VocabEntry(
            action=r[0], category=r[1], severity=r[2], summary_es=r[3], summary_en=r[4]
        )
        for r in rows
    }
    _vocab_at = time.monotonic()
    return _vocab_cache


def reset_vocabulary_cache_for_tests() -> None:
    global _vocab_cache, _vocab_at
    _vocab_cache = None
    _vocab_at = 0.0


def _encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()}|{row_id}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts, rid = raw.split("|", 1)
        return datetime.fromisoformat(ts), uuid.UUID(rid)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid cursor"
        ) from None


COMPANION_ACTOR = "Companion"

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)


def _human_document(after: dict[str, Any], before: dict[str, Any], *, lang: str) -> str:
    """QA-21: knowledge rows must not show a raw uuid as the document name."""
    raw = after.get("filename") or after.get("title") or before.get("filename") or after.get("document_id")
    if raw is None or _UUID_RE.match(str(raw).strip()):
        return "un documento" if lang == "es" else "a document"
    return str(raw)


async def partner_member_emails(session: AsyncSession, partner_id: uuid.UUID) -> dict[str, str]:
    """``user_id`` → correo, **solo del partner del llamante** (cabo 3).

    Una consulta por petición, no una por fila: el equipo de un partner es
    pequeño y acotado, así que traerlo entero es más barato que resolver
    uno a uno y evita el N+1 en la exportación en flujo.

    Por qué por membresía y no por ``companion.actions.decided_by``, que es
    lo que decía §12 de ``CONTRACT-V2.md``: esa tabla tiene **RLS por
    principal**, así que una consulta desde la sesión de quien mira la
    auditoría solo vería sus PROPIAS acciones — y la escritura que hizo el
    Companion de un compañero se seguiría pintando *Companion* a secas, que
    es justo lo que el cabo pide arreglar. Resolver contra
    ``partner_memberships`` cumple la intención y la restricción: por
    construcción no puede devolver el correo de otro partner.
    """
    # Transacción propia y corta, como ``partner_mappings`` y
    # ``load_vocabulary``: sin ella la sesión queda con una transacción
    # implícita abierta y ``reporting_transaction`` no puede abrir la suya.
    async with session.begin():
        rows = (
            await session.execute(
                sa.select(PartnerMembership.user_id, PartnerMembership.email).where(
                    PartnerMembership.partner_id == partner_id
                )
            )
        ).all()
    return {str(user_id): str(email) for user_id, email in rows if email}


def _human_actor(actor: str, emails: dict[str, str] | None = None) -> str:
    # ``console:maria@x.com`` → ``maria@x.com``; ``admin:1a2b3c4d`` → ``Auphere``.
    if actor.startswith("console:"):
        return actor.removeprefix("console:")
    if actor.startswith("companion:"):
        # El Companion escribe como ``companion:<user_id>`` (CONTRACT-V1 §10.1):
        # el identificador, y no el correo, porque quien lo fija es el ejecutor
        # de herramientas y ahí no hay membresía cargada.
        #
        # Aquí sí la hay, así que se resuelve (cabo 3 de la Ola 2): "Companion
        # · maria@facelad.com" dice qué pasó Y quién lo autorizó, que son dos
        # datos distintos y los dos hacen falta. Sin resolución posible —un
        # miembro que ya no está— cae a *Companion* a secas, **nunca al uuid
        # crudo**: un identificador en una página de auditoría no le dice nada
        # a nadie y solo ensucia la línea.
        user_id = actor.removeprefix("companion:")
        email = (emails or {}).get(user_id)
        return f"{COMPANION_ACTOR} · {email}" if email else COMPANION_ACTOR
    if actor.startswith("admin:"):
        return "Auphere"
    if actor.startswith("partner:"):
        return "API key"
    return actor


class _Safe(dict[str, Any]):
    """``str.format_map`` helper: an unknown placeholder renders as ``?``
    instead of raising, so a vocabulary typo never 500s the page."""

    def __missing__(self, key: str) -> str:
        return "?"


def summarise(
    row: AuditLog,
    client_name: str | None,
    vocab: dict[str, VocabEntry],
    lang: str = "en",
    emails: dict[str, str] | None = None,
) -> str:
    after = row.after_json or {}
    before = row.before_json or {}
    values = _Safe(
        actor=_human_actor(row.actor, emails),
        client=client_name or ("un cliente" if lang == "es" else "a client"),
        v=after.get("version", before.get("version", "?")),
        status=after.get("status", "?"),
        email=after.get("email", before.get("email", "?")),
        role=after.get("role", "?"),
        key=after.get("prefix_snippet", before.get("prefix_snippet", "?")),
        channel=after.get("channel", after.get("provider_identifier", before.get("channel", "?"))),
        template=after.get("name", after.get("template", before.get("name", "?"))),
        document=_human_document(after, before, lang=lang),
        cap=after.get("cap", "?"),
        percent=after.get("percent", "?"),
        # CO-08: los tickets de soporte. ``_Safe`` pinta ``?`` para un
        # marcador que no exista, así que añadirlos aquí no puede romper
        # ninguna plantilla anterior.
        ticket=after.get("ticket_ref", "?"),
        topic=after.get("topic", "?"),
    )
    entry = vocab.get(row.action)
    if entry is None:
        target = row.target or ""
        if _UUID_RE.search(target):
            target = str(values["client"])
        return f"{values['actor']} · {row.action} · {target}"
    return entry.summary(lang).format_map(values)


def _scope_filter(
    partner_id: uuid.UUID, mappings: list[PartnerTenant], client: str | None
) -> sa.ColumnElement[bool]:
    """El ámbito de la consulta. Un ``client`` que no sea del partner da 404.

    Antes devolvía la lista vacía con un 200, y para la interfaz daba igual
    —el cliente se elige de una lista, así que el ref siempre existe—; para
    el Companion no, porque el modelo SÍ puede inventarse una referencia, y
    una lista vacía con 200 le deja decir "ese cliente no tiene actividad"
    sobre algo que no existe. Eso es una afirmación falsa **con respaldo**,
    así que R1 no la marca: es peor que una alucinación, porque parece
    verificada. Es exactamente el mismo razonamiento —y el mismo arreglo—
    que en ``usage.py:_scope``.

    Sigue siendo opaco: el ref de otro partner y el inexistente dan el
    **mismo** 404, porque ninguno de los dos está en ``mappings``.
    """
    tenant_ids = [m.tenant_id for m in mappings]
    if client is not None:
        chosen = [m.tenant_id for m in mappings if m.external_client_ref == client]
        if not chosen:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown client")
        return AuditLog.tenant_id.in_(chosen)
    return sa.or_(
        AuditLog.tenant_id.in_(tenant_ids),
        sa.and_(AuditLog.tenant_id.is_(None), AuditLog.target == f"partner:{partner_id}"),
    )


def _base_stmt(
    scope: sa.ColumnElement[bool],
    *,
    actor: str | None,
    action: str | None,
    after: datetime | None,
    before: datetime | None,
) -> sa.Select[tuple[AuditLog]]:
    stmt = sa.select(AuditLog).where(scope)
    if actor:
        stmt = stmt.where(AuditLog.actor.ilike(f"%{actor}%"))
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    if after is not None:
        stmt = stmt.where(AuditLog.created_at >= after)
    if before is not None:
        stmt = stmt.where(AuditLog.created_at < before)
    return stmt


@router.get("/vocabulary", response_model=AuditVocabularyOut)
async def audit_vocabulary(
    _principal: ConsolePrincipal = Depends(require_console_principal("audit:read")),
    session: AsyncSession = Depends(get_db_session),
    lang: str = Query(default="en", pattern="^(es|en)$"),
) -> AuditVocabularyOut:
    vocab = await load_vocabulary(session)
    return AuditVocabularyOut(
        lang=lang,
        entries=[
            AuditVocabularyEntryOut(
                action=v.action, category=v.category, severity=v.severity, summary=v.summary(lang)
            )
            for v in sorted(vocab.values(), key=lambda v: (v.category, v.action))
        ],
    )


@router.get("", response_model=AuditPageOut)
async def list_audit(
    principal: ConsolePrincipal = Depends(require_console_principal("audit:read")),
    session: AsyncSession = Depends(get_db_session),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    actor: str | None = Query(default=None, max_length=255, description="Substring match"),
    action: str | None = Query(default=None, max_length=80, description="Prefix match"),
    client: str | None = Query(default=None, max_length=255, description="external_client_ref"),
    after: datetime | None = Query(default=None),
    before: datetime | None = Query(default=None),
    lang: str = Query(default="en", pattern="^(es|en)$"),
) -> AuditPageOut:
    partner_id = principal.partner.id
    mappings = await partner_mappings(session, partner_id)
    by_tenant = {m.tenant_id: m for m in mappings}
    vocab = await load_vocabulary(session)
    emails = await partner_member_emails(session, partner_id)
    stmt = _base_stmt(
        _scope_filter(partner_id, mappings, client),
        actor=actor,
        action=action,
        after=after,
        before=before,
    )
    if cursor:
        c_ts, c_id = _decode_cursor(cursor)
        stmt = stmt.where(
            sa.or_(
                AuditLog.created_at < c_ts,
                sa.and_(AuditLog.created_at == c_ts, AuditLog.id < c_id),
            )
        )
    async with reporting_transaction(session):
        rows = (
            (
                await session.execute(
                    stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit + 1)
                )
            )
            .scalars()
            .all()
        )

    has_more = len(rows) > limit
    rows = rows[:limit]
    items: list[AuditEntryOut] = []
    for row in rows:
        mapping = by_tenant.get(row.tenant_id) if row.tenant_id else None
        client_name = mapping.client_name if mapping else None
        items.append(
            AuditEntryOut(
                id=row.id,
                at=row.created_at,
                actor=_human_actor(row.actor, emails),
                action=row.action,
                target=row.target,
                external_client_ref=mapping.external_client_ref if mapping else None,
                client_name=client_name,
                summary=summarise(row, client_name, vocab, lang, emails),
            )
        )
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None
    return AuditPageOut(items=items, next_cursor=next_cursor)


_CSV_HEADERS: dict[str, list[str]] = {
    "en": ["at", "actor", "action", "client_ref", "client_name", "target", "summary"],
    "es": ["fecha", "actor", "accion", "ref_cliente", "cliente", "objetivo", "resumen"],
}


@router.get("/export.csv", response_class=StreamingResponse)
async def export_audit_csv(
    principal: ConsolePrincipal = Depends(require_console_principal("audit:read")),
    session: AsyncSession = Depends(get_db_session),
    actor: str | None = Query(default=None, max_length=255),
    action: str | None = Query(default=None, max_length=80),
    client: str | None = Query(default=None, max_length=255),
    after: datetime | None = Query(default=None),
    before: datetime | None = Query(default=None),
    lang: str = Query(default="en", pattern="^(es|en)$"),
    limit: int = Query(default=10_000, ge=1, le=100_000),
) -> StreamingResponse:
    partner_id = principal.partner.id
    mappings = await partner_mappings(session, partner_id)
    by_tenant = {m.tenant_id: m for m in mappings}
    vocab = await load_vocabulary(session)
    # Se carga ENTERO antes de abrir el flujo: dentro del generador no hay
    # sesión libre para una consulta más, y resolver fila a fila sería un
    # N+1 sobre una exportación de hasta cien mil filas.
    emails = await partner_member_emails(session, partner_id)
    stmt = (
        _base_stmt(
            _scope_filter(partner_id, mappings, client),
            actor=actor,
            action=action,
            after=after,
            before=before,
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
    )

    async def _rows() -> AsyncIterator[bytes]:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(_CSV_HEADERS[lang])
        yield buf.getvalue().encode("utf-8-sig")
        buf.seek(0)
        buf.truncate()
        async with reporting_transaction(session):
            result = await session.stream_scalars(stmt.execution_options(yield_per=500))
            async for row in result:
                mapping = by_tenant.get(row.tenant_id) if row.tenant_id else None
                client_name = mapping.client_name if mapping else None
                writer.writerow(
                    [
                        csv_safe(v)
                        for v in [
                            row.created_at.isoformat(),
                            _human_actor(row.actor, emails),
                            row.action,
                            mapping.external_client_ref if mapping else "",
                            client_name or "",
                            row.target,
                            summarise(row, client_name, vocab, lang, emails),
                        ]
                    ]
                )
                yield buf.getvalue().encode("utf-8")
                buf.seek(0)
                buf.truncate()

    return StreamingResponse(
        _rows(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="audit-{lang}.csv"'},
    )
