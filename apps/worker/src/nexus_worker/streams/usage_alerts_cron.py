"""Usage-alerts cron (CP-24, migration 0087).

Every ``tick_seconds`` (15 min) evaluates every console-enabled partner
that has a monthly cap and alerts on: crossing 80 % / 100 % of the cap
creates ONE in-app notification per threshold and month and e-mails the
partner's recipients (``services/usage_alerts.py``). Idempotent by
construction (dedupe key), so overlapping ticks or a restart never
double-notify. Runs in the scheduler family (singleton).

The console also evaluates synchronously on ``GET /console/home``; the
cron is for partners that do not open the console every day.
"""

from __future__ import annotations

import asyncio
import contextlib

import sqlalchemy as sa
import structlog
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Partner, PartnerStatus
from nexus_api.services.usage_alerts import evaluate_partner_usage_alerts

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 15 * 60.0


async def evaluate_all_partners() -> int:
    """One pass over the eligible partners. Returns the number evaluated."""
    sm = get_sessionmaker()
    async with sm() as session:
        async with session.begin():
            partners = list(
                (
                    await session.execute(
                        sa.select(Partner).where(
                            Partner.console_enabled.is_(True),
                            Partner.usage_alerts_enabled.is_(True),
                            Partner.usage_cap_messages_month.is_not(None),
                            Partner.status == PartnerStatus.ACTIVE.value,
                        )
                    )
                ).scalars()
            )
        evaluated = 0
        for partner in partners:
            try:
                ev = await evaluate_partner_usage_alerts(session, partner)
                evaluated += 1
                if ev.created:
                    log.info(
                        "usage_alerts_cron.notified",
                        partner_id=str(partner.id),
                        thresholds=ev.created,
                        percent=ev.percent,
                    )
            except Exception as exc:
                log.error(
                    "usage_alerts_cron.partner_failed", partner_id=str(partner.id), error=str(exc)
                )
    return evaluated


async def run_usage_alerts_cron(
    *, stop: asyncio.Event, tick_seconds: float = DEFAULT_TICK_SECONDS
) -> None:
    """Background task. Returns when ``stop`` is set."""
    log.info("usage_alerts_cron.start", tick_seconds=tick_seconds)
    while not stop.is_set():
        try:
            n = await evaluate_all_partners()
            log.debug("usage_alerts_cron.tick", partners=n)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("usage_alerts_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("usage_alerts_cron.stopped")
