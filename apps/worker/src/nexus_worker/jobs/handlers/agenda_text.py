"""El trabajo ``agenda_text`` — spec 057, requisito 3 (T027).

Al activar o desactivar «Gestiona citas» en un agente estructurado ya creado, la API
cambia sus herramientas al momento y encola este trabajo, que escribe la propuesta de
cómo cambia su texto de citas (``services.builder.agenda_text``). Nada se aplica solo.

- El modelo es el del constructor (``role="build"``, ``NEXUS_LLM_BUILD_MODEL``), con el
  mismo plazo por llamada y el mismo tope de trabajo que ``agent_draft`` (270 s).
- Va dentro de ``usage_turn(source=SOURCE_BUILDER)``: cuenta en la partida de
  construcción del partner (``partner_build_budget``), nunca en la bolsa del cliente
  (3.6). La API ya miró que quedaba presupuesto al encolar (``require_build_room``).
- Sin modelo (local, ``llm_use_inmemory``) o si el proveedor no responde algo útil,
  el respaldo sin modelo (3.5); lo dice el resultado (``fallback``).

``progress.input``: ``{agent_id, enabled, actor}``. Nunca el texto del agente.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Job
from nexus_api.services.builder.agenda_text import JOB_KIND, propose_agenda_text
from nexus_api.services.builder.agent_draft import _partner_of

from nexus_worker.jobs.handlers.agent_draft import (
    BUILD_CALL_TIMEOUT_S,
    CompleteFactory,
    default_complete,
)
from nexus_worker.jobs.registry import (
    JobContext,
    JobFailed,
    JobHandler,
    JobOutcome,
    JobRegistry,
    default_registry,
)
from nexus_worker.metering.collector import SOURCE_BUILDER, usage_turn

log = structlog.get_logger(__name__)

KIND = JOB_KIND
#: El mismo tope que ``agent_draft``: una llamada del constructor y su validación.
TIMEOUT_S = 270.0


async def _input(ctx: JobContext) -> dict[str, Any]:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, ctx.tenant_id):
        job = await session.get(Job, ctx.job_id)
        raw = dict((job.progress or {}).get("input") or {}) if job is not None else {}
    return raw


async def _room_left(ctx: JobContext) -> bool:
    """¿Le queda partida de construcción al partner del cliente?"""
    from nexus_api.services.builder.agent_draft import _partner_of
    from nexus_api.services.wallet.bags import WalletError
    from nexus_api.services.wallet.build_budget import require_room_for_partner

    async with get_sessionmaker()() as session, tenant_scoped_session(session, ctx.tenant_id):
        partner_id = await _partner_of(session)
    if partner_id is None:
        return True
    try:
        await require_room_for_partner(partner_id)
    except WalletError:
        return False
    return True


def make_agenda_text_handler(*, complete_factory: CompleteFactory | None = None) -> JobHandler:
    make_complete = complete_factory or default_complete

    async def handle(ctx: JobContext) -> JobOutcome:
        data = await _input(ctx)
        try:
            agent_id = uuid.UUID(str(data.get("agent_id")))
        except ValueError as exc:
            raise JobFailed("bad_input") from exc
        enabled = bool(data.get("enabled"))
        actor = str(data.get("actor") or "builder")
        complete = make_complete(ctx.tenant_id)
        if complete is not None and not await _room_left(ctx):
            # La partida se miró al encolar; si se agotó mientras esperaba, sin modelo.
            complete = None
        async with (
            usage_turn(tenant_id=ctx.tenant_id, turn_id=f"job:{ctx.job_id}", source=SOURCE_BUILDER),
            get_sessionmaker()() as session,
            tenant_scoped_session(session, ctx.tenant_id),
        ):
            # El partner del cliente: el catálogo que ve depende de él (65.2).
            partner_id = await _partner_of(session)
            try:
                proposal, text = await asyncio.wait_for(
                    propose_agenda_text(
                        session,
                        agent_id=agent_id,
                        enabled=enabled,
                        complete=complete,
                        job_id=ctx.job_id,
                        actor=actor,
                        partner_id=partner_id,
                    ),
                    timeout=BUILD_CALL_TIMEOUT_S + 30.0,
                )
            except TimeoutError:
                # 3.5: el modelo tardó demasiado; el respaldo sin modelo.
                proposal, text = await propose_agenda_text(
                    session,
                    agent_id=agent_id,
                    enabled=enabled,
                    complete=None,
                    job_id=ctx.job_id,
                    actor=actor,
                    partner_id=partner_id,
                )
        log.info(
            "builder.job",
            tenant_id=str(ctx.tenant_id),
            agent_id=str(agent_id),
            job_id=str(ctx.job_id),
            kind=KIND,
            status="done",
            ops=len(text.ops),
            fallback=text.fallback,
        )
        return JobOutcome(
            result={
                "agent_id": str(agent_id),
                "enabled": enabled,
                "proposal_id": str(proposal.id) if proposal is not None else None,
                "ops": len(text.ops),
                "ficha_links": len(text.ficha_links),
                "fallback": text.fallback,
            }
        )

    return handle


def register(registry: JobRegistry = default_registry) -> None:
    if registry.get(KIND) is None:
        registry.register(KIND, make_agenda_text_handler(), timeout_s=TIMEOUT_S)


register()


__all__ = ["KIND", "TIMEOUT_S", "make_agenda_text_handler", "register"]
