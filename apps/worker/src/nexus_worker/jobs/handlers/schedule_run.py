"""El trabajo ``schedule_run`` — spec 082, T017 (requisitos 4, 5, 6 y 9).

Une las tres piezas que ya existen: la rutina en su fila, el turno sin cliente
final (``runtime/schedule_turn``) y el cobro a la bolsa (el medidor, con origen
``schedule``).

El trabajo **no lleva la instrucción dentro**: la lee de la ejecución, que la
guardó al abrirse. Así un intento que se reencola no puede ejecutar una
instrucción distinta de la que el partner escribió, aunque entre medias alguien
edite la rutina.

Lo que gasta sale de la bolsa del cliente por ``usage_turn(source=schedule)``:
el consumidor del medidor lo reparte a la partida de rutinas y lo cobra con el
asiento ``debit_schedule``. Aquí no se cobra a mano.

**Sin modelo** (local, con el proveedor en memoria) el trabajo falla con
``no_model`` en vez de inventarse una respuesta: una rutina que contesta algo
que no vino de ningún agente es peor que una que no contesta.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Job, Schedule, ScheduleRun
from nexus_api.services.schedules import runs as runs_service

from nexus_worker.jobs.registry import (
    JobContext,
    JobFailed,
    JobHandler,
    JobOutcome,
    JobRegistry,
    default_registry,
)
from nexus_worker.metering.collector import SOURCE_SCHEDULE, usage_turn
from nexus_worker.runtime.schedule_turn import run_loop, tools_for_routine

log = structlog.get_logger(__name__)

KIND = "schedule_run"
#: Lo que puede durar una ejecución antes de darla por perdida. Más que un turno
#: de canal porque nadie espera delante, y bastante menos que las pruebas.
TIMEOUT_S = 180.0


async def _input(ctx: JobContext) -> dict[str, Any]:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, ctx.tenant_id):
        job = await session.get(Job, ctx.job_id)
        return dict((job.progress or {}).get("input") or {}) if job is not None else {}


def _provider() -> Any:
    """El proveedor de verdad, o ``None`` en local con el modelo en memoria."""
    from nexus_worker.config import get_worker_settings
    from nexus_worker.runtime import llm

    if get_worker_settings().llm_use_inmemory:
        return None
    return llm.LiteLLMProvider(context_management=None, timeout_s=TIMEOUT_S, max_retries=0)


def make_schedule_run_handler(*, provider_factory: Any = None) -> JobHandler:
    make_provider = provider_factory or _provider

    async def handle(ctx: JobContext) -> JobOutcome:
        from nexus_mcp import build_default_registry

        from nexus_worker.runtime.agent_loader import get_default_loader
        from nexus_worker.runtime.pipeline import agent_respond_model

        data = await _input(ctx)
        sm = get_sessionmaker()
        run_id: uuid.UUID | None = None

        if data.get("run_id"):
            # Una rutina de verdad: la instrucción sale de su ejecución, que la
            # guardó al abrirse.
            try:
                run_id = uuid.UUID(str(data["run_id"]))
                schedule_id = uuid.UUID(str(data["schedule_id"]))
            except (KeyError, ValueError) as exc:
                raise JobFailed("bad_input") from exc
            async with sm() as session, tenant_scoped_session(session, ctx.tenant_id):
                schedule = await session.get(Schedule, schedule_id)
                run = await session.get(ScheduleRun, run_id)
                if schedule is None or run is None:
                    raise JobFailed("not_found")
                await runs_service.start(session, run, job_id=ctx.job_id)
                instruction = run.instruction
                agent_id = schedule.agent_id
        else:
            # «Probar ahora» desde el alta: no hay rutina ni fila que abrir, y
            # la respuesta vuelve en el resultado del trabajo.
            try:
                agent_id = uuid.UUID(str(data["agent_id"]))
            except (KeyError, ValueError) as exc:
                raise JobFailed("bad_input") from exc
            instruction = str(data.get("instruction") or "").strip()
            if not instruction:
                raise JobFailed("bad_input")

        provider = make_provider()
        if provider is None:
            if run_id is not None:
                await _fail(ctx, run_id, "no_model")
            raise JobFailed("no_model")

        bundle = await get_default_loader().load(ctx.tenant_id, agent_id)
        registry = build_default_registry()
        chosen = await tools_for_routine(
            registry, ceiling=bundle.tools, tenant_id=ctx.tenant_id, agent_id=agent_id
        )
        started = time.monotonic()
        try:
            async with usage_turn(
                tenant_id=ctx.tenant_id,
                # Solo el identificador: el medidor ya le pone delante el origen, y
                # la referencia que sale es la que el hilo busca para enseñar
                # lo que costó (``usage_ref_for``).
                turn_id=str(run_id or ctx.job_id),
                source=SOURCE_SCHEDULE,
                agent_id=agent_id,
            ):
                answer = await run_loop(
                    provider=provider,
                    model=agent_respond_model(bundle).model_id,
                    tenant_id=ctx.tenant_id,
                    system=bundle.system_prompt,
                    instruction=instruction,
                    registry=registry,
                    chosen=chosen,
                )
        except Exception as exc:
            log.warning(
                "schedule_run.failed",
                tenant_id=str(ctx.tenant_id),
                run_id=str(run_id),
                error=type(exc).__name__,
            )
            if run_id is not None:
                await _fail(ctx, run_id, "model_failed")
            raise JobFailed("model_failed") from exc

        elapsed = int((time.monotonic() - started) * 1000)
        if run_id is not None:
            async with sm() as session, tenant_scoped_session(session, ctx.tenant_id):
                row = await session.get(ScheduleRun, run_id)
                if row is not None:
                    await runs_service.close(
                        session,
                        row,
                        answer=answer.text,
                        tools_used=answer.tools_used,
                        withheld=tuple(w.as_dict() for w in answer.withheld),
                        partial=answer.partial,
                        duration_ms=elapsed,
                    )
        return JobOutcome(
            result={
                "run_id": str(run_id) if run_id else None,
                "status": "partial" if answer.partial else "done",
                "tools_used": list(answer.tools_used),
                "withheld": [w.as_dict() for w in answer.withheld],
                # Solo en «Probar ahora»: sin fila donde guardarla, la respuesta
                # viaja en el resultado del trabajo.
                "answer": None if run_id else answer.text,
            }
        )

    return handle


async def _fail(ctx: JobContext, run_id: uuid.UUID, code: str) -> None:
    """Deja la ejecución cerrada con su motivo. Una ejecución que se queda en
    ``running`` para siempre es la que hace que el partner no sepa si esperar."""
    async with get_sessionmaker()() as session, tenant_scoped_session(session, ctx.tenant_id):
        row = await session.get(ScheduleRun, run_id)
        if row is not None and row.finished_at is None:
            await runs_service.fail(session, row, error_code=code)


def register(registry: JobRegistry = default_registry) -> None:
    if registry.get(KIND) is None:
        registry.register(KIND, make_schedule_run_handler(), timeout_s=TIMEOUT_S)


register()


__all__ = ["KIND", "TIMEOUT_S", "make_schedule_run_handler", "register"]
