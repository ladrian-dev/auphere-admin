"""``reservation-offers-cron`` — avanza las ofertas de la lista de espera cada
15 s (spec 043, Historia 6 y R7.4).

Al vencer el plazo de quien tenía la oferta (5 min en Servicios, 15 en Aforo),
vuelve a la lista y se escribe al siguiente que encaja; sin nadie más, o sin la
antelación mínima, la oferta se cierra vacía. La regla es de
``waitlist.advance``; aquí, el bucle.

Corre en todo cliente con ``reservation_settings``, también sin el módulo: una
oferta en curso retiene el hueco (Servicios), y dejarla a medias lo dejaría
retenido para siempre.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

import structlog
from nexus_api.services.reservations import waitlist
from nexus_api.services.reservations.core import load_ctx
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_worker.streams.reservations_cron import Roster, run_for_reservation_tenants

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 15.0


async def process_tenant(session: AsyncSession, tenant_id: uuid.UUID, now: datetime) -> int:
    """Vence plazos y pasa al siguiente en un cliente. Devuelve cuántos
    candidatos se quedaron sin responder en esta pasada."""
    ctx = await load_ctx(session, tenant_id)
    if ctx is None:
        return 0
    moved: int = await waitlist.advance(session, ctx, now)
    if moved:
        log.info("reservation_offers_cron.advanced", tenant_id=str(tenant_id), noreply=moved)
    return moved


async def run_reservation_offers_cron(
    *, stop: asyncio.Event, tick_seconds: float = DEFAULT_TICK_SECONDS
) -> None:
    await run_for_reservation_tenants(
        name="reservation_offers_cron",
        stop=stop,
        tick_seconds=tick_seconds,
        process=process_tenant,
        roster=Roster(),
    )


__all__ = ["DEFAULT_TICK_SECONDS", "process_tenant", "run_reservation_offers_cron"]
