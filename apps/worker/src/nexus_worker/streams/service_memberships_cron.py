"""La membresía de los clientes, al día — spec 077 (R7.8, R8.3).

Cada cinco minutos, sobre los clientes activos:

- **Del saldo del partner**: cobra el periodo siguiente desde una hora antes de
  que venza, y reintenta el de una membresía impagada hasta que haya saldo.
- **Por Stripe**: relee, como mucho una vez por hora, las pendientes con un
  enlace emitido, las impagadas y las activas cuyo periodo venció o que no se
  leen desde hace 24 horas. Cubre los avisos perdidos: el webhook no reintenta.

Repetirlo es seguro: el cargo es único por periodo y la relectura solo copia lo
que Stripe dice. La lógica vive en ``nexus_api.services.service_memberships``.
"""

from __future__ import annotations

import asyncio
import contextlib

import structlog
from nexus_api.services.service_memberships import tick

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 300.0


async def run_service_memberships_cron(
    *, stop: asyncio.Event, tick_seconds: float = DEFAULT_TICK_SECONDS
) -> None:
    """Background task. Returns when ``stop`` is set."""
    log.info("service_memberships_cron.start", tick_seconds=tick_seconds)
    while not stop.is_set():
        try:
            counts = await tick()
            if counts.get("charged") or counts.get("reread"):
                log.info("service_memberships_cron.tick", **counts)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("service_memberships_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("service_memberships_cron.stopped")
