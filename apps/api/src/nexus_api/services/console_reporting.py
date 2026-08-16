"""Cross-tenant READ helpers for the partner console (lane D).

The console shows one partner's figures across ALL its clients: usage of
the month, the audit trail, a series per day. Those tables are RLS-forced
per tenant (``usage_records`` 0068, ``audit_log`` 0002/0040) — forced
also for the table owner, so an unscoped session sees **nothing** in
Aurora (the master user is not a superuser). Locally the connecting user
IS a superuser and bypasses RLS, which is exactly how such a bug hides.

Two ways to read across tenants, and why this one:

- N scoped transactions, one per client (``apply_tenant_to_session``).
  Correct, RLS-defended, and O(N) round trips: 20 clients x 2 round
  trips per table per request. Fine at N=20, not at N=200 (CP-08 asks
  for < 1 s on the home page). It is still what the console uses for
  tables that have NO reporting policy (channels, conversations,
  messages — see ``console_home.py``).
- One query under ``nexus_reporting`` (0078) with ``tenant_id = ANY(:ids)``,
  the ids computed from ``partner_tenants`` under the principal BEFORE
  switching role. Read-only role, ``NOBYPASSRLS``, column-level grants
  (no message bodies, no prompts, no phones), permissive ``FOR SELECT``
  policies on the tables it may read. Migrations 0083/0084 extend it
  with exactly what the console needs (``usage_records.source``,
  ``audit_log``). The scope boundary is the application filter built
  from the principal — the same trust the invoice reader already has.

Never use this for writes and never without an explicit tenant filter.
"""

from __future__ import annotations

import calendar
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import PartnerTenant

REPORTING_ROLE = "nexus_reporting"


@asynccontextmanager
async def reporting_transaction(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """A transaction that reads above the tenant as ``nexus_reporting``.

    ``SET LOCAL ROLE`` lasts for the transaction only; the connection
    goes back to the pool as the connecting user. Platform tables
    (``partners``, ``partner_tenants``…) are NOT granted to the role — read
    them before entering, pass ids in.
    """
    async with session.begin():
        await session.execute(sa.text(f"SET LOCAL ROLE {REPORTING_ROLE}"))
        yield session


async def partner_mappings(session: AsyncSession, partner_id: uuid.UUID) -> list[PartnerTenant]:
    """The partner's clients (``partner_tenants``), own short transaction."""
    async with session.begin():
        rows = (
            (
                await session.execute(
                    sa.select(PartnerTenant)
                    .where(PartnerTenant.partner_id == partner_id)
                    .order_by(PartnerTenant.external_client_ref)
                )
            )
            .scalars()
            .all()
        )
    return list(rows)


def month_bounds(now: datetime | None = None) -> tuple[datetime, datetime, int, int]:
    """``(start, next_month_start, elapsed_days, days_in_month)`` of the
    natural UTC month containing ``now``. ``elapsed_days`` counts today as
    a (partial) day, so it is ≥ 1 — the projection never divides by zero."""
    now = now or datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days = calendar.monthrange(now.year, now.month)[1]
    if now.month == 12:
        end = start.replace(year=now.year + 1, month=1)
    else:
        end = start.replace(month=now.month + 1)
    return start, end, now.day, days


def project_month(units: float, elapsed_days: int, days_in_month: int) -> float:
    """Linear projection over the elapsed days of the natural month."""
    if elapsed_days <= 0:
        return units
    return round(units / elapsed_days * days_in_month, 3)


def percent_of(units: float, cap: int | None) -> float | None:
    if cap is None or cap <= 0:
        return None
    return round(units / cap * 100.0, 2)


def tenant_ids_of(mappings: Sequence[PartnerTenant]) -> list[uuid.UUID]:
    return [m.tenant_id for m in mappings]


__all__ = [
    "REPORTING_ROLE",
    "month_bounds",
    "partner_mappings",
    "percent_of",
    "project_month",
    "reporting_transaction",
    "tenant_ids_of",
]


def csv_safe(value: object) -> object:
    """Neutralise spreadsheet formula injection: a cell that starts with
    ``=``, ``+``, ``-``, ``@``, tab or CR is prefixed with a quote so Excel/
    Sheets treat it as text. Numbers pass through untouched."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value
