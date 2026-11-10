"""Los crons del dinero de la consola nueva — spec 047, T156 y T157 (requisitos 43
y 44; research D25 a D27).

- ``fx-rates-cron``: el cambio de referencia del BCE a ``fx_rates`` (cada 6 h; el
  BCE publica los días hábiles hacia las 16:00 CET y un día sin publicación usa el
  último).
- ``bag-refill-cron``: el día 1 UTC, el relleno de las bolsas con relleno, primero
  las que antes se quedarían sin saldo; lo que faltó se avisa al partner.
- ``bag-alerts-cron``: cada hora, los avisos de cada bolsa («Queda poco», «No
  llega a fin de mes», «Agotada»), deduplicados en la propia bolsa.
- ``ledger-reconciliation-cron``: cada día, el cuadre de cuenta + bolsas + gastado;
  una diferencia queda en el log como error y en las anomalías del admin.

Corren en el planificador (un solo proceso), partner a partner y solo con los que
cobran de las bolsas. Cada pasada es idempotente.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import ClientWallet, Partner

log = structlog.get_logger(__name__)

FX_TICK_SECONDS = 6 * 3600.0
HOURLY = 3600.0
DAILY = 24 * 3600.0


async def _bag_partners() -> list[uuid.UUID]:
    from nexus_api.services.wallet.bags import bags_active

    async with get_sessionmaker()() as session, session.begin():
        partners = (
            await session.scalars(
                sa.select(Partner.id).where(Partner.console_v2_enabled_at.is_not(None))
            )
        ).all()
    out: list[uuid.UUID] = []
    for partner_id in partners:
        async with get_sessionmaker()() as session, session.begin():
            await apply_partner_to_session(session, partner_id)
            if await bags_active(session, partner_id):
                out.append(partner_id)
    return out


async def fx_tick(fetch: Callable[[], Awaitable[Any]] | None = None) -> int:
    from nexus_api.services.wallet import fx

    day, rates = await (fetch() if fetch is not None else fx.fetch_ecb())
    async with get_sessionmaker()() as session, session.begin():
        return int(await fx.store(session, day, rates))


async def refill_tick(now: datetime | None = None) -> dict[str, Any]:
    """Solo el día 1 (UTC); las claves por mes hacen que repetirlo no rellene dos veces."""
    from nexus_api.services.channel_config import announce
    from nexus_api.services.wallet import bags
    from nexus_api.services.wallet.turns import after_balance_up

    now = now or datetime.now(UTC)
    if now.day != 1:
        return {}
    report: dict[str, Any] = {}
    for partner_id in await _bag_partners():
        async with get_sessionmaker()() as session, session.begin():
            await apply_partner_to_session(session, partner_id)
            before = await _balances(session, partner_id)
            shortfalls = await bags.refill_all(session, partner_id=partner_id, now=now)
            after = await _balances(session, partner_id)
        for tenant_id, balance in after.items():
            if not before.get(tenant_id) and balance:
                await after_balance_up(tenant_id)
        for short in shortfalls:
            await announce(
                tenant_id=uuid.UUID(short["tenant_id"]),
                kind="client.wallet.refill_short",
                severity="warning",
                data={"missing_micros": short["missing_micros"]},
                dedupe_key=f"refill_short:{short['tenant_id']}:{now.strftime('%Y-%m')}",
            )
        report[str(partner_id)] = shortfalls
        await _resume_capped(partner_id, now)
    return report


async def _resume_capped(partner_id: uuid.UUID, now: datetime) -> None:
    """Empieza el mes: los agentes que pausó su tope vuelven (44.3)."""
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.models import PartnerTenant
    from nexus_api.services import agent_states
    from nexus_api.services.wallet.bags import month_of

    month_start = datetime.combine(month_of(now), datetime.min.time(), UTC)
    async with get_sessionmaker()() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        tenants = (
            await session.scalars(
                sa.select(PartnerTenant.tenant_id).where(PartnerTenant.partner_id == partner_id)
            )
        ).all()
    for tenant_id in tenants:
        async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
            await agent_states.resume_after_cap(session, month_start=month_start)


async def _balances(session: Any, partner_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """El saldo de cada bolsa del partner, cliente a cliente (son del cliente)."""
    from nexus_api.services.wallet.bags import as_client, partner_tenants

    out: dict[uuid.UUID, int] = {}
    for tenant_id in await partner_tenants(session, partner_id):
        await as_client(session, tenant_id)
        balance = await session.scalar(
            sa.select(ClientWallet.balance_micros).where(ClientWallet.tenant_id == tenant_id)
        )
        if balance is not None:
            out[tenant_id] = int(balance)
    return out


async def alerts_tick() -> int:
    from nexus_api.services.wallet import alerts
    from nexus_api.services.wallet.bags import as_client, partner_tenants

    sent = 0
    for partner_id in await _bag_partners():
        async with get_sessionmaker()() as session, session.begin():
            await apply_partner_to_session(session, partner_id)
            notices: list[alerts.Alert] = []
            for tenant_id in await partner_tenants(session, partner_id):
                await as_client(session, tenant_id)
                bag = await session.scalar(
                    sa.select(ClientWallet)
                    .where(ClientWallet.tenant_id == tenant_id)
                    .with_for_update()
                )
                if bag is not None:
                    notices += await alerts.evaluate_bag(session, bag)
        await alerts.announce(notices)
        sent += len(notices)
    return sent


async def reconciliation_tick() -> list[dict[str, Any]]:
    from nexus_api.services.wallet.ledger import reconcile

    problems: list[dict[str, Any]] = []
    for partner_id in await _bag_partners():
        async with get_sessionmaker()() as session, session.begin():
            await apply_partner_to_session(session, partner_id)
            result = await reconcile(session, partner_id)
        if not result.ok:
            log.error(
                "wallet.reconciliation_mismatch",
                partner_id=str(partner_id),
                differences=result.differences,
            )
            problems.append({"partner_id": str(partner_id), "differences": result.differences})
    return problems


async def _loop(
    name: str, tick: Callable[[], Awaitable[Any]], stop: asyncio.Event, every: float
) -> None:
    log.info(f"{name}.start", tick_seconds=every)
    while not stop.is_set():
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error(f"{name}.tick_failed", error=str(exc)[:200])
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=every)
    log.info(f"{name}.stopped")


async def run_fx_rates_cron(*, stop: asyncio.Event) -> None:
    await _loop("fx_rates_cron", fx_tick, stop, FX_TICK_SECONDS)


async def run_bag_refill_cron(*, stop: asyncio.Event) -> None:
    await _loop("bag_refill_cron", refill_tick, stop, HOURLY)


async def run_bag_alerts_cron(*, stop: asyncio.Event) -> None:
    await _loop("bag_alerts_cron", alerts_tick, stop, HOURLY)


async def run_ledger_reconciliation_cron(*, stop: asyncio.Event) -> None:
    await _loop("ledger_reconciliation_cron", reconciliation_tick, stop, DAILY)


__all__ = [
    "alerts_tick",
    "fx_tick",
    "reconciliation_tick",
    "refill_tick",
    "run_bag_alerts_cron",
    "run_bag_refill_cron",
    "run_fx_rates_cron",
    "run_ledger_reconciliation_cron",
]
