"""Spec 075 — editar una plantilla de WhatsApp sin cambiarle el nombre.

Una sola fuente para la consola y el panel (9.3): qué se puede editar, cómo
se parte el contenido para el editor, cómo se arma lo que se manda a Meta y
qué plantillas manda Auphere por su nombre.

**Qué se puede editar** (research R4). La regla se escribe por lo que **sí**
se admite: cabecera de texto sin variables, cuerpo, pie y hasta tres botones
``QUICK_REPLY``, ``URL`` sin variable o ``PHONE_NUMBER``; categoría que no sea
de autenticación; estado ``APPROVED``, ``REJECTED`` o ``PAUSED``. Y además el
viaje de ida y vuelta tiene que reproducir la plantilla: ``build(draft_of(t))``
igual a lo que lista Meta. Lo que no lo reproduce se perdería al editar —Meta
sustituye el contenido entero— y queda bloqueado (3.3), aunque sea una clave
que Meta añada mañana a un cuerpo.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Literal

import sqlalchemy as sa
import structlog
from fastapi import HTTPException, status
from nexus_channels.whatsapp_meta import MetaAPIError
from nexus_channels.whatsapp_meta.credentials import MetaCredentials
from nexus_channels.whatsapp_meta.exceptions import MetaRateLimitedError
from nexus_channels.whatsapp_meta.meta_client import MetaClient
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import get_current_tenant, require_current_tenant
from nexus_api.db.models import Message, MessageStatus
from nexus_api.db.models.conversation import WhatsAppTemplateStatus
from nexus_api.repositories.audit import AuditRepository
from nexus_api.schemas.whatsapp_templates import (
    BODY_VAR_RE,
    TemplateButtonOut,
    TemplateContentIn,
    TemplateContentOut,
)
from nexus_api.services.reservations import templates as reservas
from nexus_api.services.whatsapp_templates import (
    TemplateOut,
    build_meta_client,
    invalidate_template_cache,
    require_meta_credentials,
)

log = structlog.get_logger(__name__)

BlockerCode = Literal[
    "status",
    "authentication",
    "media_header",
    "header_variable",
    "unsupported_button",
    "url_variable",
    "too_many_buttons",
    "unsupported_component",
]

#: Los únicos estados en los que Meta deja editar (documentación de gestión
#: de plantillas, leída el 2026-11-23; comprobado en WhatsApp Manager).
EDITABLE_STATUSES: Final[frozenset[str]] = frozenset({"APPROVED", "REJECTED", "PAUSED"})

_BUTTON_TYPES: Final[frozenset[str]] = frozenset({"QUICK_REPLY", "URL", "PHONE_NUMBER"})
_MAX_BUTTONS: Final[int] = 3
_ORDER: Final[Mapping[str, int]] = {"HEADER": 0, "BODY": 1, "FOOTER": 2, "BUTTONS": 3}


# ── plantillas que Auphere manda por su nombre (requisito 4) ────────────────

#: Cobros (``cobranza_reminder_cron``) las manda con estas cuatro variables.
COBROS_PROXIMO: Final[str] = "recordatorio_pago_proximo"
COBROS_VENCIDO: Final[str] = "recordatorio_pago_vencido"
COBROS_VARIABLES: Final[tuple[str, ...]] = ("cliente", "negocio", "monto", "fecha")


@dataclass(frozen=True)
class SystemTemplate:
    """``exact``: las variables son exactamente estas (Reservas, 043 15.8).
    ``subset_keep``: ninguna de fuera, y ninguna de las que la versión
    actual lleva puede desaparecer (cobros manda las cuatro siempre)."""

    mode: Literal["exact", "subset_keep"]
    variables: tuple[str, ...]


SYSTEM_TEMPLATES: Final[Mapping[str, SystemTemplate]] = {
    **{name: SystemTemplate("exact", tuple(reservas.VARIABLES[name])) for name in reservas.NAMES},
    COBROS_PROXIMO: SystemTemplate("subset_keep", COBROS_VARIABLES),
    COBROS_VENCIDO: SystemTemplate("subset_keep", COBROS_VARIABLES),
}


def system_template_for(name: str, language: str | None) -> SystemTemplate | None:
    """Auphere solo las manda en español: en otro idioma son del partner."""
    if not (language or "").lower().startswith("es"):
        return None
    return SYSTEM_TEMPLATES.get(name)


def check_system_variables(
    system: SystemTemplate, *, current: Sequence[str], new: Sequence[str]
) -> tuple[list[str], list[str]]:
    """``(faltan, sobran)``; las dos vacías quieren decir que vale."""
    allowed = system.variables
    extra = [v for v in dict.fromkeys(new) if v not in allowed]
    if system.mode == "exact":
        missing = [v for v in allowed if v not in new]
    else:
        missing = [v for v in dict.fromkeys(current) if v in allowed and v not in new]
    return missing, extra


# ── contenido: partir, armar, comparar ──────────────────────────────────────


def normalize(components: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Mismo orden de componentes que arma ``to_components``. El orden de
    las claves no cuenta: dos ``dict`` iguales lo son en cualquier orden."""
    items = [dict(c) for c in components]
    return sorted(
        items,
        key=lambda c: _ORDER.get(str(c.get("type") or "").upper(), len(_ORDER)),
    )


