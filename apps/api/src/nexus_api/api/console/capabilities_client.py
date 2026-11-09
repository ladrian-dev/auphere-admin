"""``/console/clients/{ref}/capabilities`` — lo que el agente sabe hacer.

Spec 017 (R5). Funde en una sola lectura las herramientas del catálogo y las
habilidades del bundle, que el partner no distingue y no tiene por qué:
`booking.create` no le dice nada, «Reservar una cita» sí.

Lo que este módulo decide, y por qué:

- **Agrupa por función**, no por conector ni por tipo. La pregunta del
  partner es «¿sabe coger citas?», no «¿esto es una herramienta o una
  habilidad?».
- **Filtra por el sector del cliente** y dice cuántas esconde, para que
  «Ver todas» sea una elección informada y no un salto a ciegas.
- **Un cambio por llamada.** La pantalla vieja mandaba la lista blanca
  entera en cada guardado: dos personas editando a la vez se pisaban sin
  enterarse. Aquí se nombra la capacidad y lo que cambia de ella, y el resto
  de la lista no se toca.
- **Encender algo sin su integración vale** (owner, 2026-09-26). Se devuelve
  `usable: false` y la pantalla lo dice; bloquearlo castigaría al partner por
  un orden que no eligió.
- **«Requiere aprobación» se retira** (R5.7): hoy se comporta como un bloqueo
  y engaña a quien lo elige. Pedirlo es 422.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Any, Literal

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    Agent,
    AgentStatus,
    Channel,
    ChannelStatus,
    ChannelType,
    Connector,
    ConnectorToolMode,
    TenantConnector,
    TenantConnectorStatus,
    TenantConnectorToolOverride,
    ToolCatalog,
    ToolStatus,
)
from nexus_api.repositories.audit import AuditRepository
from nexus_api.services.activations import needs_connector
from nexus_api.services.agent_spec.retired import SYSTEM_ONLY_PREFIX
from nexus_api.services.agents import principal_agent_id
from nexus_api.services.connectors import service as connector_service
from nexus_api.services.connectors.booking_skills import _BOOKS
from nexus_api.services.skills_catalog import list_skills
from nexus_api.services.templating.seed_templates import load_seed_template

from .agent_drafts import DraftView, draft_written, ensure_draft, load_view
from .capability_names import (
    FUNCTIONS,
    TOOL_ACTIONS,
    business_name,
    description_of,
    function_of,
    requires_connector,
    sectors_of,
)
from .deps import ClientScope, agent_scope, client_sector
from .schemas_capabilities_client import (
    CapabilitiesOut,
    CapabilityConnectorOut,
    CapabilityGroupOut,
    CapabilityMode,
    CapabilityModeOut,
    CapabilityOut,
    CapabilityTechnicalOut,
    CapabilityUpdatedOut,
    CapabilityUpdateIn,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/clients/{ref}/capabilities")

_CONNECTED = frozenset({TenantConnectorStatus.CONNECTED.value, TenantConnectorStatus.PARTIAL.value})
#: Los dos modos que quedan en pantalla. El tercero (`needs_approval`) sigue
#: existiendo en la base para versiones antiguas, pero no se ofrece.
_MODES: tuple[CapabilityMode, ...] = ("always", "blocked")


def _mode(value: str | None) -> CapabilityMode:
    """Un modo antiguo `needs_approval` se lee como lo que de verdad hace:
    bloquear (R5.7). Así una versión vieja muestra su modo efectivo real en
    vez de un nombre que ya no ofrecemos."""
    return "always" if value == "always" else "blocked"


async def _enabled_skill_ids(view: DraftView) -> tuple[set[str], set[str]]:
    def ids(cfg: Any) -> set[str]:
        if cfg is None or not cfg.runtime_skills:
            return set()
        return {str(s.get("skill_id")) for s in cfg.runtime_skills if s.get("skill_id")}

    return ids(view.target), ids(view.active)


async def _recommended(sector: str | None) -> set[str]:
    """Lo que la plantilla del sector enciende por defecto (R5.3). Si la
    plantilla no se puede cargar, nadie es «recomendada»: es mejor no decir
    nada que decir algo falso."""
    if not sector:
        return set()
    for name in (f"{sector}_v1", sector):
        try:
            return set(load_seed_template(name).tools_required or [])
        except Exception:
            continue
    return set()


async def _rows(scope: ClientScope) -> list[sa.Row[Any]]:
    stmt = (
        sa.select(ToolCatalog, Connector.slug, Connector.display_name, TenantConnector.status)
        .select_from(ToolCatalog)
        .outerjoin(Connector, Connector.id == ToolCatalog.connector_id)
        .outerjoin(TenantConnector, TenantConnector.connector_id == Connector.id)
        .where(
            ToolCatalog.status.notin_([ToolStatus.INTERNAL, ToolStatus.DEPRECATED]),
            # Las de Google Calendar nunca son de un agente (spec 043, R11.2).
            ToolCatalog.name.notlike(f"{SYSTEM_ONLY_PREFIX}%"),
        )
        .order_by(ToolCatalog.name)
    )
    return list((await scope.session.execute(stmt)).all())


async def _overrides(scope: ClientScope) -> dict[str, str]:
    rows = (await scope.session.scalars(sa.select(TenantConnectorToolOverride))).all()
    return {r.tool_name: r.mode for r in rows}


#: Spec 022: la dependencia no es un conector sino que **algún número vivo
#: tenga catálogo enlazado**. Sin él, la capacidad no se enseña (R3.2): no
#: hay botón apagado que explique lo que no tienes.
CHANNEL_CATALOG = "channel_catalog"


async def tenant_has_catalog(session: AsyncSession) -> bool:
    return bool(
        await session.scalar(
            sa.select(sa.func.count())
            .select_from(Channel)
            .where(
                Channel.type == ChannelType.WHATSAPP,
                Channel.status == ChannelStatus.ACTIVE,
                Channel.config["catalog_id"].astext.isnot(None),
            )
        )
    )


async def _connector_by_slug(scope: ClientScope, slug: str) -> tuple[str, str] | None:
    """(nombre visible, estado) de una integración que el catálogo no enlaza
    por `connector_id` (``requires`` en ``capability_names``). Sin fila de
    conector no hay nada conectado: la pantalla avisa de que falta."""
    display = (
        await scope.session.execute(
            sa.select(Connector.display_name).where(Connector.slug == slug).limit(1)
        )
    ).scalar_one_or_none()
    # La dependencia la dice el código de la herramienta, no el catálogo: si
    # la ficha del conector no está sembrada en este entorno, se nombra por
    # su slug antes que callar que hace falta.
    return display or slug, "none"


async def _all_capabilities(
    scope: ClientScope, view: DraftView, sector: str | None, lang: str
) -> list[CapabilityOut]:
    enabled_tools = set(view.target.tools or []) if view.target else set()
    active_tools = set(view.active.tools or []) if view.active else set()
    on_skills, on_skills_active = await _enabled_skill_ids(view)
    overrides = await _overrides(scope)
    recommended = await _recommended(sector)

    items: list[CapabilityOut] = []

    for tool, slug, display_name, install_status in await _rows(scope):
        tags = list(tool.capability_tags or [])
        connected = install_status in _CONNECTED
        # Una herramienta puede necesitar una integración que el catálogo no
        # enlaza (el catálogo de Meta del canal, por ejemplo). Sin esto la
        # pantalla la daría por utilizable y mentiría.
        if slug is None:
            needed = requires_connector(tool.name, "tool")
            if needed == CHANNEL_CATALOG:
                if not await tenant_has_catalog(scope.session):
                    continue
                slug = CHANNEL_CATALOG
                display_name = "Catálogo de Meta" if lang == "es" else "Meta catalogue"
                install_status = "connected"
                connected = True
            elif needed:
                found = await _connector_by_slug(scope, needed)
                if found:
                    slug, display_name = needed, found[0]
                    install_status = found[1]
                    connected = install_status in _CONNECTED
        override = overrides.get(tool.name)
        default = _mode(tool.default_mode)
        enabled = tool.name in enabled_tools
        items.append(
            CapabilityOut(
                key=tool.name,
                kind="tool",
                business_name=business_name(tool.name, "tool", lang),
                description=description_of(tool.name, "tool", lang) or tool.description or "",
                function=function_of(tool.name, "tool"),
                sectors=sectors_of(tool.name, "tool", tags),
                recommended=tool.name in recommended,
                enabled=enabled,
                enabled_in_active=tool.name in active_tools,
                usable=enabled and (slug is None or connected),
                connector=(
                    CapabilityConnectorOut(
                        slug=slug,
                        display_name=display_name or slug,
                        status=install_status or "none",
                    )
                    if slug is not None
                    else None
                ),
                mode=CapabilityModeOut(
                    default=default,
                    override=_mode(override) if override else None,
                    effective=_mode(override) if override else default,
                    options=list(_MODES),
                ),
                read_only=tool.read_only,
                destructive=tool.destructive,
                technical=CapabilityTechnicalOut(name=tool.name, kind="tool", tags=tags),
            )
        )

    for skill in list_skills():
        sid = skill.skill_id
        enabled = bool(sid and sid in on_skills)
        items.append(
            CapabilityOut(
                key=skill.name,
                kind="skill",
                business_name=business_name(skill.name, "skill", lang),
                description=description_of(skill.name, "skill", lang) or skill.description or "",
                function=function_of(skill.name, "skill"),
                sectors=sectors_of(skill.name, "skill", None),
                enabled=enabled,
                enabled_in_active=bool(sid and sid in on_skills_active),
                # Una habilidad no depende de un conector, pero sí puede no
                # ser activable todavía en este despliegue.
                usable=enabled and skill.activatable,
                activatable=skill.activatable,
                # Las habilidades no tienen modo: no se inventa una columna
                # vacía para que la tabla quede simétrica.
                mode=None,
                technical=CapabilityTechnicalOut(
                    name=skill.name,
                    kind="skill",
                    version=skill.uploaded_version or skill.local_version,
                ),
            )
        )
    return items


def _group(items: list[CapabilityOut]) -> list[CapabilityGroupOut]:
    """En el orden en que se leen, y sin grupos vacíos: un encabezado sin
    nada debajo es ruido."""
    return [
        CapabilityGroupOut(function=f, items=[i for i in items if i.function == f])
        for f in FUNCTIONS
        if any(i.function == f for i in items)
    ]


@router.get("", response_model=CapabilitiesOut)
async def list_capabilities(
    q: str | None = Query(default=None, max_length=120),
    all: bool = Query(default=False),
    lang: str = Query(default="es", pattern="^(es|en)$"),
    scope: ClientScope = Depends(agent_scope("agents:read")),
) -> CapabilitiesOut:
    view = await load_view(scope)
    sector = await client_sector(scope.session)
    items = await _all_capabilities(scope, view, sector, lang)

    def del_sector(i: CapabilityOut) -> bool:
        return not i.sectors or (sector is not None and sector in i.sectors)

    hidden = 0
    if sector is not None and not all:
        antes = len(items)
        items = [i for i in items if del_sector(i)]
        hidden = antes - len(items)
    elif sector is not None and all:
        for i in items:
            i.other_sector = not del_sector(i)

    if q:
        needle = q.strip().lower()
        items = [i for i in items if needle in f"{i.business_name} {i.description}".lower()]

    return CapabilitiesOut(
        sector=sector,
        has_draft=view.has_draft,
        version=view.target.version if view.target else None,
        active_version=view.active.version if view.active else None,
        hidden_by_sector=hidden,
        groups=_group(items),
    )


#: Lo que una prueba comprueba en su ``expected_state``, y las herramientas que lo
#: hacen: la agenda de Auphere o, sin Reservas, Calendly (``booking_skills``).
_STATE_TOOLS = {"booking": frozenset({"reservas.create", *_BOOKS})}

#: Por qué no se puede apagar: una tarea la nombra, una prueba espera lo que solo ella
#: hace, o el texto promete lo que solo ella cumple.
InUse = Literal["task", "test", "promise"]

#: Las que caben en un AgentSpec (``agent_spec.schema``). Se comprueba antes de validar
#: para poder decirlo con palabras: el validador solo devuelve el error del esquema.
_MAX_SPEC_TOOLS = 60


def _keeps_a_promise(spec: Any, key: str, on: set[str]) -> bool:
    """La revisión bloquea al agente estructurado cuyo texto promete lo que ninguna
    herramienta hace (65.5). En uno de antes solo avisa, así que no se le niega nada."""
    from nexus_api.services.agent_spec.missing import from_promises

    if spec.mode != "structured" or key not in TOOL_ACTIONS:
        return False
    with_it = from_promises(spec.model_copy(update={"tools": sorted(on)}))
    without = from_promises(spec.model_copy(update={"tools": sorted(on - {key})}))
    return bool({m.key for m in without} - {m.key for m in with_it})


async def tools_in_use(
    scope: ClientScope, spec: Any, target: Any, keys: Iterable[str]
) -> dict[str, InUse]:
    """¿Apagarlas dejaría al agente sin poder hacer lo que promete? Las de ``keys``
    que sí, y por qué. Lo que otra de las encendidas también hace no depende de ella."""
    from nexus_api.services.testing.suites import get_suite, list_tests

    on = {*(spec.tools or []), *((target.tools or []) if target is not None else [])}
    tasks = {name for proc in spec.procedures or [] for name in proc.tools or []}
    expected: set[str] | None = None
    out: dict[str, InUse] = {}
    for key in keys:
        if key in tasks:
            out[key] = "task"
            continue
        states = {
            state
            for state, tools in _STATE_TOOLS.items()
            if key in tools and not tools & (on - {key})
        }
        if states and target is not None:
            if expected is None:
                suite = await get_suite(scope.session, target.agent_id)
                tests = await list_tests(scope.session, suite) if suite is not None else []
                expected = {
                    state
                    for test in tests
                    # Las del sector aplican según las herramientas: contarlas sería un
                    # candado circular, encender lo único que reserva impediría apagarlo.
                    if not test.not_applicable_reason and test.kind != "sector"
                    for state in (test.expected_state or {})
                }
            if states & expected:
                out[key] = "test"
                continue
        if _keeps_a_promise(spec, key, on):
            out[key] = "promise"
    return out


async def _refuse_if_in_use(scope: ClientScope, spec: Any, target: Any, key: str) -> None:
    why = (await tools_in_use(scope, spec, target, [key])).get(key)
    if why is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "tool_in_use", "locked_by": why},
        )


async def _set_spec_tool(scope: ClientScope, key: str, *, enabled: bool) -> bool:
    """D79 (65.10): an agent with a structured AgentSpec changes its tools through
    that document and the validator, like ``PATCH …/draft``. ``write_spec``
    recompiles the prompt and leaves ``draft.tools`` equal to the document. What we
    do not have is dropped and noted (65.3), never written. Returns whether the tool
    was on before.

    What connecting turned on can be on the draft's list and not in the document
    (``auto_enable_connector_tools``): for the screen it is on, so one switch neither
    misses it nor takes the others with it."""
    return key in await _set_spec_tools(scope, [key], enabled=enabled)


async def _set_spec_tools(
    scope: ClientScope,
    keys: Sequence[str],
    *,
    enabled: bool,
    check_in_use: bool = True,
) -> set[str]:
    """:func:`_set_spec_tool` for several at once: one validation and one write. Spec
    057 (2.2 y 2.5): the agenda goes in and out whole. Switching off also takes the
    names out of ``procedures[].tools`` so the AgentSpec still validates; the words of
    those procedures change with the builder's proposal (requirement 3), not here.
    ``check_in_use=False`` (the agenda): what a task uses goes too. Returns the keys
    that were on before."""
    from nexus_api.services.agent_spec import missing
    from nexus_api.services.agent_spec.schema import dump
    from nexus_api.services.agent_spec.validator import (
        load_context,
        problems_out,
        validate_spec,
    )

    from .agent_spec_drafts import current_spec, write_spec

    spec, _target = await current_spec(scope)
    assert spec is not None
    tools = list(spec.tools or [])
    listed = list(_target.tools or []) if _target is not None else []
    was = {k for k in keys if k in tools or k in listed}
    changing = [k for k in dict.fromkeys(keys) if (k in was) != enabled]
    if not changing:
        return was
    if not enabled and check_in_use:
        for key in changing:
            await _refuse_if_in_use(scope, spec, _target, key)
    gone = set(changing)
    wanted = (
        list(dict.fromkeys([*tools, *changing])) if enabled else [t for t in tools if t not in gone]
    )
    if len(wanted) > _MAX_SPEC_TOOLS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "too_many_tools", "max": _MAX_SPEC_TOOLS},
        )
    outside = [t for t in listed if t not in tools and t not in keys and needs_connector(t)]
    doc = dump(spec)
    if not enabled:
        for proc in doc.get("procedures") or []:
            if proc.get("tools"):
                kept = [t for t in proc["tools"] if t not in gone]
                if kept:
                    proc["tools"] = kept
                else:
                    proc.pop("tools", None)
    ctx = await load_context(
        scope.session, partner_id=scope.principal.partner.id, agent_id=scope.agent_id
    )
    # Si lo de fuera no cabe en el documento, manda el documento, como en cualquier
    # otra escritura: el cambio que se pidió no se rechaza por algo que no se pidió.
    for names in ([*wanted, *outside], wanted) if outside else (wanted,):
        doc["tools"] = names
        cleaned, lacking = missing.strip_doc(doc, ctx)
        checked, problems = validate_spec(cleaned, ctx, author="person")
        if checked is not None and not problems:
            break
    if checked is None or problems:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "spec_invalid", "problems": problems_out(problems)},
        )
    await write_spec(scope, checked, expected_revision=None, lacking=lacking)
    return was


async def set_agent_tools(scope: ClientScope, keys: Sequence[str], *, enabled: bool) -> set[str]:
    """Spec 057 (2.2, 2.5 y 2.7): several tools on or off in the agent's draft at once,
    whatever its mode. A structured AgentSpec goes through :func:`_set_spec_tools`; an
    «instructions» agent changes its version's list, as the switches of Capacidades
    do. Returns the keys that were on before."""
    from nexus_api.services.testing.suites import mark_stale

    draft, _created = await ensure_draft(scope)
    if draft.spec and draft.spec.get("mode") == "structured":
        return await _set_spec_tools(scope, keys, enabled=enabled, check_in_use=False)
    names = list(draft.tools or [])
    was = {k for k in keys if k in names}
    if enabled:
        after = list(dict.fromkeys([*names, *keys]))
    else:
        gone = set(keys)
        after = [n for n in names if n not in gone]
    if after != names:
        if len(after) > _MAX_SPEC_TOOLS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "too_many_tools", "max": _MAX_SPEC_TOOLS},
            )
        draft.tools = after
        await mark_stale(scope.session, draft.agent_id)
        await draft_written(scope, draft)
    return was


#: Lo que necesita un agente para enseñar un producto: buscarlo, leer su ficha y
#: mandar la tarjeta, que sale por ``response.send_interactive`` (INC-71).
CATALOG_SKILLS = ("catalog.search_products", "catalog.get_product", "response.send_interactive")


async def enable_catalog_skills(scope: ClientScope, agent_id: uuid.UUID | None) -> list[str]:
    """Al conectar un catálogo, sus habilidades se encienden solas en el borrador
    del agente de ese número. Publicar sigue siendo un paso aparte. Devuelve las
    que encendió. Nunca rompe el enlace: el catálogo ya está conectado, y lo que no
    se pudo encender sigue en Habilidades."""
    from .agent_draft_routes import is_structured

    agent_id = agent_id or await principal_agent_id(scope.session)
    agent = await scope.session.get(Agent, agent_id) if agent_id is not None else None
    if agent is None or agent.status != AgentStatus.ACTIVE.value:
        return []
    target = replace(scope, agent_id=agent.id)
    view = await load_view(target)
    enabled = set(view.target.tools or []) if view.target else set()
    offered = set(
        await scope.session.scalars(
            sa.select(ToolCatalog.name).where(
                ToolCatalog.name.in_(CATALOG_SKILLS),
                ToolCatalog.status.notin_([ToolStatus.INTERNAL, ToolStatus.DEPRECATED]),
            )
        )
    )
    missing = [key for key in CATALOG_SKILLS if key in offered and key not in enabled]
    if not missing:
        return []
    try:
        async with scope.session.begin_nested():
            draft, _created = await ensure_draft(target)
            if is_structured(draft):
                for key in missing:
                    await _set_spec_tool(target, key, enabled=True)
            else:
                draft.tools = [*(draft.tools or []), *missing]
                await draft_written(target, draft)
            added = [key for key in missing if key in (draft.tools or [])]
            await AuditRepository(scope.session).record(
                actor=scope.principal.actor,
                action="console.capability.update",
                target=f"agent:{agent.id}",
                before=None,
                after={"catalog_skills": added},
            )
    except Exception as exc:
        log.warning("channel.catalog.skills_failed", agent_id=str(agent.id), error=str(exc))
        return []
    return added


@router.put(
    "",
    response_model=CapabilityUpdatedOut,
    responses={
        404: {"description": "No such capability."},
        422: {"description": "Unsupported mode."},
    },
)
async def update_capability(
    body: CapabilityUpdateIn,
    scope: ClientScope = Depends(agent_scope("agents:write")),
) -> CapabilityUpdatedOut:
    """Un cambio, uno solo. El resto de la lista no se toca (R5.4)."""
    if body.enabled is None and body.mode is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="nothing_to_change"
        )

    # Se comprueba **antes** de escribir, y con el mismo filtro que la
    # lectura: lo que la pantalla esconde (`INTERNAL`, `DEPRECATED`) no se
    # puede encender a través de ella. Hacerlo después dejaba el rechazo en
    # manos del rollback, y por el camino ya había borrador y fila de
    # auditoría de un cambio que no ocurrió.
    if body.kind == "tool":
        offered = await scope.session.scalar(
            sa.select(ToolCatalog.name)
            .where(
                ToolCatalog.name == body.key,
                ToolCatalog.status.notin_([ToolStatus.INTERNAL, ToolStatus.DEPRECATED]),
            )
            .limit(1)
        )
        if offered is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_capability")

    draft, created = await ensure_draft(scope)
    before: dict[str, Any] = {}
    spec_written = False

    if body.enabled is not None:
        if body.kind == "tool" and draft.spec and draft.spec.get("mode") == "structured":
            before["enabled"] = await _set_spec_tool(scope, body.key, enabled=body.enabled)
            spec_written = True
        elif body.kind == "tool":
            names = list(draft.tools or [])
            before["enabled"] = body.key in names
            if body.enabled and body.key not in names:
                names.append(body.key)
            elif not body.enabled and body.key in names:
                # Lo mismo que un agente estructurado: lo que usa no se apaga, y lo
                # que cambia deja sus pruebas desactualizadas.
                from .agent_spec_drafts import current_spec

                spec, target = await current_spec(scope)
                if spec is not None:
                    await _refuse_if_in_use(scope, spec, target, body.key)
                names.remove(body.key)
            draft.tools = names
            if before["enabled"] != body.enabled:
                from nexus_api.services.testing.suites import mark_stale

                await mark_stale(scope.session, draft.agent_id)
        else:
            catalogue = {s.name: s for s in list_skills()}
            skill = catalogue.get(body.key)
            if skill is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="unknown_capability"
                )
            if skill.skill_id is None:
                # Existe y se sabe cuál es: lo que falta es que Auphere la
                # haya subido al workspace. Decir «no existe» era mentir, y
                # mandaba a buscar el error donde no estaba.
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="skill_not_published"
                )
            entries = [dict(s) for s in (draft.runtime_skills or [])]
            before["enabled"] = any(str(s.get("skill_id")) == skill.skill_id for s in entries)
            if body.enabled and not before["enabled"]:
                entries.append(
                    {"skill_id": skill.skill_id, "version": skill.uploaded_version or "latest"}
                )
            elif not body.enabled:
                entries = [s for s in entries if str(s.get("skill_id")) != skill.skill_id]
            draft.runtime_skills = entries or None

    if body.mode is not None:
        # R5.7: se retira de la pantalla y también de la puerta. Aceptarlo
        # en el tipo y rechazarlo aquí es lo que permite decir por qué.
        if body.mode == "needs_approval":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="mode_not_supported"
            )
        if body.kind != "tool":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="mode_not_supported"
            )
        if body.mode == "default":
            # Volver al defecto es **borrar** lo fijado, no guardar el valor
            # por defecto como si se hubiera elegido. Si no había nada fijado
            # ya estábamos donde se pedía: es un no-op, no un 404.
            await connector_service.delete_override(
                scope.session,
                tenant=scope.tenant,
                tool_name=body.key,
                actor=scope.principal.actor,
            )
        else:
            await connector_service.upsert_override(
                scope.session,
                tenant=scope.tenant,
                tool_name=body.key,
                mode=ConnectorToolMode(body.mode),
                reason=None,
                actor=scope.principal.actor,
            )

    if not spec_written:
        await draft_written(scope, draft)
    await AuditRepository(scope.session).record(
        actor=scope.principal.actor,
        action="console.capability.update",
        target=f"capability:{body.key}",
        before=before or None,
        # El agente: lo que una persona apaga en uno no se vuelve a encender solo
        # (``connector_service.switched_off_by_a_person``).
        after={
            "key": body.key,
            "kind": body.kind,
            "enabled": body.enabled,
            "mode": body.mode,
            "agent_id": str(draft.agent_id),
        },
    )

    view = await load_view(scope)
    sector = await client_sector(scope.session)
    items = await _all_capabilities(scope, view, sector, "es")
    updated = next((i for i in items if i.key == body.key and i.kind == body.kind), None)
    if updated is None:  # pragma: no cover — lo habría cazado el 404 de arriba
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_capability")
    return CapabilityUpdatedOut(
        capability=updated,
        draft_created=created,
        version=view.target.version if view.target else None,
    )


__all__ = ["router"]
