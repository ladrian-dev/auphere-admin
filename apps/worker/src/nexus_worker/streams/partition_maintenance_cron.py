"""Partition maintenance cron (WP-13, scheduler family).

Ensures the current and next month's partitions exist for every partitioned
table, via the ``ensure_month_partition`` SQL function (migration 0064).
Idempotent, so it simply runs on every tick — a month can never roll over
into a missing partition, and the DEFAULT partition backstops even a cron
outage.

Since 0069 the same function also propagates the parent's RLS to the new
partition: a partition does NOT inherit row security, and one created
without it is a table full of every tenant's rows that any direct query
would read unfiltered.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

import sqlalchemy as sa
import structlog
from nexus_api.db.base import get_sessionmaker

log = structlog.get_logger(__name__)

PARTITIONED_TABLES = ("messages", "usage_records")
DEFAULT_TICK_SECONDS = 6 * 3600.0  # 4x/day — cheap and safely redundant


async def ensure_partitions_once() -> list[str]:
    """One pass: current + next month for every partitioned table.
    Returns the partition names touched (for tests/logs)."""
    sm = get_sessionmaker()
    now = datetime.now(UTC)
    if now.month == 12:
        next_month = now.replace(year=now.year + 1, month=1, day=1)
    else:
        next_month = now.replace(month=now.month + 1, day=1)
    ensured: list[str] = []
    async with sm() as session:
        for table in PARTITIONED_TABLES:
            for month in (now, next_month):
                name = (
                    await session.execute(
                        sa.text("SELECT ensure_month_partition(:t, :m)"),
                        {"t": table, "m": month.date()},
                    )
                ).scalar_one()
                ensured.append(str(name))
        await session.commit()
    return ensured


async def run_partition_maintenance_cron(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    log.info("partition_maintenance.start", tables=PARTITIONED_TABLES)
    while not stop.is_set():
        try:
            ensured = await ensure_partitions_once()
            log.info("partition_maintenance.ok", partitions=ensured)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("partition_maintenance.failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("partition_maintenance.stopped")
