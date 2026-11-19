"""``inbox-autoclose-cron`` — el cierre por inactividad de la Bandeja (spec 064, requisito 5).

Cada 5 minutos, por cada cliente activo y en su ``tenant_scoped_session``:
resuelve las conversaciones que lleva el agente y que pasaron el plazo que el
cliente eligió sin un mensaje en ningún sentido. La regla —qué se cierra, qué
no, y que sin plazo o sin Bandeja no se hace nada— vive en
``nexus_api.services.inbox_lifecycle`` (``autoclose_tick``); aquí, el bucle, a
quién se recorre y el aviso de tiempo real.

**A quién se recorre.** ``client_access`` lleva RLS FORCE: una consulta sin
acotar no devuelve ninguna fila, sin error. Así que la lista sale de ``tenants``
(sin RLS) y cada cliente se mira en su propia sesión, como en los crons de
Reservas.

**El aviso, después del commit.** La Bandeja abierta vuelve a pedir la
conversación al oír el evento: tiene que leerla ya resuelta. Si la transacción
de un cliente falla, no se avisa de nada suyo, y los demás siguen.

Una conversación resuelta así se comporta como cualquier otra: si el contacto
vuelve a escribir, se reabre y el agente empieza de cero (requisito 4).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Tenant, TenantStatus
from nexus_api.services import inbox_lifecycle
from nexus_api.services.inbox_stream import publish_inbox_event
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 5 * 60.0


async def active_tenant_ids(sm: async_sessionmaker[AsyncSession]) -> list[uuid.UUID]:
    """Los clientes activos. Si tienen plazo y Bandeja lo dice cada uno en su
    sesión acotada (``autoclose_tick``)."""
    async with sm() as session:
        return list(
            (
                await session.execute(
                    sa.select(Tenant.id)
                    .where(Tenant.status == TenantStatus.ACTIVE)
                    .order_by(Tenant.id)
                )
            ).scalars()
        )


async def cron_pass(sm: Any, *, redis: Redis | None, now: datetime | None = None) -> int:
    """Una pasada sobre todos los clientes. Devuelve cuántas conversaciones
    cerró. Un cliente que falla no para a los demás."""
    total = 0
    for tenant_id in await active_tenant_ids(sm):
        at = now or datetime.now(UTC)
        try:
            async with sm() as session, tenant_scoped_session(session, tenant_id):
                closed = await inbox_lifecycle.autoclose_tick(session, tenant_id, at)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error(
                "inbox_autoclose_cron.tenant_failed",
                tenant_id=str(tenant_id),
                error=type(exc).__name__,
            )
            continue
        if not closed:
            continue
        # Ya está confirmado: quien lo oiga leerá la conversación resuelta.
        log.info("inbox_autoclose_cron.tenant", tenant_id=str(tenant_id), closed=len(closed))
        for conversation_id in closed:
            await publish_inbox_event(
                redis,
                tenant_id=tenant_id,
                event="conversation.updated",
                conversation_id=conversation_id,
            )
        total += len(closed)
    return total


async def run_inbox_autoclose_cron(
    *, stop: asyncio.Event, redis: Redis | None = None, tick_seconds: float = DEFAULT_TICK_SECONDS
) -> None:
    log.info("inbox_autoclose_cron.start", tick_seconds=tick_seconds)
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            await cron_pass(sm, redis=redis)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("inbox_autoclose_cron.tick_failed", error=type(exc).__name__)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("inbox_autoclose_cron.stopped")


__all__ = ["DEFAULT_TICK_SECONDS", "active_tenant_ids", "cron_pass", "run_inbox_autoclose_cron"]
