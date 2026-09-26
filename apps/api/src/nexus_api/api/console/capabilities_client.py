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

from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status

from nexus_api.db.models import (
    Connector,
    ConnectorToolMode,
    TenantConnector,
    TenantConnectorStatus,
    TenantConnectorToolOverride,
    ToolCatalog,
    ToolStatus,
)
from nexus_api.repositories.audit import AuditRepository
from nexus_api.services.connectors import service as connector_service
from nexus_api.services.skills_catalog import list_skills
from nexus_api.services.templating.seed_templates import load_seed_template

from .agent_drafts import DraftView, ensure_draft, load_view
from .capability_names import FUNCTIONS, business_name, description_of, function_of, sectors_of
from .deps import ClientScope, client_scope, client_sector
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
        .where(ToolCatalog.status.notin_([ToolStatus.INTERNAL, ToolStatus.DEPRECATED]))
        .order_by(ToolCatalog.name)
    )
    return list((await scope.session.execute(stmt)).all())


async def _overrides(scope: ClientScope) -> dict[str, str]:
    rows = (await scope.session.scalars(sa.select(TenantConnectorToolOverride))).all()
    return {r.tool_name: r.mode for r in rows}


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
    scope: ClientScope = Depends(client_scope("agents:read")),
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
    scope: ClientScope = Depends(client_scope("agents:write")),
) -> CapabilityUpdatedOut:
    """Un cambio, uno solo. El resto de la lista no se toca (R5.4)."""
    if body.enabled is None and body.mode is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="nothing_to_change"
        )

    draft, created = await ensure_draft(scope)
    before: dict[str, Any] = {}

    if body.enabled is not None:
        if body.kind == "tool":
            names = list(draft.tools or [])
            before["enabled"] = body.key in names
            exists = await scope.session.scalar(
                sa.select(ToolCatalog.name).where(ToolCatalog.name == body.key).limit(1)
            )
            if exists is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="unknown_capability"
                )
            if body.enabled and body.key not in names:
                names.append(body.key)
            elif not body.enabled and body.key in names:
                names.remove(body.key)
            draft.tools = names
        else:
            catalogue = {s.name: s for s in list_skills()}
            skill = catalogue.get(body.key)
            if skill is None or skill.skill_id is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="unknown_capability"
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
        await connector_service.upsert_override(
            scope.session,
            tenant=scope.tenant,
            tool_name=body.key,
            mode=ConnectorToolMode(body.mode),
            reason=None,
            actor=scope.principal.actor,
        )

    await scope.session.flush()
    await AuditRepository(scope.session).record(
        actor=scope.principal.actor,
        action="console.capability.update",
        target=f"capability:{body.key}",
        before=before or None,
        after={"key": body.key, "kind": body.kind, "enabled": body.enabled, "mode": body.mode},
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
