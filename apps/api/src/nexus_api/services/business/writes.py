"""La única vía para escribir una sección de la ficha — spec 047, ola 2.

Toda escritura de la ficha (una persona desde la consola, la lite o la app; el
admin; la lectura de la web; el constructor por propuesta; una corrección desde la
Bandeja) pasa por ``write_section`` dentro de la transacción del llamante, con el
cliente puesto. Así nadie se salta ninguna de las cosas que la spec pide de cada
cambio:

1. **Concurrencia por sección** (requisito 13.4): si llega ``expected_revision`` y
   la sección va por otra, ``SectionRevisionConflict`` con lo que cambió desde
   entonces. La ruta lo responde como ``412`` (``{code: "revision_conflict",
   current, changes}``, como el borrador del agente).
2. **Historial** (requisito 13.3): una fila de ``business_changes`` con ``before``
   y ``after``, el autor y el origen. Deshacer vive en ``history.py``.
3. **Procedencia** (requisito 13.1): los punteros escritos quedan con su fuente y
   su autor (``set_provenance``).
4. **Revisión**: la de la sección y ``content_rev`` de la ficha.
5. **El agente usa el dato nuevo desde el siguiente mensaje** (requisito 8.4,
   research D4): ``compilation.recompile_active_versions``.
6. **Quién edita** (requisito 13.5): el constructor nunca escribe directamente
   (solo propone; aplica la persona que acepta), y cada cambio deja su fila de
   auditoría con quién lo hizo y desde dónde.
7. **El aviso al partner** (requisito 13.6): si escribe una persona del cliente,
   ``client.business_changed`` en la campana, agrupado por cliente y hora. Se
   emite **después de confirmar** (:func:`after_commit`): un cambio que no se
   guardó no avisa a nadie.
8. **Las pruebas afectadas** (requisito 13.7): las de cada agente publicado del
   cliente vuelven a pasar. Hasta la fase 9 no hay pruebas que correr: queda un
   trabajo ``tests`` terminado que las marca ``stale`` (uno por agente, que se
   va completando con las secciones que cambian; nunca uno por tecla).

El servicio de cada sección (horario, sedes, servicios…) valida su dominio y
escribe sus filas; después llama aquí. ``before``/``after`` son la vista de la
sección en el ClientSpec (``client_spec.section_view``), no las filas: es lo que
el deshacer devuelve.

**Los adaptadores de sección.** Deshacer un cambio y aplicar una propuesta (del
constructor, de una lectura o de un import) escriben en la sección por su
servicio, no aquí. Cada servicio registra el suyo con
:func:`register_section_adapter`: ``restore`` (devolver la sección a una vista) y
``apply`` (aplicar operaciones del parche). Los dos llaman a ``write_section``
con el ``kind`` y la procedencia que reciben. Los de los datos básicos, las
políticas y las redes viven en ``profile_edits.py``; los de las fuentes, en
``sources.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

import sqlalchemy as sa
import structlog
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import AuditLog
from nexus_api.db.models.business import (
    CHANGE_KINDS,
    SECTIONS,
    SOURCES,
    BusinessChange,
    BusinessFieldProvenance,
    BusinessSection,
)
from nexus_api.services.business import compilation
from nexus_api.services.business.sections import Actor, bump_content_rev, touch_section

log = structlog.get_logger(__name__)


@dataclass
class SectionRevisionConflict(Exception):
    """La sección cambió desde la revisión que se leyó (``412``)."""

    section: str
    current: int
    #: Los cambios desde la revisión leída: ``[{change_id, kind, at, by, before, after}]``.
    changes: list[dict[str, Any]] = field(default_factory=list)


class NothingWritten(Exception):
    """Un adaptador no tenía nada que escribir: la sección ya estaba así."""


class BuilderWritesOnlyByProposal(PermissionError):
    """El constructor propone; escribe la persona que acepta (requisito 13.5)."""


@dataclass(frozen=True)
class SectionWritten:
    section: str
    revision: int
    content_rev: int
    change_id: uuid.UUID


@dataclass(frozen=True)
class WriteContext:
    """Con qué procedencia escribe un adaptador lo que le piden."""

    actor: Actor
    source: str = "person"
    kind: str = "edit"
    review: str = "confirmed"
    source_url: str | None = None
    translated_from: str | None = None
    audit_actor: str | None = None
    #: El cambio que esta escritura deshace (``history.undo``).
    undo_of: uuid.UUID | None = None


@dataclass(frozen=True)
class Op:
    """Una operación del parche (``$defs.patch``): ``add`` (``/x/-``),
    ``replace`` (``/x/{id}``, ``/business/campo``, ``/hours``) o ``archive``."""

    op: str
    path: str
    value: Any = None


Restore = Callable[
    [AsyncSession, Mapping[str, Any] | None, WriteContext], Awaitable[SectionWritten]
]
Apply = Callable[[AsyncSession, Sequence[Op], WriteContext], Awaitable[SectionWritten]]


@dataclass(frozen=True)
class SectionAdapter:
    section: str
    restore: Restore | None = None
    apply: Apply | None = None


_ADAPTERS: dict[str, SectionAdapter] = {}

#: Dónde vive el servicio de cada sección: importarlo registra su adaptador.
_OWNERS: Final[dict[str, str]] = {
    "basics": "nexus_api.services.business.profile_edits",
    "policies": "nexus_api.services.business.profile_edits",
    "links": "nexus_api.services.business.profile_edits",
    "sources": "nexus_api.services.business.sources",
    "locations": "nexus_api.services.business.locations",
    "hours": "nexus_api.services.business.hours",
    "special_dates": "nexus_api.services.business.special_dates",
    "services": "nexus_api.services.business.services_catalog",
    "faqs": "nexus_api.services.business.faqs",
}


def register_section_adapter(
    section: str, *, restore: Restore | None = None, apply: Apply | None = None
) -> None:
    """Lo registra el servicio de la sección al importarse. Registrar otra vez
    sustituye (las pruebas ponen los suyos)."""
    if section not in SECTIONS:
        raise ValueError(f"unknown section: {section!r}")
    _ADAPTERS[section] = SectionAdapter(section=section, restore=restore, apply=apply)


def section_adapter(section: str) -> SectionAdapter | None:
    """El adaptador de la sección, importando su servicio si hace falta.
    ``None`` si la sección todavía no tiene uno."""
    if section not in _ADAPTERS and section in _OWNERS:
        with contextlib.suppress(ModuleNotFoundError):
            importlib.import_module(_OWNERS[section])
    return _ADAPTERS.get(section)


# ── después de confirmar ───────────────────────────────────────────────────────

_AFTER_COMMIT: Final = "nexus.business.after_commit"
_HOOKED: Final = "nexus.business.after_commit.hooked"
_PENDING: set[asyncio.Task[None]] = set()


def _run_after_commit(sync: Session) -> None:
    callbacks: list[Callable[[], Awaitable[None]]] = sync.info.pop(_AFTER_COMMIT, [])
    if not callbacks:
        return
    loop = asyncio.get_event_loop()
    for fn in callbacks:
        task = loop.create_task(_safe(fn))
        _PENDING.add(task)
        task.add_done_callback(_PENDING.discard)


def _drop_after_commit(sync: Session) -> None:
    sync.info.pop(_AFTER_COMMIT, None)


async def _safe(fn: Callable[[], Awaitable[None]]) -> None:
    try:
        await fn()
    except Exception as exc:  # lo escrito ya está; un aviso que falla no lo deshace
        log.warning("business.after_commit_failed", error=type(exc).__name__)


def after_commit(session: AsyncSession, fn: Callable[[], Awaitable[None]]) -> None:
    """``fn`` corre en segundo plano cuando la transacción **exterior** de
    ``session`` se confirma, y nunca si hace rollback."""
    sync = session.sync_session
    sync.info.setdefault(_AFTER_COMMIT, []).append(fn)
    if not sync.info.get(_HOOKED):
        event.listen(sync, "after_commit", _run_after_commit)
        event.listen(sync, "after_rollback", _drop_after_commit)
        sync.info[_HOOKED] = True


async def drain_after_commit() -> None:
    """Espera a lo que quedó corriendo tras confirmar (las pruebas, el apagado)."""
    while _PENDING:
        await asyncio.gather(*list(_PENDING), return_exceptions=True)


# ── la escritura ───────────────────────────────────────────────────────────────


async def current_revision(session: AsyncSession, section: str) -> int:
    """La revisión de la sección del cliente del contexto (0 si aún no existe)."""
    rev = await session.scalar(
        sa.select(BusinessSection.revision).where(
            BusinessSection.tenant_id == require_current_tenant(),
            BusinessSection.section == section,
        )
    )
    return int(rev or 0)


def change_out(row: BusinessChange) -> dict[str, Any]:
    return {
        "change_id": str(row.id),
        "kind": row.kind,
        "at": row.at.isoformat(),
        "by": row.actor_id,
        "before": row.before,
        "after": row.after,
    }


async def _changes_since(
    session: AsyncSession, section: str, revision: int
) -> list[dict[str, Any]]:
    """Lo escrito en la sección después de ``revision``, de más viejo a más nuevo.

    El historial no guarda la revisión de cada cambio: se cuentan hacia atrás los
    últimos ``current - revision`` cambios de la sección, que son exactamente los
    que subieron la revisión desde la que se leyó.
    """
    current = await current_revision(session, section)
    missing = max(0, current - revision)
    if missing == 0:
        return []
    rows = (
        await session.scalars(
            sa.select(BusinessChange)
            .where(
                BusinessChange.tenant_id == require_current_tenant(),
                BusinessChange.section == section,
            )
            .order_by(BusinessChange.at.desc(), BusinessChange.id.desc())
            .limit(missing)
        )
    ).all()
    return [change_out(row) for row in reversed(rows)]


async def set_provenance(
    session: AsyncSession,
    pointers: Iterable[str],
    *,
    source: str,
    actor: Actor,
    source_url: str | None = None,
    translated_from: str | None = None,
    review: str = "confirmed",
) -> None:
    """La procedencia **vigente** de cada puntero pasa a esta escritura."""
    if source not in SOURCES:
        raise ValueError(f"unknown source: {source!r}")
    tenant_id = require_current_tenant()
    now = datetime.now(UTC)
    for pointer in pointers:
        row = await session.get(BusinessFieldProvenance, (tenant_id, pointer))
        if row is None:
            row = BusinessFieldProvenance(tenant_id=tenant_id, pointer=pointer)
            session.add(row)
        row.source = source
        row.actor_kind = actor.kind
        row.actor_id = actor.id
        row.origin = actor.origin
        row.source_url = source_url
        row.translated_from = translated_from
        row.review = review
        row.at = now
    await session.flush()


#: La acción de auditoría de cada tipo de cambio (``contracts/events.md`` §4,
#: categoría Negocio). Una migración no deja fila: no la hizo nadie.
AUDIT_ACTIONS: Final[dict[str, str]] = {
    "edit": "business.section_updated",
    "builder_applied": "business.section_updated",
    "import": "business.section_updated",
    "read_applied": "business.read_applied",
    "correction": "business.correction_applied",
    "undo": "business.section_undone",
}
SECTION_UPDATED_ACTION: Final = "business.section_updated"
SECTION_UNDONE_ACTION: Final = "business.section_undone"
READ_APPLIED_ACTION: Final = "business.read_applied"
CORRECTION_APPLIED_ACTION: Final = "business.correction_applied"


def audit_actor_of(actor: Actor) -> str:
    """El ``audit_log.actor`` de una escritura sin principal a mano."""
    if actor.kind == "client_user":
        return f"client:{actor.id}"
    if actor.kind == "partner_member":
        return f"console:{actor.id}"
    if actor.kind == "operator":
        return f"operator:{actor.id}"
    return f"system:{actor.id or 'nexus'}"


async def write_section(
    session: AsyncSession,
    section: str,
    *,
    actor: Actor,
    before: Mapping[str, Any] | list[Any] | None,
    after: Mapping[str, Any] | list[Any] | None,
    pointers: Iterable[str] = (),
    source: str = "person",
    kind: str = "edit",
    expected_revision: int | None = None,
    state: str | None = None,
    source_url: str | None = None,
    translated_from: str | None = None,
    review: str = "confirmed",
    audit_actor: str | None = None,
    undo_of: uuid.UUID | None = None,
    audit_action: str | None = None,
    audit: bool = True,
) -> SectionWritten:
    """Anota una escritura ya hecha en las filas de la sección (ver el módulo).

    ``audit_actor`` es el ``audit_log.actor`` (``principal.actor`` en la
    consola); sin él se deriva de ``actor``. ``undo_of``: el cambio que este
    deshace (lo pone ``history.undo``). ``audit_action`` sustituye la acción de
    auditoría del ``kind`` (las fuentes dicen ``source.added``/``source.removed``);
    ``audit=False`` no deja fila porque la deja quien llama (el modal «Editar
    cliente» escribe ``console.client.update`` con antes y después)."""
    if section not in SECTIONS:
        raise ValueError(f"unknown section: {section!r}")
    if kind not in CHANGE_KINDS:
        raise ValueError(f"unknown change kind: {kind!r}")
    if actor.kind == "builder":
        raise BuilderWritesOnlyByProposal(
            "the builder proposes; the person who accepts it writes it"
        )
    if expected_revision is not None:
        current = await current_revision(session, section)
        if current != expected_revision:
            raise SectionRevisionConflict(
                section=section,
                current=current,
                changes=await _changes_since(session, section, expected_revision),
            )

    tenant_id = require_current_tenant()
    change = BusinessChange(
        tenant_id=tenant_id,
        section=section,
        kind=kind,
        before=_jsonable(before),
        after=_jsonable(after),
        actor_kind=actor.kind,
        actor_id=actor.id,
        origin=actor.origin,
        undo_of=undo_of,
        # La hora de la sentencia, no la de la transacción: dos cambios de la
        # misma transacción no empatan en el historial.
        at=sa.func.clock_timestamp(),
    )
    session.add(change)
    await session.flush()
    pointer_list = list(pointers)
    if pointer_list:
        await set_provenance(
            session,
            pointer_list,
            source=source,
            actor=actor,
            source_url=source_url,
            translated_from=translated_from,
            review=review,
        )
    if state == "complete" and await _still_pending(session, section):
        # Lo que queda leído sin revisar sigue diciéndolo (requisito 8.5).
        state = "read_pending"
    revision = await touch_section(session, section, actor=actor, state=state)
    content_rev = await bump_content_rev(session)
    await compilation.recompile_active_versions(session, content_rev=content_rev)

    action = audit_action or AUDIT_ACTIONS.get(kind)
    if action is not None and audit:
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor=audit_actor or audit_actor_of(actor),
                action=action,
                target=f"business:{section}",
                before_json=None,
                after_json={
                    "section": section,
                    "kind": kind,
                    "source": source,
                    "origin": actor.origin,
                    "change_id": str(change.id),
                },
            )
        )
    await mark_tests_stale(session, sections=[section])
    if actor.kind == "client_user":
        _tell_partner(session, tenant_id=tenant_id, section=section, actor=actor)
    await session.flush()
    await session.refresh(change, attribute_names=["at"])
    return SectionWritten(
        section=section, revision=revision, content_rev=content_rev, change_id=change.id
    )


async def _still_pending(session: AsyncSession, section: str) -> bool:
    """¿Queda en la sección algún dato leído pendiente de revisar?"""
    from nexus_api.services.business.client_spec import SECTION_KEYS

    prefix = "/" + SECTION_KEYS[section]
    found = await session.scalar(
        sa.select(BusinessFieldProvenance.pointer)
        .where(
            BusinessFieldProvenance.tenant_id == require_current_tenant(),
            BusinessFieldProvenance.review == "pending",
            sa.or_(
                BusinessFieldProvenance.pointer == prefix,
                BusinessFieldProvenance.pointer.startswith(prefix + "/"),
            ),
        )
        .limit(1)
    )
    return found is not None


def _jsonable(value: Mapping[str, Any] | list[Any] | None) -> dict[str, Any] | None:
    """``business_changes.before/after`` es un objeto: una lista va envuelta."""
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    return {"items": list(value)}


# ── las pruebas afectadas (requisito 13.7) ─────────────────────────────────────


async def mark_tests_stale(session: AsyncSession, *, sections: Sequence[str]) -> int:
    """Las pruebas de cada agente publicado del cliente quedan desactualizadas.

    Hasta la fase 9 no hay suites que correr: cada agente tiene **un** trabajo
    ``tests`` terminado con ``{stale: true, runs: 0, sections}``, que se completa
    con las secciones que van cambiando. La fase 9 lo cambia por la pasada de
    verdad en segundo plano (y el aviso ``agent.tests.failing`` si alguna falla).
    Devuelve cuántos agentes quedaron marcados."""
    from nexus_api.db.models import Agent, AgentConfig, AgentConfigStatus, Job
    from nexus_api.services.jobs import create_job, finish_job, start_job

    tenant_id = require_current_tenant()
    agent_ids = (
        await session.scalars(
            sa.select(Agent.id)
            .where(
                Agent.tenant_id == tenant_id,
                Agent.status == "active",
                sa.exists().where(
                    AgentConfig.agent_id == Agent.id,
                    AgentConfig.status == AgentConfigStatus.ACTIVE,
                ),
            )
            .order_by(Agent.created_at, Agent.id)
        )
    ).all()
    for agent_id in agent_ids:
        marker = await session.scalar(
            sa.select(Job)
            .where(
                Job.tenant_id == tenant_id,
                Job.agent_id == agent_id,
                Job.kind == "tests",
                Job.status == "done",
                Job.result["stale"].as_boolean().is_(True),
                Job.result["runs"].as_integer() == 0,
            )
            .order_by(Job.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        if marker is not None:
            result = dict(marker.result or {})
            merged = sorted({*result.get("sections", []), *sections})
            if merged != result.get("sections"):
                result["sections"] = merged
                marker.result = result
                marker.updated_at = sa.func.now()
            continue
        job = await create_job(session, kind="tests", agent_id=agent_id, created_by=None)
        await start_job(session, job.id)
        await finish_job(
            session,
            job.id,
            result={
                "stale": True,
                "runs": 0,
                "trigger": "business_changed",
                "sections": sorted(set(sections)),
            },
        )
    return len(agent_ids)


# ── el aviso al partner (requisito 13.6) ───────────────────────────────────────


def _tell_partner(
    session: AsyncSession, *, tenant_id: uuid.UUID, section: str, actor: Actor
) -> None:
    async def _notify() -> None:
        await notify_business_changed(tenant_id=tenant_id, section=section, actor=actor)

    after_commit(session, _notify)


async def notify_business_changed(*, tenant_id: uuid.UUID, section: str, actor: Actor) -> None:
    """``client.business_changed`` a la campana del partner: qué sección cambió,
    quién y desde dónde, **nunca** el dato. Uno por cliente y hora: los cambios
    siguientes de esa hora se suman a sus secciones."""
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import (
        ClientMembership,
        ConsoleNotification,
        NotificationKind,
        PartnerTenant,
    )
    from nexus_api.services.console_notifications import emit

    hour = datetime.now(UTC).strftime("%Y-%m-%dT%H")
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        mapping = await session.scalar(
            sa.select(PartnerTenant).where(PartnerTenant.tenant_id == tenant_id)
        )
        if mapping is None:
            return
        person = (
            await session.execute(
                sa.select(ClientMembership.display_name, ClientMembership.email).where(
                    ClientMembership.tenant_id == tenant_id,
                    ClientMembership.user_id == actor.id,
                )
            )
        ).first()
        # Siempre un nombre que leer: el visible o, sin él, su correo.
        name = (person[0] or person[1]) if person is not None else None
        key = (
            f"{NotificationKind.CLIENT_BUSINESS_CHANGED.value}:{mapping.external_client_ref}:{hour}"
        )
        row = await emit(
            session,
            partner_id=mapping.partner_id,
            kind=NotificationKind.CLIENT_BUSINESS_CHANGED,
            data={
                "client": mapping.client_name,
                "sections": [section],
                "by": name,
                "origin": actor.origin,
            },
            external_client_ref=mapping.external_client_ref,
            dedupe_key=key,
            email=False,
        )
        if row is not None:
            return
        existing = await session.scalar(
            sa.select(ConsoleNotification)
            .where(
                ConsoleNotification.partner_id == mapping.partner_id,
                ConsoleNotification.dedupe_key == key,
            )
            .with_for_update()
        )
        if existing is None:
            return
        payload = dict(existing.payload or {})
        sections = sorted({*payload.get("sections", []), section})
        if sections != payload.get("sections"):
            payload["sections"] = sections
            existing.payload = payload


__all__ = [
    "AUDIT_ACTIONS",
    "CORRECTION_APPLIED_ACTION",
    "READ_APPLIED_ACTION",
    "SECTION_UNDONE_ACTION",
    "SECTION_UPDATED_ACTION",
    "BuilderWritesOnlyByProposal",
    "NothingWritten",
    "Op",
    "SectionAdapter",
    "SectionRevisionConflict",
    "SectionWritten",
    "WriteContext",
    "after_commit",
    "audit_actor_of",
    "change_out",
    "current_revision",
    "drain_after_commit",
    "mark_tests_stale",
    "notify_business_changed",
    "register_section_adapter",
    "section_adapter",
    "set_provenance",
    "write_section",
]
