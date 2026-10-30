"""``publish`` — «Guardar» (spec 047, T093; requisitos 23 y 24; research D6).

La cadena entera, en el worker: compilar → validar → **probar** → revisar →
decidir → publicar.

- Si el borrador tiene pruebas aplicables que no se han pasado con **esta**
  versión (o están desactualizadas), se pasan primero (``reason=publish``).
- La puerta (``nexus_api.services.publishing``) decide. Si no deja, el trabajo
  falla con ``gate_blocked`` (o ``override_forbidden``) y deja el veredicto, condición
  a condición, en su progreso (el bloque ``gate``), para que la consola diga por
  qué y qué hacer.
- Si deja, publica: el siguiente mensaje usa la versión nueva (el cargador del
  agente se entera por el canal de siempre) y hay 10 minutos para deshacer.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Job
from nexus_api.db.models.agent_spec import AgentTestRun
from nexus_api.services import publishing
from nexus_api.services.testing import runs as runs_service
from nexus_api.services.testing.suites import ensure_suite, list_tests

from nexus_worker.jobs.handlers.agent_tests import (
    CustomerFactory,
    JudgeFactory,
    default_customer,
    default_judge,
    run_suite,
)
from nexus_worker.jobs.registry import (
    JobContext,
    JobFailed,
    JobHandler,
    JobOutcome,
    JobRegistry,
    default_registry,
)
from nexus_worker.simulation.runner import default_router

log = structlog.get_logger(__name__)

KIND = "publish"
TIMEOUT_S = 900.0
PROMOTE_CHANNEL = "nexus:agent_config:promote"


async def _needs_run(ctx: JobContext, agent_id: uuid.UUID) -> uuid.UUID | None:
    """Una pasada nueva si el borrador tiene pruebas aplicables que esta versión
    no ha pasado, o desactualizadas. Devuelve su id, o ``None``."""
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, ctx.tenant_id):
        version = await runs_service.target_version(session, agent_id)
        if version is None:
            raise JobFailed("no_draft")
        suite = await ensure_suite(session, agent_id)
        tests = runs_service.tests_in_scope(await list_tests(session, suite), scope="all")
        if not tests:
            return None
        done = await session.scalar(
            sa.select(AgentTestRun.id).where(
                AgentTestRun.tenant_id == ctx.tenant_id,
                AgentTestRun.agent_id == agent_id,
                AgentTestRun.agent_config_id == version.id,
                AgentTestRun.status == "done",
                AgentTestRun.scope == "all",
            )
        )
        if done is not None and not any(t.stale for t in tests):
            return None
        run = await runs_service.create_run(
            session,
            agent_id=agent_id,
            scope="all",
            reason="publish",
            job_id=ctx.job_id,
            version=version,
        )
        run_id: uuid.UUID = run.id
        return run_id


def make_publish_handler(
    *,
    judge_factory: JudgeFactory | None = None,
    router_factory: Callable[[], Any] | None = None,
    customer_factory: CustomerFactory | None = None,
) -> JobHandler:
    make_judge = judge_factory or default_judge
    make_router = router_factory or default_router
    make_customer = customer_factory or default_customer

    async def handle(ctx: JobContext) -> JobOutcome:
        agent_id = ctx.agent_id
        if agent_id is None:
            raise JobFailed("no_agent")
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, ctx.tenant_id):
            job = await session.get(Job, ctx.job_id)
            data = dict((job.progress or {}).get("input") or {}) if job is not None else {}

        await ctx.progress(step="testing")
        run_id = await _needs_run(ctx, agent_id)
        if run_id is not None:
            await run_suite(
                ctx,
                run_id,
                judge=make_judge(ctx.tenant_id),
                router=make_router(),
                customer=make_customer(ctx.tenant_id),
            )

        await ctx.progress(step="deciding")
        try:
            async with sm() as session, tenant_scoped_session(session, ctx.tenant_id):
                done = await publishing.publish(
                    session,
                    agent_id=agent_id,
                    actor=str(data.get("actor") or "console"),
                    role=str(data.get("role") or ""),
                    partner_id=uuid.UUID(data["partner_id"]) if data.get("partner_id") else None,
                    note=data.get("note"),
                    accept_normal_failures=bool(data.get("accept_normal_failures")),
                    override_reason=data.get("override_reason"),
                    origin=str(data.get("origin") or "console"),
                )
                version_id = done.version.id
                result = {
                    "agent_id": str(agent_id),
                    "number": done.version.agent_version_number,
                    "undo_until": done.undo_until.isoformat(),
                    "gate": done.gate.to_json(),
                }
        except publishing.GateBlocked as exc:
            log.info(
                "gate.decision",
                tenant_id=str(ctx.tenant_id),
                agent_id=str(agent_id),
                outcome="blocked",
                blocking=sorted(
                    {str(c.get("code")) for c in [*exc.gate.hard, *exc.gate.overridable]}
                ),
            )
            await ctx.progress(step="blocked", block={"key": "gate", **exc.gate.to_json()})
            raise JobFailed("gate_blocked") from exc
        except publishing.OverrideForbidden as exc:
            raise JobFailed("override_forbidden") from exc
        except publishing.NothingToPublish as exc:
            raise JobFailed("no_draft") from exc
        await _tell_runtime(ctx.tenant_id, agent_id)
        log.info(
            "gate.decision",
            tenant_id=str(ctx.tenant_id),
            agent_id=str(agent_id),
            version_id=str(version_id),
            outcome="published",
        )
        return JobOutcome(result=result)

    return handle


async def _tell_runtime(tenant_id: uuid.UUID, agent_id: uuid.UUID) -> None:
    """El siguiente mensaje usa la versión nueva (23.6): el cargador suelta su caché."""
    from nexus_api.core import redis_client

    try:
        await redis_client.get_redis().publish(PROMOTE_CHANNEL, f"{tenant_id}:{agent_id}")
    except Exception:  # la caché caduca sola; publicar ya está hecho
        log.warning("jobs.publish.invalidate_failed", tenant_id=str(tenant_id))


def register(registry: JobRegistry = default_registry) -> None:
    if registry.get(KIND) is None:
        registry.register(KIND, make_publish_handler(), timeout_s=TIMEOUT_S)


register()


__all__ = ["KIND", "TIMEOUT_S", "make_publish_handler", "register"]
