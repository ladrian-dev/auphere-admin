"""``conversion-events-dispatcher`` — envía los eventos de conversión a Meta (spec 076).

En ``egress``, como ``push-dispatcher``: una cola que se vacía no es un cron.
Cada ``conversion_dispatch_tick_seconds`` (60 s; Meta pide menos de una hora):

1. la sesión de identidad dice qué tenants tienen eventos que tocan;
2. por tenant, ``ad_conversion_dispatch.claim`` en su transacción;
3. el envío a Meta, **un evento por petición**, fuera de cualquier transacción;
4. ``ad_conversion_dispatch.settle`` en otra transacción.

La decisión vive en la API (``services/ad_conversion_dispatch.py``); aquí solo
el bucle y la llamada. Construir la corrutina no hace E/S
(``test_bootstrap_split``). Ningún log lleva el token, el clic ni el teléfono.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Awaitable, Callable

import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.services import ad_conversion_dispatch as dispatch
from nexus_api.services.ad_conversion_dispatch import Outcome, Outgoing
from nexus_api.services.ad_measurement import REAUTHORIZE
from nexus_channels.whatsapp_meta.exceptions import (
    MetaAPIError,
    MetaRateLimitedError,
    MetaTransientError,
    TokenInvalidatedError,
)
from nexus_channels.whatsapp_meta.meta_client import MetaClient

log = structlog.get_logger(__name__)

MAX_CONCURRENT_TENANTS = 4
#: Códigos de Graph que dicen que falta un permiso (provisionales: se fijan con
#: las respuestas reales de staging, research D8).
_PERMISSION_CODES = frozenset({10, 200})

Send = Callable[[Outgoing], Awaitable[Outcome]]


def _client() -> MetaClient:
    from nexus_api.services.meta_signup_service import build_meta_client

    return build_meta_client()


async def deliver(out: Outgoing, client: MetaClient) -> Outcome:
    """Un evento a Meta. Nunca lanza: lo inesperado se reintenta."""
    try:
        await client.send_conversion_event(
            dataset_id=out.dataset_id,
            access_token=out.access_token,
            event=out.event,
            partner_agent=dispatch.PARTNER_AGENT,
            test_event_code=out.test_event_code,
        )
    except TokenInvalidatedError:
        return Outcome("failed", REAUTHORIZE)
    except (MetaRateLimitedError, MetaTransientError):
        return Outcome("retry", "meta_transient")
    except MetaAPIError as exc:
        if exc.code in _PERMISSION_CODES or (exc.code is not None and 200 <= exc.code <= 299):
            return Outcome("failed", REAUTHORIZE)
        return Outcome("failed", f"meta_{exc.code}" if exc.code is not None else "meta_error")
    except Exception as exc:  # pragma: no cover - defensa: el despachador sigue
        log.warning(
            "ad_conversion.deliver_unexpected",
            tenant_id=str(out.tenant_id),
            error=type(exc).__name__,
        )
        return Outcome("retry", "unexpected")
    return Outcome("sent")


async def drain_tenant(tenant_id: uuid.UUID, *, send: Send | None = None) -> int:
    """Un tenant: reservar, enviar, anotar. Devuelve cuántos eventos intentó."""
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        outgoing = await dispatch.claim(session)
    if not outgoing:
        return 0
    client: MetaClient | None = None
    if send is None:
        client = _client()

        async def _send(o: Outgoing) -> Outcome:
            assert client is not None
            return await deliver(o, client)

        send = _send
    try:
        results = [(o, await send(o)) for o in outgoing]
    finally:
        if client is not None:
            await client.close()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        await dispatch.settle(session, results)
    return len(results)


async def run_conversion_dispatcher(
    *, stop: asyncio.Event, tick_seconds: float | None = None
) -> None:
    """La tarea. Vuelve cuando ``stop`` se activa."""
    from nexus_worker.config import get_worker_settings

    tick = (
        tick_seconds
        if tick_seconds is not None
        else get_worker_settings().conversion_dispatch_tick_seconds
    )
    log.info("ad_conversion.dispatcher.start", tick_seconds=tick)
    tenants = asyncio.Semaphore(MAX_CONCURRENT_TENANTS)

    async def _drain(tid: uuid.UUID) -> None:
        async with tenants:
            try:
                await drain_tenant(tid)
            except Exception as exc:
                log.error(
                    "ad_conversion.dispatcher.drain_failed",
                    tenant_id=str(tid),
                    error=type(exc).__name__,
                )

    while not stop.is_set():
        try:
            async with get_sessionmaker()() as identity:
                due = await dispatch.tenants_with_pending(identity)
            if due:
                await asyncio.gather(*(_drain(tid) for tid in due))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("ad_conversion.dispatcher.tick_failed", error=type(exc).__name__)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick)
    log.info("ad_conversion.dispatcher.stopped")
