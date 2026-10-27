"""``client_read`` — la lectura de la web y de las redes de un cliente (spec 047, T049).

El primer manejador de ``jobs-consumer``. Lo que se lee, con qué guardas y qué
se hace con lo leído vive en la API (``nexus_api.services.business.reader``);
aquí solo se pone lo que es del worker:

- el **cliente HTTP** de la lectura, sin redirecciones automáticas (cada salto
  lo valida la guarda de direcciones públicas);
- el **modelo** de la tarea ``read_source``, por el proveedor de siempre
  (``runtime/llm.py``, sin tocarlo). El modelo sale de
  ``NEXUS_LLM_READ_SOURCE_MODEL`` o, sin ella, del de clasificar, hasta que el
  router elija por tarea (B4);
- la **medición**: la lectura entera va en un turno de uso con
  ``source = reader``, que cae en la partida «Construcción y pruebas»
  (``USAGE_LINE_BY_SOURCE``) y nunca en la bolsa del cliente. El turno es
  ``job:{id}``: reprocesar el stream no duplica nada;
- el **aviso** a quien la lanzó, al terminar o al fallar.

Un ``client_read`` con ``source_id`` en su ``progress`` no es la lectura de la web
del cliente sino de una de sus fuentes (un documento o una web de «Documentos y
webs», T071): va a ``business_sources.handle_source``, con el mismo modelo y la
misma medición, y un modelo con visión para las fotos de cartas.

Un fallo de la lectura sale como :class:`JobFailed` con su código
(``unreachable``, ``blocked``, ``no_text``, ``too_large``, ``extract_failed``):
la consola pone las palabras y ofrece reintentar.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable

import httpx
import structlog
from nexus_api.services.business.reader import (
    USER_AGENT,
    Extract,
    NothingToRead,
    ReadFailure,
    notify_read_finished,
    read_client,
)
from nexus_api.services.knowledge_indexer import FETCH_TIMEOUT_S

from nexus_worker.jobs.handlers.business_sources import (
    VisionFactory,
    default_vision,
    handle_source,
    source_target,
)
from nexus_worker.jobs.registry import (
    JobContext,
    JobFailed,
    JobHandler,
    JobOutcome,
    JobRegistry,
    default_registry,
)
from nexus_worker.metering.collector import SOURCE_READER, usage_turn

log = structlog.get_logger(__name__)

KIND = "client_read"
#: 25 páginas con su plazo cada una, más el modelo. El consumidor late mientras.
TIMEOUT_S = 420.0
#: El código de un cliente sin web ni redes que leer.
NOTHING_TO_READ = "nothing_to_read"
#: El rol con el que la llamada sale por el proveedor (telemetría y trazas).
ROLE = "read_source"

ExtractorFactory = Callable[[uuid.UUID], Extract]
HttpFactory = Callable[[], httpx.AsyncClient]


def read_source_model() -> str:
    from nexus_worker.config import get_worker_settings

    return os.environ.get("NEXUS_LLM_READ_SOURCE_MODEL") or get_worker_settings().llm_classify_model


def default_extractor(tenant_id: uuid.UUID) -> Extract:
    """El modelo de verdad, por el proveedor de siempre. Su único punto de paso
    (``_record_call``) anota los tokens en el turno de uso abierto."""
    from nexus_worker.config import get_worker_settings
    from nexus_worker.runtime.llm import InMemoryProvider, LiteLLMProvider, LLMProvider

    provider: LLMProvider = (
        InMemoryProvider()
        if get_worker_settings().llm_use_inmemory
        else LiteLLMProvider(context_management=None)
    )
    model = read_source_model()

    async def extract(messages: list[dict[str, str]]) -> str:
        return await provider.acomplete(
            tenant_id=tenant_id, role=ROLE, model=model, messages=messages
        )

    return extract


def default_http() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        follow_redirects=False,
        timeout=FETCH_TIMEOUT_S,
        headers={"User-Agent": USER_AGENT},
    )


def make_client_read_handler(
    *,
    extractor_factory: ExtractorFactory | None = None,
    http_factory: HttpFactory | None = None,
    vision_factory: VisionFactory | None = None,
) -> JobHandler:
    """El manejador, con el modelo y el cliente HTTP que se le den (las pruebas
    ponen los suyos; en producción, :func:`default_extractor` y
    :func:`default_http`)."""
    make_extract = extractor_factory or default_extractor
    make_http = http_factory or default_http
    make_vision = vision_factory or default_vision

    async def handle(ctx: JobContext) -> JobOutcome:
        bound = {"tenant_id": str(ctx.tenant_id), "job_id": str(ctx.job_id)}
        # Spec 047 (T071): un documento o una web del negocio viaja como
        # ``client_read`` con la fuente en su ``progress``; se lee aparte.
        target = await source_target(ctx)
        if target is not None:
            return await handle_source(
                ctx,
                target,
                extract=make_extract(ctx.tenant_id),
                http=make_http,
                vision=make_vision(ctx.tenant_id),
            )
        try:
            async with (
                usage_turn(
                    tenant_id=ctx.tenant_id,
                    turn_id=f"job:{ctx.job_id}",
                    source=SOURCE_READER,
                ),
                make_http() as http,
            ):
                result = await read_client(
                    tenant_id=ctx.tenant_id,
                    http=http,
                    extract=make_extract(ctx.tenant_id),
                    progress=ctx.progress,
                )
        except ReadFailure as failure:
            log.info("jobs.client_read.failed", code=failure.code, **bound)
            await notify_read_finished(
                tenant_id=ctx.tenant_id,
                recipient_user_id=ctx.job.created_by,
                failure=failure.code,
            )
            raise JobFailed(failure.code) from failure
        except NothingToRead as nothing:
            raise JobFailed(NOTHING_TO_READ) from nothing
        await notify_read_finished(
            tenant_id=ctx.tenant_id, recipient_user_id=ctx.job.created_by, result=result
        )
        return JobOutcome(result=result)

    return handle


def register(registry: JobRegistry = default_registry) -> None:
    """Registra la lectura en ``registry`` (por defecto, el de ``jobs-consumer``).
    Idempotente: importar dos veces no la registra dos veces."""
    if registry.get(KIND) is None:
        registry.register(KIND, make_client_read_handler(), timeout_s=TIMEOUT_S)


register()


__all__ = [
    "KIND",
    "NOTHING_TO_READ",
    "TIMEOUT_S",
    "default_extractor",
    "default_http",
    "make_client_read_handler",
    "read_source_model",
    "register",
]
