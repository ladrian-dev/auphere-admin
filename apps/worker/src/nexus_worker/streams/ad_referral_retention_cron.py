"""Borrar el identificador del clic de un anuncio a los 90 días — spec 076, requisito 1.7.

Una vez al día, tenant a tenant (``tenant_scoped_session``, como
``meta_social_cron``): con FORCE RLS y el rol ``nexus_app``, una pasada sin
tenant no vería ninguna fila. Pone a NULL ``customer_ad_referrals.ctwa_clid``
de los clics de hace más de ``retention_ad_click_days``, por lotes; el anuncio,
el titular y el enlace se quedan, porque la Bandeja y el informe los usan.

``retention_ad_click_days <= 0`` apaga el paso, como las otras ventanas de
``data_retention_cron``: un error de configuración tiene que producir «no se
borró nada». Construir la corrutina no hace E/S (``test_bootstrap_split``).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import CustomerAdReferral, Tenant

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 86_400.0
BATCH = 1000


async def clear_old_clicks(tenant_id: uuid.UUID, *, days: int, now: datetime | None = None) -> int:
    """Clics de este tenant que pierden su ``ctwa_clid``. Devuelve cuántos."""
    if days <= 0:
        return 0
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    sm = get_sessionmaker()
    total = 0
    while True:
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            due = (
                sa.select(CustomerAdReferral.id)
                .where(
                    CustomerAdReferral.ctwa_clid.is_not(None),
                    CustomerAdReferral.clicked_at < cutoff,
                )
                .limit(BATCH)
                .scalar_subquery()
            )
            result = await session.execute(
                sa.update(CustomerAdReferral)
                .where(CustomerAdReferral.id.in_(due))
                .values(ctwa_clid=None, updated_at=sa.func.now())
                .execution_options(synchronize_session=False)
            )
            await session.commit()
        cleared = int(getattr(result, "rowcount", 0) or 0)
        total += cleared
        if cleared < BATCH:
            return total


async def run_ad_referral_retention_cron(
    *, stop: asyncio.Event, tick_seconds: float = DEFAULT_TICK_SECONDS
) -> None:
    from nexus_worker.config import get_worker_settings

    log.info("ad_referral_retention_cron.start", tick_seconds=tick_seconds)
    while not stop.is_set():
        days = get_worker_settings().retention_ad_click_days
        try:
            if days > 0:
                sm = get_sessionmaker()
                async with sm() as session:
                    tenant_ids = list((await session.scalars(sa.select(Tenant.id))).all())
                for tid in tenant_ids:
                    if stop.is_set():
                        break
                    cleared = await clear_old_clicks(tid, days=days)
                    if cleared:
                        log.info(
                            "ad_referral_retention.cleared", tenant_id=str(tid), clicks=cleared
                        )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("ad_referral_retention_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("ad_referral_retention_cron.stopped")
