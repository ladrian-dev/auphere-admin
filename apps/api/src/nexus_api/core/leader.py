"""Postgres advisory-lock leadership (WP-08, plataforma v2 Fase 1).

The scheduler family (17 crons and sweeps) must run exactly once across
replicas — before this module, a second worker replica duplicated
reminders, receipts and rollups (V5), which is what blocked all horizontal
scaling. ``run_exclusive`` wraps a task family in leader election:

- acquire ``pg_try_advisory_lock(hashtext(name))`` on a DEDICATED
  connection held for the whole leadership term (session-scoped lock);
- run the family while pinging the connection — if the ping fails, the
  lock is gone with the connection, so the tasks are stopped immediately
  and the loop re-enters the election;
- a replica that doesn't get the lock stays hot-standby, retrying, and
  takes over the moment the leader's connection dies (Postgres releases
  the lock automatically — crash-safe failover with no state anywhere).

One lock guards the whole family rather than one per cron: the scheduler
deploys as a singleton (2 replicas only during rollout), so per-cron
sharding would add 17 held connections for no operational win. If crons
ever need to shard across replicas, ``run_exclusive`` already takes the
lock name as a parameter.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable

import sqlalchemy as sa
import structlog

from nexus_api.db.base import get_engine

log = structlog.get_logger(__name__)

DEFAULT_RETRY_SECONDS = 5.0
DEFAULT_PING_SECONDS = 15.0


async def _wait_or_stop(stop: asyncio.Event, seconds: float) -> None:
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)


async def _cancel_all(tasks: list[asyncio.Task[None]]) -> None:
    for task in tasks:
        task.cancel()
    with contextlib.suppress(Exception):
        await asyncio.gather(*tasks, return_exceptions=True)


async def run_exclusive(
    name: str,
    *,
    stop: asyncio.Event,
    start_tasks: Callable[[], list[asyncio.Task[None]]],
    retry_seconds: float = DEFAULT_RETRY_SECONDS,
    ping_seconds: float = DEFAULT_PING_SECONDS,
) -> None:
    """Run ``start_tasks`` only while holding the advisory lock ``name``."""
    while not stop.is_set():
        try:
            async with get_engine().connect() as conn:
                # AUTOCOMMIT: this connection lives for the whole leadership
                # term — without it, the first SELECT would open a
                # transaction that idles for hours and pins the vacuum
                # horizon. Session-scoped advisory locks are independent of
                # transactions, so nothing else changes.
                await conn.execution_options(isolation_level="AUTOCOMMIT")
                acquired = (
                    await conn.execute(
                        sa.text("SELECT pg_try_advisory_lock(hashtext(:name))"),
                        {"name": name},
                    )
                ).scalar()
                if not acquired:
                    log.debug("leader.standby", name=name)
                    await _wait_or_stop(stop, retry_seconds)
                    continue

                log.info("leader.acquired", name=name)
                tasks = start_tasks()
                try:
                    while not stop.is_set():
                        await _wait_or_stop(stop, ping_seconds)
                        if stop.is_set():
                            break
                        # The ping proves the lock-holding session is alive.
                        # If it raises, Postgres has (or will have) released
                        # the lock — stop the family NOW, before another
                        # replica starts a duplicate.
                        await conn.execute(sa.text("SELECT 1"))
                finally:
                    await _cancel_all(tasks)
                    with contextlib.suppress(Exception):
                        await conn.execute(
                            sa.text("SELECT pg_advisory_unlock(hashtext(:name))"),
                            {"name": name},
                        )
                    log.info("leader.released", name=name)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("leader.term_failed", name=name, error=str(exc))
            await _wait_or_stop(stop, retry_seconds)
    log.info("leader.stopped", name=name)
