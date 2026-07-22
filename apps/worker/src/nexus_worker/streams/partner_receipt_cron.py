"""Monthly partner-receipt sweep — emits the *recibo* on day 1, mails it.

Billing cycle (fixed policy): each receipt covers the **previous calendar
month** (1st→last), is emitted on the **1st**, and is due on the **5th**.
The emission day is evaluated in Chile time (``America/Santiago``), the
timezone of the businesses being billed.

Once per emission day, for every ACTIVE partner that owns at least one tenant:

1. ``generate_partner_receipt`` builds (or returns) the USD invoice for the
   previous month — idempotent via the ``(partner, period)`` unique index, so
   the hourly tick creating it only happens once and later ticks are no-ops.
2. When the receipt was **just created** and the partner has a
   ``billing_email``, the recibo is mailed (best-effort). Re-runs return
   ``created=False`` and never re-send.

Multi-tenant / replicable by design: onboarding another partner needs no code
change — create the partner, associate its tenants with a billing model, set
``billing_email``, and it starts receiving monthly recibos.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

import sqlalchemy as sa
import structlog
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Partner, PartnerStatus, PartnerTenant
from nexus_api.services.email import send_email
from nexus_api.services.partner_receipt import ReceiptResult, generate_partner_receipt
from nexus_api.services.partner_receipt_email import receipt_subject, render_receipt_html

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 3600.0  # hourly; idempotency makes the real work fire once
_BILLING_TZ = ZoneInfo("America/Santiago")
# Emission day-of-month. Overridable for a manual back-run / testing.
EMISSION_DAY = int(os.getenv("NEXUS_RECEIPT_EMISSION_DAY", "1"))


def _previous_month(today: date) -> tuple[int, int]:
    """(year, month) of the calendar month before ``today``."""
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


async def run_partner_receipt_cron(
    *, stop: asyncio.Event, tick_seconds: float = DEFAULT_TICK_SECONDS
) -> None:
    """Background task. Returns when ``stop`` is set."""
    log.info("partner_receipt_cron.start", tick_seconds=tick_seconds, emission_day=EMISSION_DAY)
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            await _maybe_emit(sm)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("partner_receipt_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("partner_receipt_cron.stopped")


async def _maybe_emit(sm: sa.orm.sessionmaker) -> None:  # type: ignore[type-arg]
    today = datetime.now(_BILLING_TZ).date()
    if today.day != EMISSION_DAY:
        return
    year, month = _previous_month(today)
    async with sm() as session:
        slugs = (
            (
                await session.execute(
                    sa.select(Partner.slug)
                    .join(PartnerTenant, PartnerTenant.partner_id == Partner.id)
                    .where(Partner.status == PartnerStatus.ACTIVE.value)
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
    log.info("partner_receipt_cron.emitting", period=f"{year}-{month:02d}", partners=len(slugs))
    for slug in slugs:
        try:
            await _emit_one(sm, slug, year, month, today)
        except Exception as exc:
            log.warning("partner_receipt_cron.partner_failed", partner=slug, error=str(exc))


async def _emit_one(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
    slug: str,
    year: int,
    month: int,
    emission_date: date,
) -> None:
    receipt = await generate_partner_receipt(
        sm,
        partner_slug=slug,
        period_year=year,
        period_month=month,
        emission_date=emission_date,
    )
    if receipt.created and receipt.billing_email:
        await _mail_receipt(receipt)
    elif receipt.created:
        log.warning("partner_receipt_cron.no_billing_email", partner=slug)


async def _mail_receipt(receipt: ReceiptResult) -> None:
    assert receipt.billing_email is not None
    await send_email(
        to=receipt.billing_email,
        subject=receipt_subject(receipt),
        html=render_receipt_html(receipt),
    )
