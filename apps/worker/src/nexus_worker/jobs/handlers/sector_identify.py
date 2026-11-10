"""``sector_identify`` — identificar el sector del negocio (spec 047, enmienda del
2026-10-29: T200; requisito 57; research D46).

Lo que se identifica, cómo se valida y qué se hace con ello vive en la API
(``nexus_api.services.business.sector``); aquí, lo que es del worker:

- el **modelo**: uno barato, el de la tarea ``sector`` de la plataforma
  (``platform_models``: ``NEXUS_LLM_SECTOR_MODEL`` o el de clasificar), con el rol
  ``classify`` (la tarea de la taxonomía). Con ``llm_use_inmemory`` (local y
  pruebas) no hay modelo y vale la regla de respaldo de palabras enteras;
- la **medición**: todo el trabajo en un turno de uso con ``source = builder``,
  la partida «Construcción y pruebas» (57.8). El turno es ``job:{id}``;
- el **tope** (spec 047, T217): esa partida la paga Auphere hasta el tope del
  partner. Sin sitio (``build_budget.require_room_for_partner``), no se llama al
  modelo y vale la regla de respaldo, que no cuesta; la siguiente ocasión lo vuelve
  a identificar.

La llamada sale con la clave del partner del cliente: el consumidor abre su ámbito
(``llm_proxy_partner_scope``) para todo el trabajo.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Job
from nexus_api.services.business.sector import KIND, Complete, identify_sector

from nexus_worker.jobs.registry import (
    JobContext,
    JobHandler,
    JobOutcome,
    JobRegistry,
    default_registry,
)
from nexus_worker.metering.collector import SOURCE_BUILDER, usage_turn
from nexus_worker.platform_models import platform_model

log = structlog.get_logger(__name__)

#: Una llamada corta a un modelo barato; el plazo deja margen a uno lento.
TIMEOUT_S = 60.0
#: La tarea ``classify`` de la taxonomía (``runtime/llm.TASK_BY_ROLE``).
ROLE = "classify"

CompleteFactory = Callable[[uuid.UUID], Complete | None]


def sector_model() -> str:
    return platform_model("sector")


def default_complete(tenant_id: uuid.UUID) -> Complete | None:
    """El modelo de verdad; ``None`` en local con el proveedor en memoria."""
    from nexus_worker.config import get_worker_settings
    from nexus_worker.runtime.llm import LiteLLMProvider

    if get_worker_settings().llm_use_inmemory:
        return None
    provider = LiteLLMProvider(context_management=None)
    model = sector_model()

    async def complete(messages: list[dict[str, str]]) -> str:
        return await provider.acomplete(
            tenant_id=tenant_id, role=ROLE, model=model, messages=messages
        )

    return complete


async def _has_room(tenant_id: uuid.UUID) -> bool:
    """¿Le queda «Construcción y pruebas» al partner del cliente? (T217)."""
    import sqlalchemy as sa
    from nexus_api.db.models import Tenant
    from nexus_api.services.wallet import build_budget
    from nexus_api.services.wallet.bags import WalletError

    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        partner_id = await session.scalar(
            sa.select(Tenant.partner_id).where(Tenant.id == tenant_id)
        )
    if partner_id is None:
        return True
    try:
        await build_budget.require_room_for_partner(partner_id)
    except WalletError:
        return False
    return True


async def _after_read(ctx: JobContext) -> bool:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, ctx.tenant_id):
        job = await session.get(Job, ctx.job_id)
        given = dict((job.progress or {}).get("input") or {}) if job is not None else {}
    return bool(given.get("after_read"))


def make_sector_identify_handler(*, complete_factory: CompleteFactory | None = None) -> JobHandler:
    make_complete = complete_factory or default_complete

    async def handle(ctx: JobContext) -> JobOutcome:
        after_read = await _after_read(ctx)
        complete = make_complete(ctx.tenant_id)
        if complete is not None and not await _has_room(ctx.tenant_id):
            log.info("sector.no_build_room", tenant_id=str(ctx.tenant_id), job_id=str(ctx.job_id))
            complete = None
        async with usage_turn(
            tenant_id=ctx.tenant_id, turn_id=f"job:{ctx.job_id}", source=SOURCE_BUILDER
        ):
            result = await identify_sector(
                tenant_id=ctx.tenant_id,
                job_id=ctx.job_id,
                complete=complete,
                progress=ctx.progress,
                after_read=after_read,
            )
        return JobOutcome(result=result)

    return handle


def register(registry: JobRegistry = default_registry) -> None:
    if registry.get(KIND) is None:
        registry.register(KIND, make_sector_identify_handler(), timeout_s=TIMEOUT_S)


register()


__all__ = [
    "KIND",
    "ROLE",
    "TIMEOUT_S",
    "default_complete",
    "make_sector_identify_handler",
    "register",
    "sector_model",
]