def build(content: TemplateContentIn) -> list[dict[str, Any]]:
    return content.to_components()


def template_version(tpl: TemplateOut) -> str:
    """Huella de ``{category, components}`` (research R7): Meta no tiene
    versión ni ETag de una plantilla, y el contenido es lo único que
    distingue un cambio hecho por otro."""
    canonical = json.dumps(
        {"category": tpl.category, "components": normalize(tpl.components)},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _split(tpl: TemplateOut) -> TemplateContentOut | None:
    """El contenido en las partes del editor, o ``None`` si lleva algo que
    el editor no pinta."""
    header: str | None = None
    body: str | None = None
    footer: str | None = None
    buttons: list[TemplateButtonOut] = []
    examples: dict[str, str] = {}
    for comp in tpl.components:
        ctype = str(comp.get("type") or "").upper()
        if ctype == "HEADER":
            if str(comp.get("format") or "").upper() != "TEXT":
                return None
            header = str(comp.get("text") or "")
        elif ctype == "BODY":
            body = str(comp.get("text") or "")
            example = comp.get("example") or {}
            if isinstance(example, Mapping):
                named = example.get("body_text_named_params")
                if isinstance(named, list):
                    for p in named:
                        if isinstance(p, Mapping) and p.get("param_name"):
                            examples[str(p["param_name"])] = str(p.get("example") or "")
                positional = example.get("body_text")
                if isinstance(positional, list) and positional and isinstance(positional[0], list):
                    names = sorted(
                        {m.group(1) for m in BODY_VAR_RE.finditer(body) if m.group(1).isdigit()},
                        key=int,
                    )
                    for name, value in zip(names, positional[0], strict=False):
                        examples[name] = str(value)
        elif ctype == "FOOTER":
            footer = str(comp.get("text") or "")
        elif ctype == "BUTTONS":
            for b in comp.get("buttons") or []:
                if not isinstance(b, Mapping):
                    return None
                buttons.append(
                    TemplateButtonOut(
                        type=str(b.get("type") or ""),
                        label=str(b.get("text") or ""),
                        url=b.get("url"),
                        phone_number=b.get("phone_number"),
                    )
                )
        else:
            return None
    if body is None:
        return None
    return TemplateContentOut(
        category=tpl.category,
        header_text=header or None,
        body_text=body,
        footer_text=footer or None,
        buttons=buttons,
        examples=examples,
    )


def _content_blocker(tpl: TemplateOut) -> BlockerCode | None:
    for comp in tpl.components:
        ctype = str(comp.get("type") or "").upper()
        if ctype == "HEADER":
            if str(comp.get("format") or "").upper() != "TEXT":
                return "media_header"
            if BODY_VAR_RE.search(str(comp.get("text") or "")):
                return "header_variable"
        elif ctype == "BUTTONS":
            buttons = comp.get("buttons") or []
            if len(buttons) > _MAX_BUTTONS:
                return "too_many_buttons"
            for b in buttons:
                btype = str((b or {}).get("type") or "").upper()
                if btype not in _BUTTON_TYPES:
                    return "unsupported_button"
                if btype == "URL" and "{{" in str(b.get("url") or ""):
                    return "url_variable"
        elif ctype not in ("BODY", "FOOTER"):
            return "unsupported_component"
    draft = _split(tpl)
    if draft is None:
        return "unsupported_component"
    try:
        rebuilt = build(TemplateContentIn(**draft.model_dump()))
    except ValidationError:
        return "unsupported_component"
    if normalize(rebuilt) != normalize(tpl.components):
        return "unsupported_component"
    return None


def edit_blocker(tpl: TemplateOut) -> BlockerCode | None:
    """Por qué no se puede editar aquí, o ``None`` (3.1, 3.2)."""
    if (tpl.status or "").upper() not in EDITABLE_STATUSES:
        return "status"
    if (tpl.category or "").upper() == "AUTHENTICATION":
        return "authentication"
    return _content_blocker(tpl)


def draft_of(tpl: TemplateOut) -> TemplateContentOut | None:
    """El borrador para abrir el editor; ``None`` si el contenido no se
    puede pintar sin perder algo (el estado no cuenta aquí)."""
    if _content_blocker(tpl) is not None:
        return None
    return _split(tpl)


def is_noop(tpl: TemplateOut, content: TemplateContentIn) -> bool:
    """Nada que mandar (3.4). Compara lo que se va a mandar con lo que
    se armaría con el contenido de hoy, no con la lectura en bruto de Meta:
    una diferencia de forma no puede gastar una edición de una aprobada."""
    draft = draft_of(tpl)
    if draft is None:
        return False
    if (content.category or tpl.category) != tpl.category:
        return False
    current = build(TemplateContentIn(**draft.model_dump()))
    return bool(_loose(normalize(build(content))) == _loose(normalize(current)))


def _loose(value: Any, *, key: str | None = None) -> Any:
    """Igualdad que no cuenta espacios al borde ni el formato del teléfono:
    el editor recorta lo que manda, y una diferencia así no puede gastar una
    edición de una aprobada (3.4)."""
    if isinstance(value, dict):
        return {k: _loose(v, key=k) for k, v in value.items()}
    if isinstance(value, list):
        return [_loose(v, key=key) for v in value]
    if isinstance(value, str):
        text = value.strip()
        return text.replace(" ", "").replace("-", "") if key == "phone_number" else text
    return value


# ── editar (T015, T022, T027) ───────────────────────────────────────────────


@dataclass(frozen=True)
class EditResult:
    name: str
    language: str
    changed: bool
    status: str | None
    category: str | None


def _refuse(status_code: int, code: str, **info: Any) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, **info})


