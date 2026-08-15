"""``/console/usage`` — consumption in **units**, per client, meter and
source (CP-22 backend, decision C9).

What the partner sees: quantities from ``usage_records`` (tokens, messages,
minutes, media…) split by ``source`` (``channel`` = the client's traffic,
``qa`` = the partner's own tests in the playground). What the partner
does NOT see: ``cost_usd`` — that is Auphere's cost and showing it is
showing the margin. The partner's *price* is a Fase-2 concern (Stripe
meters); until then the console shows units.

``usage_records`` is RLS-forced per tenant, so the report is assembled
tenant by tenant in short scoped transactions — the same pattern the
backoffice's partner usage uses. N is the partner's client count.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.tenant_context import _current_tenant, apply_tenant_to_session
from nexus_api.db.models import PartnerTenant, UsageRecord
from nexus_api.repositories.partner import PartnerTenantRepository

from .schemas import UsageBucketOut, UsageReportOut

router = APIRouter(prefix="/usage")


@router.get("", response_model=UsageReportOut)
async def usage_report(
    principal: ConsolePrincipal = Depends(require_console_principal("usage:read")),
    session: AsyncSession = Depends(get_db_session),
    days: int = Query(default=30, ge=1, le=366),
    client: str | None = Query(
        default=None, max_length=255, description="Restrict to one external_client_ref"
    ),
    source: str | None = Query(default=None, pattern="^(channel|qa)$"),
) -> UsageReportOut:
    until = datetime.now(UTC)
    since = until - timedelta(days=days)

    async with session.begin():
        mappings: list[PartnerTenant] = await PartnerTenantRepository(session).list_for_partner(
            principal.partner.id
        )
    if client is not None:
        mappings = [m for m in mappings if m.external_client_ref == client]

    buckets: list[UsageBucketOut] = []
    totals: dict[str, float] = {}
    total_records = 0
    for mapping in mappings:
        token = _current_tenant.set(mapping.tenant_id)
        try:
            async with session.begin():
                await apply_tenant_to_session(session, mapping.tenant_id)
                stmt = (
                    sa.select(
                        UsageRecord.meter,
                        UsageRecord.source,
                        sa.func.coalesce(sa.func.sum(UsageRecord.quantity), 0),
                        sa.func.coalesce(sa.func.sum(UsageRecord.billable_qty), 0),
                        sa.func.count(),
                    )
                    .where(UsageRecord.occurred_at >= since, UsageRecord.occurred_at < until)
                    .group_by(UsageRecord.meter, UsageRecord.source)
                    .order_by(UsageRecord.meter, UsageRecord.source)
                )
                if source is not None:
                    stmt = stmt.where(UsageRecord.source == source)
                rows = (await session.execute(stmt)).all()
        finally:
            _current_tenant.reset(token)
        for meter, src, qty, billable, count in rows:
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

    return UsageReportOut(
        since=since,
        until=until,
        buckets=buckets,
        totals_by_meter=totals,
        total_records=total_records,
    )
