"""Retention cron for ``agent_memory_versions``.

The Memory tool's audit trigger (migration 0032) writes a row to
``agent_memory_versions`` on every INSERT / UPDATE / DELETE of
``agent_memories``. Without retention that table grows unboundedly —
chatty agents can produce thousands of rows per customer over weeks.

This cron keeps the *last 30 days* of versions and drops the rest.
Run once a day; the delete is a simple range scan on the
``versioned_at`` btree index.

The cron does NOT use ``tenant_scoped_session`` — it runs as the
DB owner (the alembic role) so RLS does not hide rows from it. RLS
is for app-time tenant scoping, not for audit-retention sweeps. The
delete is a single ranged statement so it cannot accidentally clear
rows the operator wants to keep (no per-row choices).

Configurable knobs:

- ``NEXUS_MEMORY_RETENTION_DAYS`` (default 30) — keep window.
- ``NEXUS_MEMORY_RETENTION_TICK_SECONDS`` (default 86400 = 1 day) —
  how often the cron wakes up. 1 day is fine: missing one tick by a
  few hours has no operational impact.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

import structlog
from nexus_api.db.base import get_sessionmaker
from sqlalchemy import text

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 86_400.0
DEFAULT_RETENTION_DAYS = 30


def _retention_days() -> int:
    raw = os.getenv("NEXUS_MEMORY_RETENTION_DAYS", str(DEFAULT_RETENTION_DAYS))
    try:
        days = int(raw)
    except ValueError:
        return DEFAULT_RETENTION_DAYS
    # Never less than 1 day — a "0 days" knob would wipe the audit trail
    # immediately and we want a sanity floor.
    return max(1, days)


async def _drain_once() -> int:
    """Delete rows older than the retention window.

    Returns the number of rows deleted (best effort — Postgres rowcount).
    Uses a raw ``DELETE ... WHERE versioned_at < now() - INTERVAL`` so
    the planner uses the ``idx_agent_memory_versions_versioned_at``
    btree directly without materialising a CTE.
    """
    days = _retention_days()
    sm = get_sessionmaker()
    async with sm() as session:
        # No tenant scoping: this is a global sweep run by the
        # superuser-equivalent app role. We do NOT SET LOCAL ROLE
        # nexus_app — that would activate RLS and silently delete zero
        # rows.
        result = await session.execute(
            text(
                "DELETE FROM agent_memory_versions "
                "WHERE versioned_at < now() - make_interval(days => :days)"
            ),
            {"days": days},
        )
        await session.commit()
        return result.rowcount or 0


async def run_memory_versions_retention_cron(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    """Background task. One pass per ``tick_seconds``.

    ``stop`` is signalled by the worker's signal handler; the loop wakes
    once per tick OR when ``stop`` is set, whichever is first.
    """
    log.info(
        "memory_versions_retention.start",
        tick_seconds=tick_seconds,
        retention_days=_retention_days(),
    )
    while not stop.is_set():
        try:
            deleted = await _drain_once()
            log.info(
                "memory_versions_retention.swept",
                deleted=deleted,
                retention_days=_retention_days(),
                at=datetime.now(UTC).isoformat(),
            )
        except Exception as exc:
            # The cron must never crash the worker — log and try again
            # on the next tick. A persistent DB error here would be
            # surfaced by other monitoring well before the table grows
            # to operationally relevant size.
            log.exception("memory_versions_retention.error", error=str(exc))

        try:
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
        except TimeoutError:
            continue
