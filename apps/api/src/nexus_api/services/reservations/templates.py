"""Reservas — las seis plantillas de WhatsApp, pedidas solas a Meta (spec 043,
requisito 15; ``contracts/worker-y-avisos.md`` §Plantillas).

**El catálogo.** Las seis que usa el outbox fuera de la ventana de 24 h, con su
texto de partida, sus variables con nombre y una muestra por variable; idioma
``es``, categoría UTILITY. ``automation.TEMPLATE_VARIABLES`` —lo que el outbox
manda con cada una— sale de aquí: lo que se pide a Meta y lo que se le manda
no pueden separarse (15.8).

**La pasada** (:func:`ensure_templates`), dentro de la sesión acotada al cliente
(``reservation-templates-cron``, cada 15 min):

1. Solo con Reservas encendido (``ClientAccess.reservas_on``) y un número de
   Meta con credenciales (``tenant_credentials``, bajo su RLS) que Meta no haya
   dado por caducadas (``needs_reauth``: cada llamada sería otro 190).
2. Si el espejo ``whatsapp_template_status`` ya tiene las seis de su WABA en un
   idioma ``es*``, en el estado que sea, no se llama a Meta (15.4).
3. Si no, se lista la WABA entera —siguiendo el cursor: sin él solo se veían
   las cien primeras— y se pide cada una que no esté con ese nombre en ``es*``
   (15.1, 15.2). La que ya está, aprobada, en revisión, rechazada o pausada, no
   se pide otra vez ni se toca (15.3): se apunta en el espejo, sin pisar lo que
   dijo el webhook, para que la pasada siguiente no pregunte.
4. Si Meta contesta que ya existe, cuenta como creada (15.2).
5. Cada petición aceptada deja ``reservations.template_requested`` en la
   auditoría (nombre, idioma, id y estado que devolvió Meta) y su fila en el
   espejo con el estado que dio Meta, ``PENDING`` casi siempre (15.6).
6. Una llamada que falla no se repite en la pasada; la siguiente lo intenta
   (15.5). Con Meta caído, limitando o sin permiso se acaba la pasada de ese
   cliente —insistir solo suma llamadas—; con un rechazo de una plantilla, se
   sigue con las demás.

Del error del proveedor se apuntan el tipo y los códigos, nunca su texto (15.6):
el de Meta puede llevar el token o lo que escribió alguien.

**El espejo no lleva RLS** (también guarda las de la WABA de Auphere): toda
lectura de aquí filtra por la WABA de las credenciales del cliente de la sesión
(garantía 1, ``tests/isolation/test_reservas_templates_scope.py``).

Mientras una plantilla no esté aprobada, el outbox sigue como siempre: texto
dentro de la ventana y ``no_template`` fuera (15.10).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Literal, Protocol

import sqlalchemy as sa
import structlog
from nexus_channels.whatsapp_meta import MetaAPIError
from nexus_channels.whatsapp_meta.credentials import INTEGRATION_KEY as META_INTEGRATION
from nexus_channels.whatsapp_meta.credentials import MetaCredentials, MetaCredentialsRepository
from nexus_channels.whatsapp_meta.exceptions import (
    MetaRateLimitedError,
    MetaTransientError,
    TokenInvalidatedError,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import ClientAccess, TenantCredentials, WhatsAppTemplateStatus
from nexus_api.repositories.audit import AuditRepository
from nexus_api.services.whatsapp_templates import invalidate_template_cache

log = structlog.get_logger(__name__)

LANGUAGE: Final = "es"
CATEGORY: Final = "UTILITY"
ACTOR: Final = "system:reservation-templates-cron"
AUDIT_ACTION: Final = "reservations.template_requested"
#: Lo que se pide a Meta por página y cuántas se leen como mucho (una WABA
#: verificada admite 6000 plantillas). Sin ver la lista entera no se pide nada.
PAGE_SIZE: Final = 100
MAX_PAGES: Final = 60
#: «Message Template Already Exists»: ese nombre ya tiene contenido en ese idioma.
ALREADY_EXISTS_SUBCODES: Final = frozenset({2388024})
#: Los estados de Meta que el espejo admite (``ck_tplstatus_status``, 0207).
META_STATES: Final = frozenset(
    {
        "APPROVED",
        "REJECTED",
        "PENDING",
        "PAUSED",
        "DISABLED",
        "PENDING_DELETION",
        "DELETED",
        "ARCHIVED",
        "UNARCHIVED",
        "FLAGGED",
        "IN_APPEAL",
        "LIMIT_EXCEEDED",
        "LOCKED",
        "REINSTATED",
        "UNKNOWN",
    }
)

_VAR = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")


def variables_of(text: str) -> tuple[str, ...]:
    """Las variables ``{{nombre}}`` del texto, en orden de aparición y sin repetir."""
    return tuple(dict.fromkeys(_VAR.findall(text)))


def is_spanish(language: str | None) -> bool:
    """``es``, ``es_ES``, ``es_MX``…: las que el outbox acepta."""
    lang = (language or "").lower()
    return lang == LANGUAGE or lang.startswith(f"{LANGUAGE}_")


# ── el catálogo ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, eq=False)
class TemplateSpec:
    """Una plantilla del contrato: su nombre, su texto y una muestra por variable."""

    name: str
    body: str
    examples: Mapping[str, str]

    @property
    def variables(self) -> tuple[str, ...]:
        return variables_of(self.body)

    def create_payload(self) -> dict[str, Any]:
        """Lo que se manda a ``POST /{waba_id}/message_templates``. Lo arma el
        mismo esquema que usa el formulario de plantillas de la consola."""
        from nexus_api.api.console.schemas_channels import TemplateCreateIn

        form = TemplateCreateIn(
            name=self.name,
            language=LANGUAGE,
            category=CATEGORY,
            body_text=self.body,
            examples=dict(self.examples),
        )
        return {
            "name": self.name,
            "language": LANGUAGE,
            "category": CATEGORY,
            "components": form.to_components(),
            "parameter_format": form.parameter_format(),
        }


_EXAMPLES: Final[Mapping[str, str]] = {
    "nombre": "Camila",
    "negocio": "Barbería Centro",
    "cuando": "el jueves 23 a las 20:30",
    "detalle": "Corte con Lucía",
    "minutos": "15",
}


def _spec(name: str, body: str) -> TemplateSpec:
    return TemplateSpec(
        name=name, body=body, examples={v: _EXAMPLES[v] for v in variables_of(body)}
    )


#: Los textos de partida del contrato, con dos arreglos de la enmienda del
#: requisito 15, porque Meta los habría rechazado y una plantilla rechazada no se
#: rehace sola (15.3): ``reserva_hueco_libre`` saluda por el nombre (el outbox ya
#: mandaba ``nombre`` y Meta rechaza una variable que el texto no lleva), y la
#: petición de confirmación y el recordatorio dicen ``{{cuando}} en {{negocio}}``
#: (``{{negocio}} {{cuando}}`` son dos variables seguidas, formato no válido). El
#: recordatorio y el cambio llevan más texto fijo: con 4 variables en una frase corta, Meta
#: los rechazó en staging (code 100, subcode 2388293, 2026-11-08).
CATALOG: Final[tuple[TemplateSpec, ...]] = (
    _spec(
        "reserva_confirmada",
        "Hola, {{nombre}}. Tu reserva en {{negocio}} quedó para {{cuando}} ({{detalle}}). "
        "Si necesitas cambiarla, escríbenos por aquí.",
    ),
    _spec(
        "reserva_pide_confirmacion",
        "Hola, {{nombre}}. Te esperamos {{cuando}} en {{negocio}} ({{detalle}}). "
        "¿Nos confirmas que vienes? Responde SÍ o NO.",
    ),
    _spec(
        "reserva_recordatorio",
        "Hola, {{nombre}}. Te escribimos para recordarte tu reserva {{cuando}} en {{negocio}} "
        "({{detalle}}). Si no puedes venir, avísanos por aquí y la cambiamos.",
    ),
    _spec(
        "reserva_cambiada",
        "Hola, {{nombre}}. Te avisamos de que tu reserva en {{negocio}} cambió: ahora es "
        "{{cuando}} ({{detalle}}). Si esa hora no te viene bien, escríbenos por aquí.",
    ),
    _spec(
        "reserva_cancelada",
        "Hola, {{nombre}}. Tu reserva en {{negocio}} para {{cuando}} quedó cancelada. "
        "Si quieres otra hora, escríbenos por aquí.",
    ),
    _spec(
        "reserva_hueco_libre",
        "Hola, {{nombre}}. Mensaje automático de {{negocio}}: se liberó un hueco {{cuando}} "
        "({{detalle}}). ¿Lo quieres? Responde SÍ en los próximos {{minutos}} minutos y te "
        "lo reservamos.",
    ),
)
BY_NAME: Final[Mapping[str, TemplateSpec]] = {t.name: t for t in CATALOG}
NAMES: Final[tuple[str, ...]] = tuple(t.name for t in CATALOG)
#: Las variables (BODY, con nombre) que el outbox manda con cada plantilla.
VARIABLES: Final[Mapping[str, tuple[str, ...]]] = {t.name: t.variables for t in CATALOG}


# ── la pasada ───────────────────────────────────────────────────────────────


class TemplatesClient(Protocol):
    """Lo que la pasada usa de ``MetaClient``: listar y crear. Nunca borrar."""

    async def list_templates(
        self, *, waba_id: str, access_token: str, limit: int = ..., after: str | None = ...
    ) -> dict[str, Any]: ...

    async def create_template(
        self,
        *,
        waba_id: str,
        access_token: str,
        name: str,
        language: str,
        category: str,
        components: list[dict[str, Any]],
        parameter_format: str | None = ...,
    ) -> dict[str, Any]: ...


Skipped = Literal["reservas_off", "no_whatsapp", "complete", "needs_reauth", "list_failed"]


@dataclass
class Outcome:
    """Lo que hizo la pasada en un cliente."""

    skipped: Skipped | None = None
    requested: list[str] = field(default_factory=list)
    existing: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    def as_log(self) -> dict[str, Any]:
        return {
            "skipped": self.skipped,
            "requested": len(self.requested),
            "existing": len(self.existing),
            "failed": len(self.failed),
        }


@dataclass(frozen=True)
class _Live:
    name: str
    language: str
    status: str
    category: str | None


def _meta_error(exc: MetaAPIError) -> dict[str, Any]:
    """Del error de Meta, lo que puede ir al log: tipo y códigos, sin su texto."""
    return {
        "error_type": type(exc).__name__,
        "status_code": exc.status_code,
        "code": exc.code,
        "subcode": exc.subcode,
    }


def _already_exists(exc: MetaAPIError) -> bool:
    if exc.subcode in ALREADY_EXISTS_SUBCODES:
        return True
    # Por si Meta lo dice con otro subcódigo: se mira, no se apunta.
    return exc.status_code == 400 and "already exists" in (exc.body or "").lower()


def _ends_the_pass(exc: MetaAPIError) -> bool:
    """Meta caído, limitando o sin permiso: las demás fallarían igual."""
    return isinstance(exc, MetaTransientError | MetaRateLimitedError | TokenInvalidatedError)


def _state(raw: object) -> str:
    st = str(raw or "").upper()
    return st if st in META_STATES else "PENDING"


async def _mirrored(session: AsyncSession, waba_id: str) -> dict[str, list[WhatsAppTemplateStatus]]:
    """Las filas del espejo de las seis en la WABA del cliente, en ``es*``."""
    rows = await session.execute(
        sa.select(WhatsAppTemplateStatus).where(
            WhatsAppTemplateStatus.waba_id == waba_id,
            WhatsAppTemplateStatus.template_name.in_(NAMES),
        )
    )
    out: dict[str, list[WhatsAppTemplateStatus]] = {}
    for row in rows.scalars():
        if is_spanish(row.language):
            out.setdefault(row.template_name, []).append(row)
    return out


async def _needs_reauth(session: AsyncSession) -> bool:
    """La fila de credenciales del cliente (bajo su RLS) está marcada para
    volver a conectar."""
    flagged = await session.scalar(
        sa.select(TenantCredentials.needs_reauth).where(
            TenantCredentials.integration == META_INTEGRATION
        )
    )
    return bool(flagged)


async def _live(client: TemplatesClient, creds: MetaCredentials) -> dict[str, _Live]:
    """Las del contrato que ya tiene la WABA en ``es*``, leyendo todas las páginas.
    Lanza ``MetaAPIError`` si una falla, y ``LookupError`` si no se acaba."""
    found: dict[str, _Live] = {}
    after: str | None = None
    for _page in range(MAX_PAGES):
        payload = await client.list_templates(
            waba_id=creds.waba_id, access_token=creds.bisuat, limit=PAGE_SIZE, after=after
        )
        for raw in payload.get("data") or []:
            if not isinstance(raw, dict):
                continue
            name, language = str(raw.get("name") or ""), str(raw.get("language") or "")
            if name in BY_NAME and is_spanish(language) and name not in found:
                category = raw.get("category")
                found[name] = _Live(
                    name=name,
                    language=language,
                    status=_state(raw.get("status")),
                    category=category if isinstance(category, str) else None,
                )
        paging = payload.get("paging")
        paging = paging if isinstance(paging, dict) else {}
        cursors = paging.get("cursors")
        cursors = cursors if isinstance(cursors, dict) else {}
        nxt = cursors.get("after")
        if not paging.get("next") or not isinstance(nxt, str) or not nxt:
            return found
        after = nxt
    raise LookupError("template list did not end")


async def _mirror(
    session: AsyncSession,
    *,
    tenant_id: Any,
    waba_id: str,
    name: str,
    language: str,
    status: str,
    category: str | None,
    now: datetime | None,
) -> None:
    """Una fila nueva en el espejo. Si el webhook ya escribió esa plantilla, gana
    el webhook: lo suyo es más nuevo que lo que esta pasada sabe."""
    values: dict[str, Any] = {
        "waba_id": waba_id,
        "template_name": name,
        "language": language,
        "status": status,
        "category": category,
        "tenant_id": tenant_id,
        "last_event_payload": {"source": "reservation_templates"},
    }
    if now is not None:
        values["last_event_at"] = now
    await session.execute(
        insert(WhatsAppTemplateStatus)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["waba_id", "template_name", "language"])
    )


async def ensure_templates(
    session: AsyncSession, *, client: TemplatesClient, now: datetime | None = None
) -> Outcome:
    """Pide a Meta las plantillas de Reservas que le faltan a la WABA del cliente
    de la sesión. Nunca lanza por Meta: lo que falla queda en ``Outcome`` y en el
    log (sin el texto del proveedor), y lo intenta la pasada siguiente."""
    tenant_id = require_current_tenant()
    access = await session.get(ClientAccess, tenant_id)
    if access is None or not access.reservas_on:
        return Outcome(skipped="reservas_off")
    creds = await MetaCredentialsRepository(session).get()
    if creds is None or not creds.waba_id or not creds.bisuat:
        return Outcome(skipped="no_whatsapp")

    mirrored = await _mirrored(session, creds.waba_id)
    missing = [t for t in CATALOG if t.name not in mirrored]
    if not missing:
        return Outcome(skipped="complete")
    if await _needs_reauth(session):
        # Meta ya dijo que ese token no vale: hasta que se vuelva a conectar el
        # número, cada llamada sería otro 190.
        return Outcome(skipped="needs_reauth")

    try:
        live = await _live(client, creds)
    except MetaAPIError as exc:
        log.warning(
            "reservation_templates.list_failed", tenant_id=str(tenant_id), **_meta_error(exc)
        )
        return Outcome(skipped="list_failed")
    except LookupError:
        log.warning("reservation_templates.list_unbounded", tenant_id=str(tenant_id))
        return Outcome(skipped="list_failed")

    out = Outcome()
    audit = AuditRepository(session)
    for spec in missing:
        there = live.get(spec.name)
        if there is not None:
            # Ya está en la WABA (la hizo el partner, o el espejo no la vio): no
            # se pide otra vez, ni se recrea ni se borra si Meta la rechazó o pausó.
            await _mirror(
                session,
                tenant_id=tenant_id,
                waba_id=creds.waba_id,
                name=spec.name,
                language=there.language,
                status=there.status,
                category=there.category,
                now=now,
            )
            out.existing.append(spec.name)
            continue
        payload = spec.create_payload()
        try:
            result = await client.create_template(
                waba_id=creds.waba_id, access_token=creds.bisuat, **payload
            )
        except MetaAPIError as exc:
            if _already_exists(exc):
                # La pasada siguiente la ve en la lista y la apunta con su estado.
                out.existing.append(spec.name)
                continue
            out.failed.append(spec.name)
            log.warning(
                "reservation_templates.create_failed",
                tenant_id=str(tenant_id),
                template=spec.name,
                **_meta_error(exc),
            )
            if _ends_the_pass(exc):
                break
            continue
        meta_id = result.get("id")
        status = _state(result.get("status"))
        returned = result.get("category")
        category: str = returned if isinstance(returned, str) and returned else CATEGORY
        # Meta no se deshace con un ROLLBACK: lo de cada plantilla va en su
        # SAVEPOINT, y un fallo aquí no se lleva lo apuntado de las demás. La que
        # quede sin fila la ve en la lista la pasada siguiente.
        try:
            await _record(
                session,
                audit,
                tenant_id=tenant_id,
                waba_id=creds.waba_id,
                spec=spec,
                meta_id=meta_id if isinstance(meta_id, str) else None,
                status=status,
                category=category,
                now=now,
            )
        except Exception as exc:
            out.failed.append(spec.name)
            log.error(
                "reservation_templates.record_failed",
                tenant_id=str(tenant_id),
                template=spec.name,
                error_type=type(exc).__name__,
            )
            continue
        out.requested.append(spec.name)
        log.info(
            "reservation_templates.requested",
            tenant_id=str(tenant_id),
            template=spec.name,
            status=status,
        )
    await session.flush()
    if out.requested:
        invalidate_template_cache(creds.waba_id)
    return out


async def _record(
    session: AsyncSession,
    audit: AuditRepository,
    *,
    tenant_id: Any,
    waba_id: str,
    spec: TemplateSpec,
    meta_id: str | None,
    status: str,
    category: str,
    now: datetime | None,
) -> None:
    """La fila del espejo y la de auditoría de una plantilla pedida, juntas."""
    async with session.begin_nested():
        await _mirror(
            session,
            tenant_id=tenant_id,
            waba_id=waba_id,
            name=spec.name,
            language=LANGUAGE,
            status=status,
            category=category,
            now=now,
        )
        await audit.record(
            actor=ACTOR,
            action=AUDIT_ACTION,
            target=f"template:{spec.name}",
            after={
                "name": spec.name,
                "language": LANGUAGE,
                "category": category,
                "meta_id": meta_id,
                "status": status,
            },
        )


# ── lo que ve el negocio (los Ajustes de Reservas) ──────────────────────────

TemplateState = Literal["approved", "in_review", "rejected", "paused", "not_created"]
Rejection = Literal[
    "invalid_format", "incorrect_category", "promotional", "abusive_content", "other"
]
NotCreated = Literal["no_whatsapp", "on_its_way", "deleted"]

_APPROVED = frozenset({"APPROVED", "REINSTATED", "UNARCHIVED"})
_IN_REVIEW = frozenset({"PENDING", "IN_APPEAL", "UNKNOWN"})
_PAUSED = frozenset({"PAUSED", "DISABLED", "FLAGGED", "LIMIT_EXCEEDED", "LOCKED"})
_GONE = frozenset({"PENDING_DELETION", "DELETED", "ARCHIVED"})
#: Del mejor al peor: con dos idiomas ``es*``, manda el que deja enviar.
_RANK: Final[tuple[TemplateState, ...]] = ("approved", "in_review", "paused", "rejected")


def state_of(status: str | None) -> tuple[TemplateState, NotCreated | None]:
    st = (status or "").upper()
    if st in _APPROVED:
        return "approved", None
    if st == "REJECTED":
        return "rejected", None
    if st in _PAUSED:
        return "paused", None
    if st in _GONE:
        return "not_created", "deleted"
    return "in_review", None


def rejection_of(reason: str | None) -> Rejection:
    """El motivo de Meta como código: la pantalla lo dice con palabras del
    negocio, y el texto libre de Meta no llega a la persona del cliente (el
    partner lo ve entero en su consola)."""
    key = (reason or "").strip().upper()
    if key == "INVALID_FORMAT" or any(w in key for w in ("FORMAT", "VARIABLE", "SAMPLE")):
        return "invalid_format"
    if key in {"INCORRECT_CATEGORY", "TAG_CONTENT_MISMATCH"}:
        return "incorrect_category"
    if key == "PROMOTIONAL":
        return "promotional"
    if key in {"ABUSIVE_CONTENT", "SCAM"}:
        return "abusive_content"
    return "other"


@dataclass(frozen=True)
class TemplateView:
    name: str
    state: TemplateState
    rejection: Rejection | None = None
    why_not_created: NotCreated | None = None
    since: datetime | None = None


@dataclass(frozen=True)
class TemplatesView:
    whatsapp: bool
    items: tuple[TemplateView, ...]

    @property
    def approved(self) -> int:
        return sum(1 for i in self.items if i.state == "approved")


def _view(name: str, rows: list[WhatsAppTemplateStatus]) -> TemplateView:
    if not rows:
        return TemplateView(name=name, state="not_created", why_not_created="on_its_way")
    views = []
    for row in rows:
        state, why = state_of(row.status)
        views.append(
            TemplateView(
                name=name,
                state=state,
                rejection=rejection_of(row.reason) if state == "rejected" else None,
                why_not_created=why,
                since=row.last_event_at or row.updated_at,
            )
        )
    order = {s: i for i, s in enumerate(_RANK)}
    return min(views, key=lambda v: order.get(v.state, len(order)))


async def templates_view(session: AsyncSession) -> TemplatesView:
    """Las seis del cliente de la sesión, leídas del espejo de su WABA. No llama
    a Meta: el webhook y la pasada mantienen el espejo."""
    creds = await MetaCredentialsRepository(session).get()
    if creds is None or not creds.waba_id:
        return TemplatesView(
            whatsapp=False,
            items=tuple(
                TemplateView(name=n, state="not_created", why_not_created="no_whatsapp")
                for n in NAMES
            ),
        )
    mirrored = await _mirrored(session, creds.waba_id)
    return TemplatesView(whatsapp=True, items=tuple(_view(n, mirrored.get(n, [])) for n in NAMES))


__all__ = [
    "ACTOR",
    "AUDIT_ACTION",
    "BY_NAME",
    "CATALOG",
    "LANGUAGE",
    "NAMES",
    "VARIABLES",
    "NotCreated",
    "Outcome",
    "Rejection",
    "TemplateSpec",
    "TemplateState",
    "TemplateView",
    "TemplatesClient",
    "TemplatesView",
    "ensure_templates",
    "is_spanish",
    "rejection_of",
    "state_of",
    "templates_view",
    "variables_of",
]