def _user_message(exc: MetaAPIError) -> str | None:
    """El ``error_user_msg`` que Meta escribe para personas. Va a la pantalla
    como dato; nunca a un registro (8.5)."""
    try:
        payload = json.loads(exc.body or "{}")
    except (TypeError, ValueError):
        return None
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return None
    msg = error.get("error_user_msg") or error.get("error_user_title")
    return str(msg) if msg else None


async def _live_template(
    client: MetaClient, creds: MetaCredentials, name: str, language: str
) -> TemplateOut | None:
    """La plantilla tal como la tiene Meta ahora, sin caché, buscada **solo**
    en la cuenta de las credenciales de la sesión (8.1). Sigue el cursor:
    sin él, una plantilla de la segunda página no existiría."""
    after: str | None = None
    for _ in range(50):
        payload = await client.list_templates(
            waba_id=creds.waba_id, access_token=creds.bisuat, after=after
        )
        for raw in payload.get("data") or []:
            if not isinstance(raw, dict):
                continue
            if raw.get("name") == name and raw.get("language") == language:
                return TemplateOut(
                    id=raw.get("id"),
                    name=name,
                    language=language,
                    category=raw.get("category"),
                    status=raw.get("status"),
                    components=[c for c in (raw.get("components") or []) if isinstance(c, dict)],
                )
        paging = payload.get("paging") if isinstance(payload, dict) else None
        cursors = (paging or {}).get("cursors") or {}
        after = cursors.get("after") if (paging or {}).get("next") else None
        if not after:
            return None
    return None


