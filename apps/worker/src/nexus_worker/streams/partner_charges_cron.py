"""Automatic charges to partners' saved cards (spec 041).

Every few minutes: top up the partners on **automatic recharge** whose
purchased balance fell below their threshold. On the **1st** (Spain time, the
billing timezone of ``partner_receipt_cron``): charge the **postpaid**
partners what they consumed beyond their balance last month — and retry,
once a day, a postpaid charge that did not go through.

Both are safe to repeat: a charge row is unique on its key, and the balance
goes up only once per paid invoice (``services/partner_billing``). Without
Stripe keys nothing runs — a closed billing is not a declined card.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
from zoneinfo import ZoneInfo

import structlog
from nexus_api.config import get_settings
from nexus_api.services.partner_billing import (
    refresh_waiting_charges,
    run_auto_recharges,
    run_postpaid_settlement,
)

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 300.0
_BILLING_TZ = ZoneInfo("Europe/Madrid")


async def tick(now: datetime | None = None) -> None:
    if not get_settings().billing_enabled:
        return
    # First: a charge Stripe already paid but we still see waiting (a lost
    # notice) is settled, so it neither blocks the next top-up nor is retried.
    refreshed = await refresh_waiting_charges()
    if refreshed:
        log.info("partner_charges.refreshed", settled=refreshed)
    recharges = await run_auto_recharges()
    if recharges:
        log.info("partner_charges.recharges", outcomes=[o.status for o in recharges])
    # The settlement decides itself: last month's debt on the 1st, and a
    # daily retry for a line frozen by a charge that did not go through.
    local = (now or datetime.now(_BILLING_TZ)).astimezone(_BILLING_TZ)
    settled = await run_postpaid_settlement(local)
    if settled:
        log.info("partner_charges.postpaid", outcomes=[o.status for o in settled])


async def run_partner_charges_cron(
    *, stop: asyncio.Event, tick_seconds: float = DEFAULT_TICK_SECONDS
) -> None:
    """Background task. Returns when ``stop`` is set."""
    log.info("partner_charges_cron.start", tick_seconds=tick_seconds)
    while not stop.is_set():
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("partner_charges_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("partner_charges_cron.stopped")
