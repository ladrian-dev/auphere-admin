"""El ciclo de vida de los modelos, en el planificador — spec 047, T149
(requisitos 41.7, 41.8 y 41.9).

Cada hora, una pasada de ``nexus_api.services.model_lifecycle.run_lifecycle``:

- los avisos ``model.retirement`` a 30 y a 7 días de la fecha de retirada, a
  los partners con agentes fijados en ese despliegue, con el sustituto propuesto;
- los avisos ``model.price_change`` de los precios que aún no están en vigor y
  suben más de un 10 % el precio estimado por mensaje de algún agente;
- lo que vence: en la fecha de retirada, cada agente fijado pasa a su sustituto
  o a «Automático» con una versión nueva, y el despliegue a ``retired``; y los
  precios que entran en vigor pasan a las columnas que lee el medidor.

Todo es idempotente (los avisos se deduplican; lo hecho no se rehace), así que
correr cada hora y no cada día solo acerca el cambio a su hora. Cuando algo
cambió, avisa a los demás procesos por el canal de promoción: ``catalog`` (el
router olvida su catálogo en memoria) y el cliente de cada agente movido (el
cargador recarga su versión).

Corre **sin persona** y en el planificador (un solo proceso). Registro:
``run_model_lifecycle_cron(stop=…, redis=…)`` con el nombre
``model-lifecycle-cron``.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
from typing import Any

import structlog
from nexus_api.services.model_lifecycle import LifecycleReport, run_lifecycle
from nexus_api.services.router_catalog import CATALOG_CHANGED

from nexus_worker.config import get_worker_settings
from nexus_worker.runtime.promote_subscriber import PROMOTE_CHANNEL

log = structlog.get_logger(__name__)

#: El nombre de la tarea en el planificador (``bootstrap.py``).
TASK_NAME = "model-lifecycle-cron"
DEFAULT_TICK_SECONDS = 3600.0


async def lifecycle_tick(
    *, redis: Any | None = None, now: datetime | None = None
) -> LifecycleReport:
    """Una pasada y, si algo cambió, el aviso a los demás procesos."""
    report = await run_lifecycle(now=now, default_respond=get_worker_settings().llm_respond_model)
    if redis is not None and (report.catalog_changed or report.moved_agents):
        await redis.publish(PROMOTE_CHANNEL, CATALOG_CHANGED)
        for tenant_id in sorted(report.tenants_changed, key=str):
            await redis.publish(PROMOTE_CHANNEL, str(tenant_id))
    return report


async def run_model_lifecycle_cron(
    *,
    stop: asyncio.Event,
    redis: Any | None = None,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    log.info("model_lifecycle_cron.start", tick_seconds=tick_seconds)
    while not stop.is_set():
        try:
            await lifecycle_tick(redis=redis)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("model_lifecycle_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("model_lifecycle_cron.stopped")


__all__ = [
    "DEFAULT_TICK_SECONDS",
    "TASK_NAME",
    "lifecycle_tick",
    "run_model_lifecycle_cron",
]
