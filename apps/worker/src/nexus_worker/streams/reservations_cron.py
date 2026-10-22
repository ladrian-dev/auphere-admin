"""``reservations-cron`` — lo que Reservas hace solo, cada minuto (spec 043, R7).

Por cada cliente con ``reservation_settings``, en su ``tenant_scoped_session``:

1. encola la petición de confirmación o el recordatorio que ya toca;
2. Aforo: libera la que sigue sin confirmar 1 h antes (si «liberar» está
   encendido y la pregunta salió);
3. pasa a ``done`` lo terminado;
4. caduca las entradas de la lista cuyo día pasó;
5. Aforo: abre ofertas cuando hay sitio y alguien de la lista cabe.

Las reglas viven en ``nexus_api.services.reservations.automation``; aquí, el
bucle y a quién se recorre. Lo comparten los otros dos crons de Reservas
(``reservation-offers-cron`` y ``reservation-outbox-cron``).

**A quién se recorre.** ``reservation_settings`` y ``client_access`` llevan RLS
FORCE: una consulta sin acotar no devuelve ninguna fila, sin error (el fallo
silencioso que documenta ``cobranza_reminder_cron``). Así que la lista sale de
``tenants`` (sin RLS) y cada cliente se mira en su propia sesión acotada. El
módulo no decide si se recorre: el contrato dice «clientes con
``reservation_settings``» y la spec, que al desactivar el módulo las reservas
futuras siguen recibiendo sus recordatorios. Sin el módulo solo se deja de
**ofrecer** huecos (el paso 5).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    ClientAccess,
    ClientModule,
    ReservationSettings,
    Tenant,
    TenantStatus,
)
from nexus_api.services.reservations import automation
from nexus_api.services.reservations.core import load_ctx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 60.0
#: Cada cuánto se rehace la lista de clientes con Reservas en los crons
#: rápidos (10 y 15 s): activar el módulo tarda como mucho esto en notarse.
ROSTER_TTL_SECONDS = 60.0

ProcessTenant = Callable[[AsyncSession, uuid.UUID, datetime], Awaitable[object]]


# ── a quién se recorre ──────────────────────────────────────────────────────


async def reservation_tenant_ids(sm: async_sessionmaker[AsyncSession]) -> list[uuid.UUID]:
    """Clientes activos con ``reservation_settings``. Ver la cabecera: la lista
    sale de ``tenants`` y cada uno se comprueba en su sesión acotada."""
    async with sm() as session:
        active = list(
            (
                await session.execute(
                    sa.select(Tenant.id)
                    .where(Tenant.status == TenantStatus.ACTIVE)
                    .order_by(Tenant.id)
                )
            ).scalars()
        )
    out: list[uuid.UUID] = []
    for tenant_id in active:
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            has = await session.scalar(
                sa.select(ReservationSettings.tenant_id).where(
                    ReservationSettings.tenant_id == tenant_id
                )
            )
        if has is not None:
            out.append(tenant_id)
    return out


class Roster:
    """La lista de clientes con Reservas, rehecha como mucho cada ``ttl``
    segundos (0 = siempre)."""

    def __init__(self, ttl_seconds: float = ROSTER_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._ids: list[uuid.UUID] = []
        self._at: float | None = None

    async def ids(self, sm: async_sessionmaker[AsyncSession]) -> list[uuid.UUID]:
        mono = time.monotonic()
        if self._at is None or mono - self._at >= self.ttl_seconds:
            self._ids = await reservation_tenant_ids(sm)
            self._at = mono
        return list(self._ids)


async def pass_over_tenants(
    sm: async_sessionmaker[AsyncSession],
    process: ProcessTenant,
    *,
    roster: Roster,
    name: str,
    now: datetime | None = None,
) -> int:
    """Una pasada: ``process`` en cada cliente, cada uno en su transacción. Un
    cliente que falla no para a los demás."""
    tenants = await roster.ids(sm)
    for tenant_id in tenants:
        at = now or datetime.now(UTC)
        try:
            async with sm() as session, tenant_scoped_session(session, tenant_id):
                await process(session, tenant_id, at)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error(
                f"{name}.tenant_failed",
                tenant_id=str(tenant_id),
                error=automation.error_text(exc),
            )
    return len(tenants)


async def run_for_reservation_tenants(
    *,
    name: str,
    stop: asyncio.Event,
    tick_seconds: float,
    process: ProcessTenant,
    roster: Roster,
) -> None:
    """El bucle común de los crons de Reservas: una pasada por ``tick_seconds``."""
    log.info(f"{name}.start", tick_seconds=tick_seconds)
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            await pass_over_tenants(sm, process, roster=roster, name=name)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error(f"{name}.tick_failed", error=automation.error_text(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info(f"{name}.stopped")


# ── reservations-cron ───────────────────────────────────────────────────────


async def _offers_on(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    """El cliente tiene el módulo encendido: se le pueden ofrecer huecos."""
    access = await session.get(ClientAccess, tenant_id)
    return bool(
        access is not None
        and access.enabled
        and ClientModule.RESERVAS.value in (access.modules or [])
    )


async def process_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, now: datetime
) -> automation.Tick | None:
    """Una pasada en un cliente, dentro de su sesión acotada."""
    ctx = await load_ctx(session, tenant_id)
    if ctx is None:
        return None
    result = await automation.tick(session, ctx, now, offers=await _offers_on(session, tenant_id))
    if any(result.as_log().values()):
        log.info("reservations_cron.tenant", tenant_id=str(tenant_id), **result.as_log())
    return result


async def cron_pass(now: datetime | None = None) -> int:
    """Una pasada sobre todos los clientes con Reservas (la lista, fresca)."""
    return await pass_over_tenants(
        get_sessionmaker(),
        process_tenant,
        roster=Roster(ttl_seconds=0),
        name="reservations_cron",
        now=now,
    )


async def run_reservations_cron(
    *, stop: asyncio.Event, tick_seconds: float = DEFAULT_TICK_SECONDS
) -> None:
    await run_for_reservation_tenants(
        name="reservations_cron",
        stop=stop,
        tick_seconds=tick_seconds,
        process=process_tenant,
        # Cada minuto, la lista fresca: es el cron lento.
        roster=Roster(ttl_seconds=0),
    )


__all__ = [
    "DEFAULT_TICK_SECONDS",
    "Roster",
    "cron_pass",
    "pass_over_tenants",
    "process_tenant",
    "reservation_tenant_ids",
    "run_for_reservation_tenants",
    "run_reservations_cron",
]