async def count_queued_sends(session: AsyncSession, *, name: str, language: str) -> int:
    """Envíos del cliente de la sesión todavía en cola con esta plantilla.
    ``messages`` va bajo RLS, pero sin FORCE: quien es dueño de la tabla la
    salta. El filtro por el cliente del contexto (nunca del llamante) es la
    segunda llave (5.1, garantía 1)."""
    stmt = sa.select(sa.func.count()).where(
        Message.tenant_id == require_current_tenant(),
        Message.status == MessageStatus.PENDING,
        Message.template_payload["name"].astext == name,
        Message.template_payload["language"].astext == language,
    )
    return int((await session.execute(stmt)).scalar_one())


async def _mirror_after_edit(
    session: AsyncSession,
    *,
    waba_id: str,
    tpl: TemplateOut,
    since: datetime,
) -> None:
    """El espejo pasa al estado que acaba de dar Meta (6.2), sin motivo de
    rechazo, salvo que el aviso de Meta haya llegado ya (6.3): ese manda.
    Siempre con la ``waba_id`` de las credenciales de la sesión (garantía 1)."""
    status = (tpl.status or "").upper()
    if not status:
        return
    now = datetime.now(UTC)
    values = {
        "waba_id": waba_id,
        "template_name": tpl.name,
        "language": tpl.language,
        "status": status,
        "category": tpl.category,
        "reason": None,
        "tenant_id": get_current_tenant(),
        "last_event_at": now,
        "last_event_payload": {"field": "nexus_edit", "value": {"status": status}},
    }
    stmt = pg_insert(WhatsAppTemplateStatus).values(**values)
    table = WhatsAppTemplateStatus.__table__
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=["waba_id", "template_name", "language"],
            set_={
                "status": stmt.excluded.status,
                "category": stmt.excluded.category,
                "reason": None,
                "last_event_at": stmt.excluded.last_event_at,
                "last_event_payload": stmt.excluded.last_event_payload,
            },
            where=sa.or_(table.c.last_event_at.is_(None), table.c.last_event_at < since),
        )
    )


