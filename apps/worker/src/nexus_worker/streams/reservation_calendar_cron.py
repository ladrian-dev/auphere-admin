"""``reservation-calendar-cron`` — el Google Calendar de cada profesional, cada 2 min
(spec 043, requisitos 10, 12 y 13; ``contracts/worker-y-avisos.md``).

Por cada cliente con Reservas y algún profesional con su calendario conectado desde el
panel, una pasada de ``calendar_sync.sync_tenant``: termina las autorizaciones en curso,
entra el «ocupado» de cada persona, salen sus reservas vivas como «Ocupado», se borran
las que ya no lo son o se movieron, y se termina de desconectar a quien lo pidió. Sin nada
que sincronizar, no llama a nadie.

**Cada uno con su conexión, y sin conexión sana no se bloquea con datos viejos.** Si la
cuenta de una persona necesita volver a conectarse, su ocupado se quita y la pantalla lo
dice; a los demás no les pasa nada.

**Solo con el proveedor de verdad.** Sin ``composio_api_key`` la API cae en el
cliente simulado del proveedor; sincronizar contra él borraría el ocupado real
de la base. Así que sin clave el cron no hace nada (y lo dice una vez).

La lista de clientes y el bucle son los de ``reservations-cron``.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import datetime

import structlog
from nexus_api.config import get_settings
from nexus_api.services.reservations import calendar_sync
from nexus_api.services.reservations.calendar_sync import GoogleCalendarGateway
from nexus_api.services.reservations.core import load_ctx
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_worker.streams.reservations_cron import (
    ProcessTenant,
    Roster,
    run_for_reservation_tenants,
)

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 120.0
#: Un proveedor colgado no para al resto: el cron pasa por los clientes de uno en uno.
TENANT_TIMEOUT_SECONDS = 300.0

GatewayFactory = Callable[[], GoogleCalendarGateway | None]


def live_gateway() -> GoogleCalendarGateway | None:
    """La puerta real, o ``None`` si el entorno no tiene el proveedor."""
    if not get_settings().composio_api_key:
        return None
    return calendar_sync.default_gateway()


def make_process(factory: GatewayFactory = live_gateway) -> ProcessTenant:
    """La pasada de un cliente. La puerta se construye la primera vez que un
    cliente la necesita, y una sola vez."""
    gateway: list[GoogleCalendarGateway | None] = []

    async def process(
        session: AsyncSession, tenant_id: uuid.UUID, now: datetime
    ) -> dict[str, int] | None:
        if not await calendar_sync.has_work(session, now=now):
            return None
        if not gateway:
            gateway.append(factory())
            if gateway[0] is None:
                log.warning("reservation_calendar_cron.no_provider")
        if gateway[0] is None:
            return None
        ctx = await load_ctx(session, tenant_id)
        if ctx is None:
            return None
        stats: dict[str, int] = await asyncio.wait_for(
            calendar_sync.sync_tenant(session, ctx, gateway[0], now=now),
            timeout=TENANT_TIMEOUT_SECONDS,
        )
        if any(stats.values()):
            log.info("reservation_calendar_cron.tenant", tenant_id=str(tenant_id), **stats)
        return stats

    return process


async def run_reservation_calendar_cron(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
    factory: GatewayFactory = live_gateway,
) -> None:
    await run_for_reservation_tenants(
        name="reservation_calendar_cron",
        stop=stop,
        tick_seconds=tick_seconds,
        process=make_process(factory),
        roster=Roster(),
    )


__all__ = [
    "DEFAULT_TICK_SECONDS",
    "live_gateway",
    "make_process",
    "run_reservation_calendar_cron",
]
