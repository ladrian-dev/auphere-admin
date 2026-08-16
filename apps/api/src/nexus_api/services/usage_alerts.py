"""Usage alerts of a partner (CP-24, migration 0087).

A partner may set a monthly cap of **channel messages** (units, C9) across
all its clients. When the natural month's usage crosses 80 % and 100 % of
that cap, this module:

1. inserts ONE ``console_notifications`` row per threshold and month
   (``dedupe_key = partner:<id>:usage:<80|100>:<YYYY-MM>``, unique index of
   0086 → re-evaluating never duplicates), and
2. e-mails ``partners.usage_alert_recipients`` (Resend via
   ``services/email.py``, best-effort: a failed mail never fails the
   evaluation, the in-app notification is the durable record).

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
from html import escape

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
from nexus_api.services.email import send_email

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


async def _notify_by_email(partner: Partner, ev: AlertEvaluation, since: datetime) -> bool:
    recipients = [r for r in (partner.usage_alert_recipients or []) if isinstance(r, str) and r]
    if not recipients:
        return False
    top = max(ev.created)
    period = f"{since:%Y-%m}"
    used = f"{ev.used:,.0f}"
    cap = f"{ev.cap:,}" if ev.cap is not None else "—"
    if top >= 100:
        subject = f"[Auphere] {partner.name}: tope mensual de mensajes alcanzado ({period})"
        headline = "Habéis alcanzado el 100 % del tope mensual de mensajes."
        note = (
            "El servicio sigue activo: en esta versión el tope solo avisa. "
            "Si necesitáis ampliarlo, respondednos a este correo."
        )
    else:
        subject = f"[Auphere] {partner.name}: {top} % del tope mensual de mensajes ({period})"
        headline = f"Habéis superado el {top} % del tope mensual de mensajes."
        note = "Al llegar al 100 % os avisaremos de nuevo. El servicio no se interrumpe."
    html = f"""\
<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;color:#111">
  <h2 style="margin:0 0 8px">{escape(headline)}</h2>
  <p style="margin:0 0 16px;color:#555">{escape(partner.name)} · {period}</p>
  <p style="margin:0 0 8px;font-size:15px"><strong>Mensajes del mes:</strong> {used} de {cap}</p>
  <p style="margin:0 0 16px;font-size:14px;color:#333">{escape(note)}</p>
  <p style="color:#999;font-size:12px;margin:24px 0 0">Auphere · alerta de consumo configurada en la consola de partners (Consumo → Alertas).</p>
</div>"""
    try:
        sent = await send_email(to=recipients, subject=subject, html=html)
    except Exception as exc:  # pragma: no cover - send_email already swallows
        log.warning("usage_alerts.email_failed", partner_id=str(partner.id), error=str(exc))
        return False
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