async def edit_template(
    session: AsyncSession,
    *,
    name: str,
    language: str,
    body: TemplateContentIn,
    version: str,
    confirm: bool,
    actor: str,
    audit_action: str,
) -> EditResult:
    """Editar una plantilla del cliente de la sesión (075). La consola y el
    panel llaman aquí y a ningún otro sitio (9.3)."""
    creds = await require_meta_credentials(session)
    client = build_meta_client()
    try:
        try:
            tpl = await _live_template(client, creds, name, language)
        except MetaAPIError as exc:
            log.warning(
                "template.edit.list_failed",
                waba_id=creds.waba_id,
                error_type=type(exc).__name__,
                code=exc.code,
                subcode=exc.subcode,
            )
            raise _refuse(status.HTTP_502_BAD_GATEWAY, "meta_unavailable") from exc
        if tpl is None or not tpl.id:
            raise _refuse(status.HTTP_404_NOT_FOUND, "template_not_found")
        if template_version(tpl) != version:
            raise _refuse(status.HTTP_409_CONFLICT, "template_changed")
        blocker = edit_blocker(tpl)
        if blocker is not None:
            raise _refuse(status.HTTP_409_CONFLICT, "not_editable", blocker=blocker)
        missing_examples = body.missing_examples()
        if missing_examples:
            raise _refuse(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "missing_examples", variables=missing_examples
            )
        approved = (tpl.status or "").upper() == "APPROVED"
        wants_category = body.category or tpl.category
        if approved and wants_category != tpl.category:
            raise _refuse(status.HTTP_422_UNPROCESSABLE_ENTITY, "category_locked")

        draft = draft_of(tpl)
        assert draft is not None  # sin bloqueo de contenido hay borrador
        current_vars = TemplateContentIn(**draft.model_dump()).variables()
        new_vars = body.variables()
        system = system_template_for(name, language)
        if system is not None:
            missing, extra = check_system_variables(system, current=current_vars, new=new_vars)
            if missing or extra:
                raise _refuse(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "system_variables",
                    missing=missing,
                    extra=extra,
                )

        if is_noop(tpl, body):
            return EditResult(name, language, False, tpl.status, tpl.category)

        reasons: list[dict[str, Any]] = []
        if approved:
            reasons.append({"kind": "approved"})
        if system is None and any(v not in new_vars for v in current_vars):
            queued = await count_queued_sends(session, name=name, language=language)
            if queued:
                reasons.append({"kind": "queued_sends", "count": queued})
        if reasons and not confirm:
            raise _refuse(status.HTTP_409_CONFLICT, "confirmation_required", reasons=reasons)

        components = build(body)
        since = datetime.now(UTC)
        try:
            await client.edit_template(
                template_id=tpl.id,
                access_token=creds.bisuat,
                components=components,
                category=wants_category if wants_category != tpl.category else None,
                parameter_format=body.parameter_format(),
            )
        except MetaAPIError as exc:
            log.warning(
                "template.edit.meta_rejected",
                waba_id=creds.waba_id,
                error_type=type(exc).__name__,
                status_code=exc.status_code,
                code=exc.code,
                subcode=exc.subcode,
            )
            if isinstance(exc, MetaRateLimitedError):
                http = status.HTTP_429_TOO_MANY_REQUESTS
            elif 400 <= int(exc.status_code or 502) < 500:
                http = status.HTTP_422_UNPROCESSABLE_ENTITY
            else:
                http = status.HTTP_502_BAD_GATEWAY
            raise _refuse(
                http,
                "meta_rejected",
                meta_code=exc.code,
                meta_subcode=exc.subcode,
                user_message=_user_message(exc),
            ) from exc

        invalidate_template_cache(creds.waba_id)
        try:
            fresh = await _live_template(client, creds, name, language)
        except MetaAPIError:
            fresh = None
    finally:
        await client.close()

    now_tpl = fresh or tpl.model_copy(update={"status": "PENDING", "components": components})
    await _mirror_after_edit(session, waba_id=creds.waba_id, tpl=now_tpl, since=since)
    await AuditRepository(session).record(
        actor=actor,
        action=audit_action,
        target=f"template:{name}:{language}",
        before={"category": tpl.category, "components": tpl.components},
        after={
            "category": now_tpl.category,
            "components": now_tpl.components,
            "meta_status": now_tpl.status,
        },
    )
    log.info(
        "template.edit.done",
        waba_id=creds.waba_id,
        template_name=name,
        language=language,
        status=now_tpl.status,
    )
    return EditResult(name, language, True, now_tpl.status, now_tpl.category)


def row_extras(tpl: TemplateOut) -> dict[str, Any]:
    """Lo que la consola y el panel añaden a cada fila de la lista (075):
    los dos pintan «Editar» con la misma regla (9.3)."""
    system = system_template_for(tpl.name, tpl.language)
    return {
        "edit_blocker": edit_blocker(tpl),
        "draft": draft_of(tpl),
        "version": template_version(tpl),
        "system_variables": (
            {"mode": system.mode, "variables": list(system.variables)} if system else None
        ),
    }
