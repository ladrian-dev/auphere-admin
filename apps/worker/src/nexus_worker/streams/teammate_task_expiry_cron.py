"""Barrido de tareas de teammate vencidas — spec 003, Requisito 6.1.

Una tarea espera a una persona **mientras la tarea viva**. Cuando su
``expires_at`` pasa de verdad, alguien tiene que cerrarla y decir por qué: si
no, la bandeja acumularía tarjetas que ya no significan nada y «esperándote»
dejaría de querer decir algo.

Corre **sin persona** —a las tres de la mañana nadie tiene sesión—, así que el
barrido no se apoya en la RLS: usa el rol de la aplicación, que ve la tabla
entera. Es la única excepción del carril, y por eso vive aquí y no en una ruta.

Cada diez minutos, no cada treinta segundos: la caducidad se mide en días y un
barrido más frecuente solo gastaría conexiones del pool que comparte el webhook
de WhatsApp.
"""

from __future__ import annotations

import asyncio
import contextlib

import structlog
from nexus_api.db.base import get_sessionmaker
from nexus_api.repositories.teammate_tasks import TeammateTaskRepository

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 600.0


async def sweep_expired_tasks() -> int:
    """Cierra las tareas vencidas y sus acciones. Devuelve cuántas."""
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        expired: int = await TeammateTaskRepository(session).expire_due()
        return expired


async def run_teammate_task_expiry_cron(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    log.info("teammate_task_expiry_cron.start", tick_seconds=tick_seconds)
    while not stop.is_set():
        try:
            expired = await sweep_expired_tasks()
            if expired:
                log.info("teammate_task_expiry_cron.tick", expired=expired)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("teammate_task_expiry_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("teammate_task_expiry_cron.stopped")
