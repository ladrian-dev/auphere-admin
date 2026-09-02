"""D3 — renueva el included del mes y siembra la cuota que falte.

Los dos pasos del runbook manual «las tres puertas», automatizados y **en
este orden**, que no es opcional:

1. ``renew_included_if_expired`` repone el included caducado. Hasta aquí
   ``included_expires_at`` nacía a fin de mes y nada lo renovaba: el día 1 el
   saldo efectivo pasaba a 0 y con él se cerraba ``allow_channel_turn`` para
   todos los clientes del partner, sin error y sin aviso.
2. ``seed_default_allocation`` da cuota a los clientes que no la tienen.

El orden importa porque el cap se calcula sobre el disponible del wallet: con
el included caducado, ``available`` es 0 y **cualquier asignación de cuota
sale 0** — por SQL, por API y desde la consola. Sembrar antes de renovar
produce filas a 0 que parecen correctas y dejan al cliente igual de mudo,
que es peor que no tener fila.

Se dispara por **caducidad, no por calendario**. Un cron atado al día 1 que
se pierde su ventana —scheduler caído, rollback, despliegue largo— deja el
mes entero sin saldo. Así, si el included está caducado, se repone en el
siguiente tick. Ambos pasos son idempotentes: con el wallet vigente y las
cuotas puestas, el tick horario no escribe nada.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

import sqlalchemy as sa
import structlog
from nexus_api.config import get_settings
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Partner, PartnerStatus, Tenant, TenantStatus
from nexus_api.metering.wallet import renew_included_if_expired, seed_default_allocation

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 3600.0  # horario; la idempotencia hace el trabajo una vez

#: Un cliente archivado no atiende a nadie, así que no reserva saldo. Los
#: ``provisioning`` sí: son clientes recién creados que todavía no han
#: conectado WhatsApp, y quedarse sin cuota es justo lo que les impediría
#: contestar al primer mensaje.
_QUOTA_STATES = (TenantStatus.ACTIVE, TenantStatus.PROVISIONING, TenantStatus.PAUSED)


async def _partner_ids(sm: object) -> list[tuple[uuid.UUID, int]]:
    async with sm() as session:  # type: ignore[operator]
        rows = await session.execute(
            sa.select(Partner.id, Partner.companion_monthly_token_cap).where(
                Partner.status == PartnerStatus.ACTIVE
            )
        )
        return [(r[0], int(r[1] or 0)) for r in rows.all()]


async def _tenant_ids(sm: object, partner_id: uuid.UUID) -> list[uuid.UUID]:
    async with sm() as session:  # type: ignore[operator]
        rows = await session.execute(
            sa.select(Tenant.id).where(
                Tenant.partner_id == partner_id,
                Tenant.status.in_(_QUOTA_STATES),
            )
        )
        return [r[0] for r in rows.all()]


async def sweep_once(sm: object) -> dict[str, int]:
    """Un barrido. Devuelve el recuento, para el log y para los tests."""
    settings = get_settings()
    default_cap = settings.partner_default_client_allocation_tokens
    renewed = 0
    seeded = 0

    for partner_id, monthly_cap in await _partner_ids(sm):
        try:
            async with sm() as session, session.begin():  # type: ignore[operator]
                await apply_partner_to_session(session, partner_id)
                if await renew_included_if_expired(
                    session, partner_id=partner_id, monthly_cap=monthly_cap
                ):
                    renewed += 1
        except Exception as exc:
            # Un partner que falla no puede dejar sin saldo a los demás.
            log.error(
                "wallet_renewal_cron.renew_failed", partner_id=str(partner_id), error=str(exc)
            )
            continue

        for tenant_id in await _tenant_ids(sm, partner_id):
            try:
                async with sm() as session, session.begin():  # type: ignore[operator]
                    await apply_partner_to_session(session, partner_id)
                    before = await session.scalar(
                        sa.text(
                            "SELECT count(*) FROM partner_allocations "
                            "WHERE partner_id = :p AND tenant_id = :t"
                        ),
                        {"p": str(partner_id), "t": str(tenant_id)},
                    )
                    if int(before or 0) > 0:
                        continue
                    await seed_default_allocation(
                        session,
                        partner_id=partner_id,
                        tenant_id=tenant_id,
                        default_cap=default_cap,
                    )
                    seeded += 1
            except Exception as exc:
                log.error(
                    "wallet_renewal_cron.seed_failed",
                    partner_id=str(partner_id),
                    tenant_id=str(tenant_id),
                    error=str(exc),
                )

    if renewed or seeded:
        log.info("wallet_renewal_cron.swept", renewed=renewed, seeded=seeded)
    return {"renewed": renewed, "seeded": seeded}


async def run_wallet_renewal_cron(
    *, stop: asyncio.Event, tick_seconds: float = DEFAULT_TICK_SECONDS
) -> None:
    """Background task. Returns when ``stop`` is set."""
    log.info("wallet_renewal_cron.start", tick_seconds=tick_seconds)
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            await sweep_once(sm)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("wallet_renewal_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("wallet_renewal_cron.stopped")
