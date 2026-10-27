"""Volver a leer las webs del negocio cada semana — spec 047, T071 (requisito 12.3).

Cada hora, una pasada por los clientes que atienden (ni archivados ni en
pausa): las webs de «Documentos y webs» leídas hace más de una semana y la web y
las redes del propio cliente (la lectura del alta) vuelven a la cola como
``client_read``. Lo que hay detrás es de la API
(``nexus_api.services.business.sources.reread_due``):

- **Los cambios llegan como propuestas.** La relectura pasa por el mismo
  extractor y por ``reader.apply_extraction``: lo que choca con lo escrito por
  una persona queda como sugerencia al lado, y lo nuevo, marcado «revísalo».
- **Nunca dos a la vez.** Una fuente con su lectura en marcha no se encola otra
  vez; la pasada siguiente la vuelve a mirar.
- **Los archivos no se releen solos**: no cambian. «Volver a leer» sí los relee.
- **Se mide en «Construcción y pruebas»**: el manejador corre dentro del turno de
  uso del lector, nunca en la bolsa del cliente.

Corre en la familia del scheduler (elección de líder: una instancia).
"""

from __future__ import annotations

import asyncio
import contextlib

import structlog
from nexus_api.services.business.sources import reread_due
from redis.asyncio import Redis

log = structlog.get_logger(__name__)

#: El nombre de la tarea en el planificador (``wk/bootstrap.py``).
TASK_NAME = "source-reread-cron"
#: Mira cada hora; cada web se relee a la semana de su última lectura.
DEFAULT_TICK_SECONDS = 3600.0


async def run_source_reread_cron(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
    redis: Redis | None = None,
) -> None:
    """Cada ``tick_seconds``, encola lo que toca releer. Vuelve con ``stop``."""
    from nexus_api.core.redis_client import get_redis

    log.info("source_reread_cron.start", tick_seconds=tick_seconds)
    while not stop.is_set():
        try:
            queued = await reread_due(redis or get_redis())
            if queued:
                log.info("source_reread_cron.queued", jobs=queued)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("source_reread_cron.tick_failed", error=type(exc).__name__)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("source_reread_cron.stopped")


__all__ = ["DEFAULT_TICK_SECONDS", "TASK_NAME", "run_source_reread_cron"]
