"""``agent_draft`` — «Generar borrador» (spec 047, T079; requisitos 15, 17).

Lo que se construye y cómo vive en la API
(``nexus_api.services.builder.agent_draft``); aquí solo lo que es del worker:

- el **modelo** de la tarea ``build``, por el proveedor de siempre
  (``runtime/llm.py``). Sale de ``NEXUS_LLM_BUILD_MODEL`` o, sin ella, del de
  responder, hasta que el router elija por tarea. Con ``llm_use_inmemory`` (local
  y pruebas) no hay modelo: el constructor usa su generador determinista y el
  flujo se recorre entero sin claves;
- la **medición**: todo el trabajo va en un turno de uso con ``source=builder``,
  que cae en la partida «Construcción y pruebas» y nunca en la bolsa del cliente
  (requisito 15.7). El turno es ``job:{id}``: reprocesar no duplica nada;
- el **fallo con nombre**: sin borrador que enseñar, ``builder_unavailable``, y
  la consola ofrece «Desde una plantilla» y «En blanco» (15.8). Si la ficha no se
  pudo leer, ``facts_unavailable`` (65.12): ningún borrador genérico.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Job
from nexus_api.services.builder.agent_draft import (
    BuilderUnavailable,
    Complete,
    DraftInputInvalid,
    DraftRequest,
    FactsUnavailable,
    build_agent_draft,
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

KIND = "agent_draft"
#: 30 s en el p90 es el objetivo; el plazo deja margen a un modelo lento.
TIMEOUT_S = 180.0
ROLE = "build"
UNAVAILABLE = "builder_unavailable"

CompleteFactory = Callable[[uuid.UUID], Complete | None]


def build_model() -> str:
    """El de la plataforma (requisito 64.2): ``NEXUS_LLM_BUILD_MODEL`` o el de responder."""
    from nexus_worker.platform_models import platform_model

    return platform_model("build")


def default_complete(tenant_id: uuid.UUID) -> Complete | None:
    """El modelo de verdad; ``None`` en local con el proveedor en memoria."""
    from nexus_worker.config import get_worker_settings
    from nexus_worker.runtime.llm import LiteLLMProvider

    if get_worker_settings().llm_use_inmemory:
        return None
    provider = LiteLLMProvider(context_management=None)
    model = build_model()

    async def complete(messages: list[dict[str, str]]) -> str:
        return await provider.acomplete(
            tenant_id=tenant_id, role=ROLE, model=model, messages=messages
        )

    return complete


async def _input(ctx: JobContext) -> dict[str, str]:
    """Lo que escribió la persona (nombre y descripción) y quién lo pidió: va en
    el ``progress`` del trabajo, que escribió la API con el cliente puesto."""
    async with get_sessionmaker()() as session, tenant_scoped_session(session, ctx.tenant_id):
        job = await session.get(Job, ctx.job_id)
        raw = dict((job.progress or {}).get("input") or {}) if job is not None else {}
    return {k: str(v) for k, v in raw.items() if isinstance(v, str)}


def make_agent_draft_handler(*, complete_factory: CompleteFactory | None = None) -> JobHandler:
    make_complete = complete_factory or default_complete

    async def handle(ctx: JobContext) -> JobOutcome:
        data = await _input(ctx)
        try:
            request = DraftRequest.clean(data.get("name", ""), data.get("description", ""))
        except DraftInputInvalid as exc:
            raise JobFailed(exc.code) from exc
        try:
            async with usage_turn(
                tenant_id=ctx.tenant_id, turn_id=f"job:{ctx.job_id}", source=SOURCE_BUILDER
            ):
                result = await build_agent_draft(
                    tenant_id=ctx.tenant_id,
                    job_id=ctx.job_id,
                    request=request,
                    complete=make_complete(ctx.tenant_id),
                    progress=ctx.progress,
                    actor=data.get("actor") or "builder",
                )
        except DraftInputInvalid as exc:  # p. ej. el nombre se ocupó mientras tanto
            raise JobFailed(exc.code) from exc
        except FactsUnavailable as exc:
            log.info(
                "jobs.agent_draft.facts_unavailable",
                tenant_id=str(ctx.tenant_id),
                job_id=str(ctx.job_id),
            )
            raise JobFailed(FactsUnavailable.code) from exc
        except BuilderUnavailable as exc:
            log.info(
                "jobs.agent_draft.unavailable",
                tenant_id=str(ctx.tenant_id),
                job_id=str(ctx.job_id),
                why=str(exc),
            )
            raise JobFailed(UNAVAILABLE) from exc
        return JobOutcome(result=result)

    return handle


def register(registry: JobRegistry = default_registry) -> None:
    if registry.get(KIND) is None:
        registry.register(KIND, make_agent_draft_handler(), timeout_s=TIMEOUT_S)


register()


__all__ = [
    "KIND",
    "TIMEOUT_S",
    "UNAVAILABLE",
    "build_model",
    "default_complete",
    "make_agent_draft_handler",
    "register",
]
