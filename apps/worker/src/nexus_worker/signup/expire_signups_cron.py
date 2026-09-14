"""Barre las solicitudes de alta vencidas — spec 006, T050 (Requisito 6.1).

**Por qué existe si la caducidad ya es perezosa.** El repositorio marca una
solicitud como caducada cuando alguien la mira, así que la respuesta al usuario
siempre es correcta sin este cron. Lo que la pereza no hace es limpiar lo que
**nadie vuelve a mirar**: el caso normal de un alta abandonada es que su enlace
no se abra jamás. Sin esto, la tabla acumula filas `pending` que ya no lo son,
y el índice parcial que hace barata la regla de «una pendiente por correo»
crece con basura.

Diario, y no más a menudo, por la misma razón que el cron de crédito: la
caducidad es una fecha, no un evento — no hay nada a lo que reaccionar y nada
que ganar mirando más veces.

**Recordatorio para quien añada el siguiente cron:** el nombre va en DOS
sitios, ``bootstrap.SCHEDULER_TASK_NAMES`` y el contrato de
``tests/unit/test_bootstrap_split.py``. Olvidar el segundo ha abortado dos
despliegues (2026-09-11 y 2026-09-13).
"""

from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger(__name__)

#: Diario. La caducidad es una fecha, no un evento.
DEFAULT_TICK_SECONDS = 86_400.0


async def sweep_once(sm: Any) -> int:
    """Una pasada. Devuelve cuántas se marcaron, para el registro y las pruebas."""
    from nexus_api.repositories.signup import SignupRequestRepository

    async with sm() as session:
        # int(...) no es decoración: sm viene tipado como Any —el
        # sessionmaker se inyecta— así que sin esto mypy --strict ve un Any
        # saliendo de una función que promete int.
        swept = int(await SignupRequestRepository(session).expire_overdue())
        await session.commit()
    if swept:
        log.info("expire_signups_cron.swept", requests=swept)
    return swept


async def run_expire_signups_cron(*, stop: Any, tick_seconds: float = DEFAULT_TICK_SECONDS) -> None:
    """Tarea de fondo. Vuelve cuando ``stop`` se activa."""
    import asyncio
    import contextlib

    from nexus_api.db.base import get_sessionmaker

    log.info("expire_signups_cron.start", tick_seconds=tick_seconds)
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            await sweep_once(sm)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Una solicitud que debía caducar y no caducó es un problema menor
            # que un planificador muerto: la pereza del repositorio ya impide
            # que se pueda usar, y la siguiente pasada se pone al día porque la
            # consulta mira una fecha, no lo que pasó desde entonces.
            log.error("expire_signups_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("expire_signups_cron.stopped")
