"""``client_builder`` — «Completar con el constructor» (spec 047, T098; requisito 18).

Lo que se propone vive en la API (``nexus_api.services.builder.client_profile``);
aquí, el modelo de la tarea ``build`` (sin modelo en local, con
``llm_use_inmemory``) y la medición en «Construcción y pruebas» (``source=builder``).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from nexus_api.services.builder.agent_draft import BuilderUnavailable, Complete
from nexus_api.services.builder.client_profile import build_client_profile

from nexus_worker.jobs.handlers.agent_draft import UNAVAILABLE, default_complete
from nexus_worker.jobs.registry import (
    JobContext,
    JobFailed,
    JobHandler,
    JobOutcome,
    JobRegistry,
    default_registry,
)
from nexus_worker.metering.collector import SOURCE_BUILDER, usage_turn

KIND = "client_builder"
TIMEOUT_S = 180.0

CompleteFactory = Callable[[uuid.UUID], Complete | None]


def make_client_builder_handler(*, complete_factory: CompleteFactory | None = None) -> JobHandler:
    make_complete = complete_factory or default_complete

    async def handle(ctx: JobContext) -> JobOutcome:
        try:
            async with usage_turn(
                tenant_id=ctx.tenant_id, turn_id=f"job:{ctx.job_id}", source=SOURCE_BUILDER
            ):
                result = await build_client_profile(
                    tenant_id=ctx.tenant_id,
                    job_id=ctx.job_id,
                    complete=make_complete(ctx.tenant_id),
                    progress=ctx.progress,
                )
        except BuilderUnavailable as exc:
            raise JobFailed(UNAVAILABLE) from exc
        return JobOutcome(result=result)

    return handle


def register(registry: JobRegistry = default_registry) -> None:
    if registry.get(KIND) is None:
        registry.register(KIND, make_client_builder_handler(), timeout_s=TIMEOUT_S)


register()


__all__ = ["KIND", "make_client_builder_handler", "register"]
