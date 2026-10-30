"""Usage alerts of a partner (CP-24, migration 0087).

A partner may set a monthly cap of **channel messages** (units, C9) across
all its clients. When the natural month's usage crosses 80 % and 100 % of
that cap, this module:

1. inserts ONE ``console_notifications`` row per threshold and month
   (``dedupe_key = partner:<id>:usage:<80|100>:<YYYY-MM>``, unique index of
   0086 → re-evaluating never duplicates), and
2. e-mails ``partners.usage_alert_recipients`` (spec 051: the
   ``usage_cap_threshold`` / ``usage_cap_reached`` templates, each person in
   the language of their console account; best-effort: a failed mail never
   fails the evaluation, the in-app notification is the durable record).

**v1 warns, it does not cut.** At 100 % nothing stops: no channel is
paused and no message is refused. Cutting a partner's end customers off
over a commercial cap is a contract decision, and it belongs to the
Stripe phase together with the price. The plan's wording — "aviso ANTES
de quedarse sin servicio" — is met by the 80 % mail.

Called from two places: the worker cron ``usage_alerts_cron`` (every 15
min, all console partners with a cap) and, synchronously and cheaply,
``GET /console/home`` (so a partner that only uses the console gets the
alert without depending on the cron being deployed).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

import sqlalchemy as sa
import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    ConsoleNotification,
    NotificationKind,
    NotificationSeverity,
    Partner,
    UsageRecord,
)
from nexus_api.services.console_reporting import (
    month_bounds,
    partner_mappings,
    percent_of,
    reporting_transaction,
    tenant_ids_of,
)
from nexus_api.services.email_catalog import EmailKind, console_link, format_month

log = structlog.get_logger(__name__)

THRESHOLDS: tuple[int, ...] = (80, 100)
CAP_METER = "channel.message"


async def channel_units_month(
    session: AsyncSession,
    tenant_ids: list[uuid.UUID],
    since: datetime,
    until: datetime,
) -> float:
    """Billable ``channel.message`` units of ``source='channel'`` in
    ``[since, until)`` across ``tenant_ids`` — one query under the reporting
    role. QA never counts towards a cap (0079)."""
    if not tenant_ids:
        return 0.0
    async with reporting_transaction(session):
        value = await session.scalar(
            sa.select(sa.func.coalesce(sa.func.sum(UsageRecord.billable_qty), 0)).where(
                UsageRecord.tenant_id.in_(tenant_ids),
                UsageRecord.meter == CAP_METER,
                UsageRecord.source == "channel",
                UsageRecord.occurred_at >= since,
                UsageRecord.occurred_at < until,
            )
        )
    return float(value or 0)


@dataclass
class AlertEvaluation:
    used: float
    cap: int | None
    percent: float | None
    created: list[int] = field(default_factory=list)  # thresholds notified this call
    emailed: bool = False


def dedupe_key(partner_id: uuid.UUID, threshold: int, since: datetime) -> str:
    return f"partner:{partner_id}:usage:{threshold}:{since:%Y-%m}"


async def evaluate_partner_usage_alerts(
    session: AsyncSession,
    partner: Partner,
    *,
    used: float | None = None,
    now: datetime | None = None,
) -> AlertEvaluation:
    """Evaluate the partner against its cap and notify crossed thresholds
    once per month. Manages its own short transactions. Never raises on
    e-mail failure."""
    cap = partner.usage_cap_messages_month
    since, until, _elapsed, _days = month_bounds(now)
    if used is None:
        mappings = await partner_mappings(session, partner.id)
        used = await channel_units_month(session, tenant_ids_of(mappings), since, until)
    result = AlertEvaluation(used=used, cap=cap, percent=percent_of(used, cap))
    if not partner.usage_alerts_enabled or cap is None or cap <= 0 or result.percent is None:
        return result

    for threshold in THRESHOLDS:
        if result.percent < threshold:
            continue
        kind = (
            NotificationKind.USAGE_CAP_REACHED
            if threshold >= 100
            else NotificationKind.USAGE_THRESHOLD
        )
        severity = (
            NotificationSeverity.CRITICAL if threshold >= 100 else NotificationSeverity.WARNING
        )
        stmt = (
            pg_insert(ConsoleNotification)
            .values(
                partner_id=partner.id,
                kind=kind.value,
                severity=severity.value,
                payload={
                    "percent": threshold,
                    "cap": cap,
                    "used": round(used, 3),
                    "period": f"{since:%Y-%m}",
                },
                dedupe_key=dedupe_key(partner.id, threshold, since),
            )
            .on_conflict_do_nothing(
                index_elements=["dedupe_key"], index_where=sa.text("dedupe_key IS NOT NULL")
            )
        )
        async with session.begin():
            inserted = await session.execute(stmt.returning(ConsoleNotification.id))
            if inserted.scalar_one_or_none() is not None:
                result.created.append(threshold)

    if result.created:
        result.emailed = await _notify_by_email(partner, result, since)
    return result


def format_count(value: float, locale: str) -> str:
    """A whole count as the reader writes it: «1.234» in Spanish, «1,234» in English."""
    text = f"{value:,.0f}"
    return text if locale == "en" else text.replace(",", ".")


async def _notify_by_email(partner: Partner, ev: AlertEvaluation, since: datetime) -> bool:
    """Spec 051: ``usage_cap_threshold`` at 80 %, ``usage_cap_reached`` at 100 %.
    When both are crossed at once only the 100 % one goes out."""
    from nexus_api.services.email import send_localized

    recipients = [r for r in (partner.usage_alert_recipients or []) if isinstance(r, str) and r]
    if not recipients or ev.cap is None:
        return False
    top = max(ev.created)
    cap = ev.cap

    if top >= 100:

        def compose_reached(locale: str) -> tuple[str, dict[str, str]]:
            subject = (
                "You've reached your monthly message limit"
                if locale == "en"
                else "Has alcanzado tu límite mensual de mensajes"
            )
            return subject, {
                "PARTNER_NAME": partner.name,
                "CAP": format_count(cap, locale),
                "PERIOD": format_month(since.year, since.month, locale),
                "ALERTS_URL": console_link("/usage/alerts"),
            }

        sent = await send_localized(
            EmailKind.USAGE_CAP_REACHED,
            to=recipients,
            compose=compose_reached,
            partner_id=partner.id,
        )
    else:
        # The real percentage, rounded down: never more than there is, and,
        # the threshold being whole, never less than the one just crossed.
        percent = str(int(ev.percent if ev.percent is not None else top))

        def compose_threshold(locale: str) -> tuple[str, dict[str, str]]:
            subject = (
                f"You've used {percent}% of your monthly message limit"
                if locale == "en"
                else f"Llevas el {percent} % de tu límite mensual de mensajes"
            )
            return subject, {
                "PARTNER_NAME": partner.name,
                "PERCENT": percent,
                "USED": format_count(ev.used, locale),
                "CAP": format_count(cap, locale),
                "PERIOD": format_month(since.year, since.month, locale),
                "USAGE_URL": console_link("/usage"),
            }

        sent = await send_localized(
            EmailKind.USAGE_CAP_THRESHOLD,
            to=recipients,
            compose=compose_threshold,
            partner_id=partner.id,
        )
    log.info(
        "usage_alerts.notified",
        partner_id=str(partner.id),
        thresholds=ev.created,
        emailed=sent,
        recipients=len(recipients),
    )
    return sent


__all__ = [
    "CAP_METER",
    "THRESHOLDS",
    "AlertEvaluation",
    "channel_units_month",
    "dedupe_key",
    "evaluate_partner_usage_alerts",
]
