"""``reservation-templates-cron`` — las seis plantillas de WhatsApp de Reservas,
pedidas solas a Meta cada 15 min (spec 043, requisito 15).

Recorre los clientes **activos** (la lista sale de ``tenants``, sin RLS) y entra
en cada uno con su ``tenant_scoped_session``: allí
:func:`nexus_api.services.reservations.templates.ensure_templates` mira si tiene
Reservas encendido y un número de Meta, y pide a su WABA, con su token, las que
le faltan. Las reglas viven allí; aquí, el bucle.

- El que ya tiene las seis en el espejo no cuesta ninguna llamada a Meta.
- El cliente de Meta de la pasada no reintenta (``max_retries=1``): lo que falla
  lo intenta la pasada siguiente, no esta (15.5).
- Un cliente que falla no para a los demás. Del fallo se apunta el tipo, nunca
  su texto: el de Meta o el de la base pueden llevar datos de alguien.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections import Counter
from datetime import UTC, datetime

import sqlalchemy as sa
import structlog
from nexus_api.config import get_settings
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Tenant, TenantStatus
from nexus_api.services.reservations import templates
from nexus_channels.whatsapp_meta import MetaClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

log = structlog.get_logger(__name__)

NAME = "reservation_templates_cron"
DEFAULT_TICK_SECONDS = 15 * 60.0


def build_client() -> MetaClient:
    """El cliente de Meta de una pasada: un intento por llamada."""
    settings = get_settings()
    return MetaClient(
        app_secret=settings.meta_app_secret,
        require_appsecret_proof=settings.meta_require_appsecret_proof,
        version=settings.meta_graph_api_version,
        max_retries=1,
    )


async def active_tenant_ids(sm: async_sessionmaker[AsyncSession]) -> list[uuid.UUID]:
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


async def cron_pass(
    *,
    client: templates.TemplatesClient | None = None,
    sm: async_sessionmaker[AsyncSession] | None = None,
    now: datetime | None = None,
) -> Counter[str]:
    """Una pasada sobre todos los clientes activos. Devuelve lo que hizo, sumado.
    El ``client`` que se le pasa no se cierra: es de quien lo creó."""
    sm = sm or get_sessionmaker()
    owned: MetaClient | None = None
    if client is None:
        owned = client = build_client()
    meta: templates.TemplatesClient = client
    summary: Counter[str] = Counter()
    try:
        for tenant_id in await active_tenant_ids(sm):
            try:
                async with sm() as session, tenant_scoped_session(session, tenant_id):
                    out = await templates.ensure_templates(
                        session, client=meta, now=now or datetime.now(UTC)
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                summary["tenant_failed"] += 1
                log.error(
                    f"{NAME}.tenant_failed", tenant_id=str(tenant_id), error_type=type(exc).__name__
                )
                continue
            if out.skipped is not None:
                summary[out.skipped] += 1
            summary["requested"] += len(out.requested)
            summary["existing"] += len(out.existing)
            summary["failed"] += len(out.failed)
            if out.requested or out.existing or out.failed:
                log.info(f"{NAME}.tenant", tenant_id=str(tenant_id), **out.as_log())
    finally:
        if owned is not None:
            await owned.close()
    return summary


async def run_reservation_templates_cron(
    *, stop: asyncio.Event, tick_seconds: float = DEFAULT_TICK_SECONDS
) -> None:
    log.info(f"{NAME}.start", tick_seconds=tick_seconds)
    while not stop.is_set():
        try:
            summary = await cron_pass()
            if summary["requested"] or summary["failed"] or summary["tenant_failed"]:
                log.info(f"{NAME}.pass", **dict(summary))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error(f"{NAME}.tick_failed", error_type=type(exc).__name__)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info(f"{NAME}.stopped")


__all__ = [
    "DEFAULT_TICK_SECONDS",
    "active_tenant_ids",
    "build_client",
    "cron_pass",
    "run_reservation_templates_cron",
]
