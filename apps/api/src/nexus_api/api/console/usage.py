"""``/console/usage`` — consumption in **units**, per client, meter and
source (CP-22 + CP-24 backend, decision C9).

What the partner sees: quantities from ``usage_records`` (tokens, messages,
minutes, media…) split by ``source`` (``channel`` = the client's traffic,
``qa`` = the partner's own tests in the playground), a daily series per
meter, a linear end-of-month projection, the monthly cap (0087) with its
percentage, and how many rows are still *unpriced* (``cost_usd IS
NULL``) — a hint that Auphere has not valued something yet. What the
partner does NOT see: ``cost_usd`` itself — that is Auphere's cost and
showing it is showing the margin.

Reads run as ONE query per endpoint under the read-only reporting role
(``services/console_reporting.py``) with ``tenant_id = ANY(partner's
clients)`` — instead of one RLS transaction per client, which is what
this file did before and does not scale past a few dozen clients.

Endpoints: ``GET /usage`` (report + month block), ``GET /usage/series``
(per day x meter), ``GET /usage/export.csv`` (streaming, localized
header), ``GET|PUT /usage/alerts`` (cap, recipients, switch).
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.db.models import AuditLog, Partner, PartnerTenant, UsageRecord
from nexus_api.services.console_reporting import (
    csv_safe,
    month_bounds,
    partner_mappings,
    percent_of,
    project_month,
    reporting_transaction,
    tenant_ids_of,
)
from nexus_api.services.usage_alerts import channel_units_month

from .schemas import UsageBucketOut
from .schemas_home_usage import (
    UsageAlertsIn,
    UsageAlertsOut,
    UsageMonthOut,
    UsageReportV2Out,
    UsageSeriesOut,
    UsageSeriesPointOut,
)

router = APIRouter(prefix="/usage")

_CSV_HEADERS: dict[str, list[str]] = {
    "en": [
        "client_ref",
        "client_name",
        "day",
        "meter",
        "source",
        "quantity",
        "billable_units",
        "records",
    ],
    "es": [
        "ref_cliente",
        "cliente",
        "dia",
        "medidor",
        "origen",
        "cantidad",
        "unidades_facturables",
        "registros",
    ],
}


def _window(days: int) -> tuple[datetime, datetime]:
    until = datetime.now(UTC)
    return until - timedelta(days=days), until


def _scope(
    mappings: Sequence[PartnerTenant], client: str | None
) -> tuple[list[PartnerTenant], dict[uuid.UUID, PartnerTenant]]:
    chosen = [m for m in mappings if client is None or m.external_client_ref == client]
    return chosen, {m.tenant_id: m for m in chosen}


async def _month_block(
    session: AsyncSession, partner: Partner, tenant_ids: list[uuid.UUID]
) -> UsageMonthOut:
    since, until, elapsed, days_in_month = month_bounds()
    units = await channel_units_month(session, tenant_ids, since, until)
    cap = partner.usage_cap_messages_month
    return UsageMonthOut(
        since=since,
        until=until,
        units=units,
        cap=cap,
        percent=percent_of(units, cap),
        projected_month_units=project_month(units, elapsed, days_in_month),
        basis_days=elapsed,
        days_in_month=days_in_month,
    )


# ── report ─────────────────────────────────────────────────────────────


@router.get("", response_model=UsageReportV2Out)
async def usage_report(
    principal: ConsolePrincipal = Depends(require_console_principal("usage:read")),
    session: AsyncSession = Depends(get_db_session),
    days: int = Query(default=30, ge=1, le=366),
    client: str | None = Query(
        default=None, max_length=255, description="Restrict to one external_client_ref"
    ),
    source: str | None = Query(default=None, pattern="^(channel|qa)$"),
) -> UsageReportV2Out:
    since, until = _window(days)
    mappings = await partner_mappings(session, principal.partner.id)
    _chosen, by_tenant = _scope(mappings, client)
    tenant_ids = list(by_tenant)

    buckets: list[UsageBucketOut] = []
    totals: dict[str, float] = {}
    total_records = 0
    unpriced = 0
    if tenant_ids:
        stmt = (
            sa.select(
                UsageRecord.tenant_id,
                UsageRecord.meter,
                UsageRecord.source,
                sa.func.coalesce(sa.func.sum(UsageRecord.quantity), 0),
                sa.func.coalesce(sa.func.sum(UsageRecord.billable_qty), 0),
                sa.func.count(),
                sa.func.count().filter(UsageRecord.cost_usd.is_(None)),
            )
            .where(
                UsageRecord.tenant_id.in_(tenant_ids),
                UsageRecord.occurred_at >= since,
                UsageRecord.occurred_at < until,
            )
            .group_by(UsageRecord.tenant_id, UsageRecord.meter, UsageRecord.source)
        )
        if source is not None:
            stmt = stmt.where(UsageRecord.source == source)
        async with reporting_transaction(session):
            rows = (await session.execute(stmt)).all()
        # Order by client ref, then meter, then source (stable for the UI).
        rows = sorted(rows, key=lambda r: (by_tenant[r[0]].external_client_ref, r[1], r[2]))
        for tid, meter, src, qty, billable, count, no_price in rows:
            mapping = by_tenant[tid]
            buckets.append(
                UsageBucketOut(
                    external_client_ref=mapping.external_client_ref,
                    client_name=mapping.client_name,
                    meter=str(meter),
                    source=str(src),
                    quantity=float(qty),
                    billable_qty=float(billable),
                    records=int(count),
                )
            )
            # Totals count the client's traffic only — QA is the partner's
            # own testing and never enters the billable total (0079).
            if str(src) == "channel":
                totals[str(meter)] = totals.get(str(meter), 0.0) + float(billable)
            total_records += int(count)
            unpriced += int(no_price)

    return UsageReportV2Out(
        since=since,
        until=until,
        buckets=buckets,
        totals_by_meter=totals,
        total_records=total_records,
        month=await _month_block(session, principal.partner, tenant_ids_of(mappings)),
        unpriced_records=unpriced,
    )


# ── daily series ───────────────────────────────────────────────────────


@router.get("/series", response_model=UsageSeriesOut)
async def usage_series(
    principal: ConsolePrincipal = Depends(require_console_principal("usage:read")),
    session: AsyncSession = Depends(get_db_session),
    days: int = Query(default=30, ge=1, le=366),
    client: str | None = Query(default=None, max_length=255),
    source: str = Query(default="channel", pattern="^(channel|qa)$"),
    meter: str | None = Query(default=None, max_length=60, description="Prefix match (e.g. llm.)"),
) -> UsageSeriesOut:
    since, until = _window(days)
    mappings = await partner_mappings(session, principal.partner.id)
    _chosen, by_tenant = _scope(mappings, client)
    tenant_ids = list(by_tenant)
    day_col = sa.cast(sa.func.timezone("UTC", UsageRecord.occurred_at), sa.Date)
    points: dict[date, dict[str, float]] = {}
    meters: set[str] = set()
    if tenant_ids:
        stmt = (
            sa.select(
                day_col,
                UsageRecord.meter,
                sa.func.coalesce(sa.func.sum(UsageRecord.billable_qty), 0),
            )
            .where(
                UsageRecord.tenant_id.in_(tenant_ids),
                UsageRecord.source == source,
                UsageRecord.occurred_at >= since,
                UsageRecord.occurred_at < until,
            )
            .group_by(day_col, UsageRecord.meter)
        )
        if meter:
            stmt = stmt.where(UsageRecord.meter.like(f"{meter}%"))
        async with reporting_transaction(session):
            rows = (await session.execute(stmt)).all()
        for day, m, qty in rows:
            points.setdefault(day, {})[str(m)] = float(qty)
            meters.add(str(m))
    # Dense series: one point per day even with nothing measured.
    out: list[UsageSeriesPointOut] = []
    day = since.date()
    last = until.date()
    while day <= last:
        out.append(UsageSeriesPointOut(day=day, by_meter=points.get(day, {})))
        day += timedelta(days=1)
    return UsageSeriesOut(
        since=since, until=until, source=source, meters=sorted(meters), points=out
    )


# ── CSV export (streaming) ─────────────────────────────────────────────


@router.get("/export.csv", response_class=StreamingResponse)
async def usage_export_csv(
    principal: ConsolePrincipal = Depends(require_console_principal("usage:read")),
    session: AsyncSession = Depends(get_db_session),
    days: int = Query(default=30, ge=1, le=366),
    client: str | None = Query(default=None, max_length=255),
    source: str | None = Query(default=None, pattern="^(channel|qa)$"),
    lang: str = Query(default="en", pattern="^(es|en)$"),
) -> StreamingResponse:
    since, until = _window(days)
    mappings = await partner_mappings(session, principal.partner.id)
    _chosen, by_tenant = _scope(mappings, client)
    tenant_ids = list(by_tenant)
    day_col = sa.cast(sa.func.timezone("UTC", UsageRecord.occurred_at), sa.Date)
    stmt = (
        sa.select(
            UsageRecord.tenant_id,
            day_col,
            UsageRecord.meter,
            UsageRecord.source,
            sa.func.coalesce(sa.func.sum(UsageRecord.quantity), 0),
            sa.func.coalesce(sa.func.sum(UsageRecord.billable_qty), 0),
            sa.func.count(),
        )
        .where(
            UsageRecord.tenant_id.in_(tenant_ids),
            UsageRecord.occurred_at >= since,
            UsageRecord.occurred_at < until,
        )
        .group_by(UsageRecord.tenant_id, day_col, UsageRecord.meter, UsageRecord.source)
        .order_by(day_col, UsageRecord.meter, UsageRecord.source)
    )
    if source is not None:
        stmt = stmt.where(UsageRecord.source == source)

    async def _rows() -> AsyncIterator[bytes]:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(_CSV_HEADERS[lang])
        yield buf.getvalue().encode("utf-8-sig")
        buf.seek(0)
        buf.truncate()
        if not tenant_ids:
            return
        async with reporting_transaction(session):
            result = await session.stream(stmt.execution_options(yield_per=500))
            async for tid, day, meter, src, qty, billable, count in result:
                m = by_tenant[tid]
                writer.writerow(
                    [
                        csv_safe(v)
                        for v in [
                            m.external_client_ref,
                            m.client_name or "",
                            day.isoformat(),
                            meter,
                            src,
                            f"{float(qty):g}",
                            f"{float(billable):g}",
                            int(count),
                        ]
                    ]
                )
                yield buf.getvalue().encode("utf-8")
                buf.seek(0)
                buf.truncate()

    filename = f"usage-{days}d-{lang}.csv"
    return StreamingResponse(
        _rows(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── alerts (CP-24) ─────────────────────────────────────────────────────


async def _alerts_out(session: AsyncSession, partner: Partner) -> UsageAlertsOut:
    since, until, _e, _d = month_bounds()
    mappings = await partner_mappings(session, partner.id)
    units = await channel_units_month(session, tenant_ids_of(mappings), since, until)
    return UsageAlertsOut(
        cap_messages_month=partner.usage_cap_messages_month,
        recipients=list(partner.usage_alert_recipients or []),
        enabled=partner.usage_alerts_enabled,
        month_units=units,
        percent=percent_of(units, partner.usage_cap_messages_month),
    )


@router.get("/alerts", response_model=UsageAlertsOut)
async def get_usage_alerts(
    principal: ConsolePrincipal = Depends(require_console_principal("usage:read")),
    session: AsyncSession = Depends(get_db_session),
) -> UsageAlertsOut:
    return await _alerts_out(session, principal.partner)


@router.put("/alerts", response_model=UsageAlertsOut)
async def put_usage_alerts(
    body: UsageAlertsIn,
    principal: ConsolePrincipal = Depends(require_console_principal("usage:manage")),
    session: AsyncSession = Depends(get_db_session),
) -> UsageAlertsOut:
    before: dict[str, Any] = {
        "cap": principal.partner.usage_cap_messages_month,
        "recipients": len(principal.partner.usage_alert_recipients or []),
        "enabled": principal.partner.usage_alerts_enabled,
    }
    recipients = sorted({str(r).lower() for r in body.recipients})
    async with session.begin():
        partner = await session.get(Partner, principal.partner.id)
        assert partner is not None  # the principal was resolved from this row
        partner.usage_cap_messages_month = body.cap_messages_month
        partner.usage_alert_recipients = recipients
        partner.usage_alerts_enabled = body.enabled
        session.add(
            AuditLog(
                tenant_id=None,
                actor=principal.actor,
                action="console.usage.alerts_update",
                target=f"partner:{principal.partner.id}",
                before_json=before,
                after_json={
                    "cap": body.cap_messages_month,
                    "recipients": len(recipients),
                    "enabled": body.enabled,
                },
            )
        )
    # ``partner`` is the same identity as ``principal.partner`` when the
    # principal was loaded through this session; when it is not (cached
    # principal), copy the fields without touching an attached ORM object
    # after the transaction (that would autobegin a new one).
    session.expunge_all()
    principal.partner.usage_cap_messages_month = body.cap_messages_month
    principal.partner.usage_alert_recipients = recipients
    principal.partner.usage_alerts_enabled = body.enabled
    return await _alerts_out(session, principal.partner)
