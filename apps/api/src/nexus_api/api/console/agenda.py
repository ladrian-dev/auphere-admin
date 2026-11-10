"""«Agenda (Reservas)» de un agente — spec 057, requisitos 2, 3, 4.4 y 7
(``contracts/console-api.md`` §3 a §5).

- ``GET /clients/{ref}/agents/{agent_id}/agenda`` [``agents:read``]: si se ofrece, el
  módulo y su modo, si está listo y qué falta, la agenda en el borrador y en lo
  publicado, la propuesta de texto y el trabajo que la escribe.
- ``PUT …/agenda`` [``agents:write``] ``{enabled, reservas?}``: enciende Reservas para el
  cliente si hace falta (``reservations.turn_on``), pone o quita las nueve de una vez en
  el borrador (``capabilities_client.set_agent_tools``) y, en un agente estructurado,
  encola la propuesta de texto (trabajo ``agenda_text``). Nunca apaga el módulo ni toca
  reservas: eso es de Acceso (7.4).
- ``GET …/agenda/tools?lang=``: las nueve, con la forma de ``ConnectorToolsOut`` para el
  diálogo «Qué puede hacer». Encender o apagar una sigue siendo ``PUT …/capabilities``.

La agenda no es un conector: no tiene conexión, permiso ni ajustes (``research.md`` R2).
El cliente sale de la ruta y de la sesión; ningún cuerpo lleva ``tenant_id`` (7.3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, cast

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from nexus_api.db.models import AuditLog, Job, ReservationSettings
from nexus_api.db.models.agent_spec import Proposal
from nexus_api.services import jobs as jobs_service
from nexus_api.services.builder.agenda_text import JOB_KIND
from nexus_api.services.reservations import passing
from nexus_api.services.reservations.admin import Choice, ReservasChoiceError
from nexus_api.services.reservations.turn_on import (
    TurnOnRefused,
    suggested_choice,
    turn_on_from_agent,
)

from .agent_builder import agenda_offered
from .agent_draft_routes import agent_in_path
from .agent_drafts import load_view
from .agent_integrations import ConnectorToolOut, ConnectorToolsOut
from .agent_spec_drafts import current_spec
from .capabilities_client import _MAX_SPEC_TOOLS, set_agent_tools, tools_in_use
from .capability_names import business_name, description_of
from .deps import ClientScope, require_build_room
from .schemas_agent_builder import CapacityKind, ReservasChoiceIn, ReservasMode

log = structlog.get_logger(__name__)

router = APIRouter()

#: Lo que solo consulta: lo demás cambia algo en la agenda.
READS: frozenset[str] = frozenset(
    {"reservas.services", "reservas.find_slots", "reservas.list_mine"}
)
NotReadyCode = Literal[
    "reservas_off",
    "hours_missing",
    "no_staff",
    "no_services",
    "no_bookable_service",
    "no_capacity",
]


class AgendaModuleOut(BaseModel):
    on: bool
    mode: ReservasMode | None = None
    capacity_kind: CapacityKind | None = None


class AgendaDraftOut(BaseModel):
    on: bool
    tools_on: int


class AgendaPublishedOut(BaseModel):
    on: bool


class AgendaProposalOut(BaseModel):
    id: str
    status: Literal["open", "applied", "rejected", "expired", "stale"]


class AgendaJobOut(BaseModel):
    id: str
    status: Literal["queued", "running", "done", "failed"]


class AgendaChoiceOut(BaseModel):
    mode: ReservasMode
    capacity_kind: CapacityKind | None = None


class AgendaOut(BaseModel):
    offered: bool
    module: AgendaModuleOut
    ready: bool
    missing: list[NotReadyCode]
    draft: AgendaDraftOut
    published: AgendaPublishedOut
    state: Literal["none", "prepared", "on"]
    structured: bool
    proposal: AgendaProposalOut | None = None
    job: AgendaJobOut | None = None
    suggested: AgendaChoiceOut
    can_write: bool
    max_tools: int = _MAX_SPEC_TOOLS
    #: Solo en la respuesta del ``PUT``: por qué no hay propuesta de texto.
    proposal_reason: Literal["build_budget_exhausted", "not_structured"] | None = None


class AgendaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    reservas: ReservasChoiceIn | None = None


def _has_agenda(tools: Any) -> bool:
    return "reservas.create" in (tools or [])


async def agenda_out(scope: ClientScope) -> AgendaOut:
    """El estado de la agenda del agente de la ruta. Bajo la RLS del cliente."""
    assert scope.agent_id is not None
    session = scope.session
    tenant_id = scope.tenant.id
    module_on = await passing.reservas_enabled(session, tenant_id)
    settings = await session.get(ReservationSettings, tenant_id) if module_on else None
    reasons = (
        await passing.not_ready(session, tenant_id, now=datetime.now(UTC))
        if module_on
        else ["reservas_off"]
    )
    view = await load_view(scope)
    target_tools = list(view.target.tools or []) if view.target else []
    active_tools = list(view.active.tools or []) if view.active else []
    draft_on = _has_agenda(target_tools)
    published_on = _has_agenda(active_tools)
    state: Literal["none", "prepared", "on"] = (
        "on"
        if published_on and (view.draft is None or draft_on)
        else "prepared"
        if view.draft is not None and draft_on and not published_on
        else "none"
    )
    structured = bool(
        view.target and view.target.spec and view.target.spec.get("mode") == "structured"
    )
    proposal = (
        await session.scalars(
            sa.select(Proposal)
            .where(
                Proposal.agent_id == scope.agent_id,
                Proposal.author == "builder",
                Proposal.job_id.in_(sa.select(Job.id).where(Job.kind == JOB_KIND)),
            )
            .order_by(Proposal.created_at.desc())
            .limit(1)
        )
    ).first()
    job = (
        await session.scalars(
            sa.select(Job)
            .where(
                Job.agent_id == scope.agent_id,
                Job.kind == JOB_KIND,
                Job.status.in_(("queued", "running")),
            )
            .order_by(Job.created_at.desc())
            .limit(1)
        )
    ).first()
    proposal_status = proposal.status if proposal is not None else None
    if (
        proposal is not None
        and proposal_status == "open"
        and proposal.expires_at < datetime.now(UTC)
    ):
        proposal_status = "expired"
    suggested = await suggested_choice(session)
    return AgendaOut(
        offered=agenda_offered(scope),
        module=AgendaModuleOut(
            on=module_on,
            mode=cast(Any, settings.mode) if settings else None,
            capacity_kind=cast(Any, settings.capacity_kind) if settings else None,
        ),
        ready=not reasons,
        missing=cast(Any, reasons),
        draft=AgendaDraftOut(
            on=draft_on, tools_on=sum(1 for t in passing.RESERVAS_TOOLS if t in target_tools)
        ),
        published=AgendaPublishedOut(on=published_on),
        state=state,
        structured=structured,
        proposal=AgendaProposalOut(id=str(proposal.id), status=cast(Any, proposal_status))
        if proposal is not None
        else None,
        job=AgendaJobOut(id=str(job.id), status=cast(Any, job.status)) if job is not None else None,
        suggested=AgendaChoiceOut(
            mode=cast(Any, suggested.mode), capacity_kind=cast(Any, suggested.capacity_kind)
        ),
        can_write="agents:write" in scope.principal.permissions,
    )


async def _queued(scope: ClientScope) -> bool:
    """¿Hay un trabajo de la propuesta de este agente esperando a empezar?"""
    return bool(
        await scope.session.scalar(
            sa.select(sa.func.count())
            .select_from(Job)
            .where(Job.agent_id == scope.agent_id, Job.kind == JOB_KIND, Job.status == "queued")
        )
    )


async def _may_ask_again(scope: ClientScope) -> bool:
    """¿Se puede volver a pedir la propuesta? Sin trabajo en curso ni propuesta abierta y
    viva: así repetir el ``PUT`` no encola trabajos de más (cada uno gasta modelo)."""
    running = await scope.session.scalar(
        sa.select(sa.func.count())
        .select_from(Job)
        .where(
            Job.agent_id == scope.agent_id,
            Job.kind == JOB_KIND,
            Job.status.in_(("queued", "running")),
        )
    )
    if running:
        return False
    open_ = await scope.session.scalar(
        sa.select(sa.func.count())
        .select_from(Proposal)
        .where(
            Proposal.agent_id == scope.agent_id,
            Proposal.author == "builder",
            Proposal.status == "open",
            Proposal.expires_at > datetime.now(UTC),
            Proposal.job_id.in_(sa.select(Job.id).where(Job.kind == JOB_KIND)),
        )
    )
    return not open_


def _error(code: str, status_code: int, **info: Any) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, **info})


@router.get("/clients/{ref}/agents/{agent_id}/agenda", response_model=AgendaOut)
async def get_agenda(scope: ClientScope = Depends(agent_in_path("agents:read"))) -> AgendaOut:
    return await agenda_out(scope)


@router.put("/clients/{ref}/agents/{agent_id}/agenda", response_model=AgendaOut)
async def put_agenda(
    body: AgendaIn,
    scope: ClientScope = Depends(agent_in_path("agents:write")),
) -> AgendaOut:
    """Activa o desactiva la agenda del agente (2.2 a 2.7) y pide su propuesta (3)."""
    assert scope.agent_id is not None
    session = scope.session
    module_turned_on = False
    if body.enabled and not await passing.reservas_enabled(session, scope.tenant.id):
        choice = (
            Choice(mode=body.reservas.mode, capacity_kind=body.reservas.capacity_kind)
            if body.reservas is not None
            else None
        )
        try:
            turned = await turn_on_from_agent(
                session,
                tenant_id=scope.tenant.id,
                partner_id=scope.mapping.partner_id,
                choice=choice,
                actor=scope.principal.actor,
                origin_agent_id=scope.agent_id,
                now=datetime.now(UTC),
            )
        except ReservasChoiceError as exc:
            raise _error(exc.code, exc.status) from None
        except TurnOnRefused as exc:
            raise _error(exc.code, exc.status) from None
        module_turned_on = turned.turned_on

    was = await set_agent_tools(scope, passing.RESERVAS_TOOLS, enabled=body.enabled)
    changed = len(was) < len(passing.RESERVAS_TOOLS) if body.enabled else bool(was)
    # 3.5: «Reintentar» o «Pedir la propuesta» repiten el mismo cambio. Las herramientas
    # ya están así, pero si no hay trabajo en curso ni propuesta abierta (falló, caducó, se
    # aplicó o se descartó y el texto sigue igual), se vuelve a pedir.
    retry = not changed and await _may_ask_again(scope)

    reason: Literal["build_budget_exhausted", "not_structured"] | None = None
    if changed:
        session.add(
            AuditLog(
                tenant_id=scope.tenant.id,
                actor=scope.principal.actor,
                action="console.agenda.update",
                target=f"agent:{scope.agent_id}",
                after_json={
                    "agent_id": str(scope.agent_id),
                    "enabled": body.enabled,
                    "module_turned_on": module_turned_on,
                },
            )
        )
    # Como mucho uno en cola por agente: el que espera leerá el borrador al empezar, así que
    # cambiar varias veces seguidas no encola un trabajo (ni una llamada al modelo) por clic.
    changed_needs_job = changed and not await _queued(scope)
    if changed_needs_job or retry:
        view = await load_view(scope)
        structured = bool(
            view.target and view.target.spec and view.target.spec.get("mode") == "structured"
        )
        if not structured:
            reason = "not_structured"
        else:
            try:
                await require_build_room(scope.principal.partner.id)
            except HTTPException as exc:
                if exc.status_code != status.HTTP_402_PAYMENT_REQUIRED:
                    raise
                reason = "build_budget_exhausted"
            else:
                job = await jobs_service.create_job(
                    session,
                    kind=JOB_KIND,
                    agent_id=scope.agent_id,
                    created_by=scope.principal.user_id,
                )
                job.progress = {
                    "step": None,
                    "input": {
                        "agent_id": str(scope.agent_id),
                        "enabled": body.enabled,
                        "actor": scope.principal.actor,
                    },
                }
                await session.flush()
                jobs_service.enqueue_after_commit(session, job)
    out = await agenda_out(scope)
    out.proposal_reason = reason
    return out


@router.get("/clients/{ref}/agents/{agent_id}/agenda/tools", response_model=ConnectorToolsOut)
async def agenda_tools(
    lang: str = Query(default="es", pattern="^(es|en)$"),
    scope: ClientScope = Depends(agent_in_path("agents:read")),
) -> ConnectorToolsOut:
    """Las nueve de la agenda, para «Qué puede hacer» (2.4), con la forma del diálogo
    de un conector. Las que usa un procedimiento no se apagan (``locked``)."""
    view = await load_view(scope)
    spec, target = await current_spec(scope)
    enabled = set(view.target.tools or []) if view.target else set()
    active = set(view.active.tools or []) if view.active else set()
    names = list(passing.RESERVAS_TOOLS)
    in_use = (
        await tools_in_use(scope, spec, target, [t for t in names if t in enabled])
        if spec is not None
        else {}
    )
    tools: list[ConnectorToolOut] = []
    for name in names:
        why = in_use.get(name)
        tools.append(
            ConnectorToolOut(
                name=name,
                title=business_name(name, "tool", lang),
                description=(description_of(name, "tool", lang) or "")[:400],
                read_only=name in READS,
                enabled=name in enabled,
                enabled_in_active=name in active,
                locked=why is not None,
                locked_by=why,
                needs_write_permission=False,
                suggested=True,
            )
        )
    return ConnectorToolsOut(
        slug="reservas",
        name="Agenda (Reservas)",
        permission=None,
        tools=tools,
    )


__all__ = ["AgendaIn", "AgendaOut", "agenda_out", "router"]
