"""Checkpoint retention cron (WP-13, scheduler family) — closes half of V3.

LangGraph checkpoints every super-step and never deletes anything: storage
grows O(turns²) and reached a 100:1 ratio against ``messages``. Two prunes,
both in bounded batches with a pause so writers are never blocked:

1. **Trim per thread**: keep the newest ``NEXUS_CHECKPOINT_KEEP``
   checkpoints per (thread_id, checkpoint_ns); delete the rest plus their
   ``checkpoint_writes``. ``checkpoint_id`` is a UUIDv6-style sortable id —
   LangGraph itself orders by it.
2. **Purge dead threads**: threads whose NEWEST checkpoint is older than
   ``NEXUS_CHECKPOINT_MAX_AGE_DAYS`` (from the checkpoint's own ``ts``
   field) are deleted entirely — writes → blobs → checkpoints, the safe
   order. This is the only step that touches ``checkpoint_blobs``: blob
   versions are only provably orphaned when the whole thread is gone.

Runs in the scheduler family (leader-elected — exactly one instance).
"""

from __future__ import annotations

import asyncio
import contextlib

import sqlalchemy as sa
import structlog
from nexus_api.db.base import get_sessionmaker

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 24 * 3600.0
BATCH_ROWS = 5_000
BATCH_PAUSE_S = 0.5

_TRIM_SQL = sa.text(
    """
    WITH ranked AS (
        SELECT thread_id, checkpoint_ns, checkpoint_id,
               row_number() OVER (
                   PARTITION BY thread_id, checkpoint_ns
                   ORDER BY checkpoint_id DESC
               ) AS rn
        FROM checkpoints
    ),
    doomed AS (
        SELECT thread_id, checkpoint_ns, checkpoint_id
        FROM ranked WHERE rn > :keep LIMIT :batch
    ),
    del_writes AS (
        DELETE FROM checkpoint_writes w
        USING doomed d
        WHERE w.thread_id = d.thread_id
          AND w.checkpoint_ns = d.checkpoint_ns
          AND w.checkpoint_id = d.checkpoint_id
    )
    DELETE FROM checkpoints c
    USING doomed d
    WHERE c.thread_id = d.thread_id
      AND c.checkpoint_ns = d.checkpoint_ns
      AND c.checkpoint_id = d.checkpoint_id
    """
)

_DEAD_THREADS_SQL = sa.text(
    """
    SELECT thread_id
    FROM checkpoints
    GROUP BY thread_id
    HAVING max((checkpoint->>'ts')::timestamptz)
           < now() - make_interval(days => :max_age_days)
    LIMIT :batch
    """
)


_MAINTENANCE_GUC = sa.text("SELECT set_config('app.rls_maintenance', 'on', false)")


async def prune_once(
    *,
    keep: int,
    max_age_days: int,
    batch_rows: int = BATCH_ROWS,
    pause_s: float = BATCH_PAUSE_S,
) -> dict[str, int]:
    """One full retention pass. Returns counters for logs/tests.

    WP-14b: las tablas de checkpoint tienen RLS FORCE con policy por
    tenant; este barrido es global A PROPÓSITO y entra por la policy de
    mantenimiento (``app.rls_maintenance='on'``, migración 0066). Ese GUC
    es exclusivo de los caminos de mantenimiento del scheduler — el
    runtime jamás lo setea.
    """
    sm = get_sessionmaker()
    trimmed = 0
    dead_threads = 0

    # 1 · per-thread trim, batched until dry.
    while True:
        async with sm() as session:
            await session.execute(_MAINTENANCE_GUC)
            result = await session.execute(_TRIM_SQL, {"keep": keep, "batch": batch_rows})
            await session.commit()
            deleted = result.rowcount or 0
        trimmed += deleted
        if deleted < batch_rows:
            break
        await asyncio.sleep(pause_s)

    # 2 · dead threads, batched until dry. Safe order: writes → blobs →
    # checkpoints (a crash mid-batch leaves a consistent, re-prunable state).
    while True:
        async with sm() as session:
            await session.execute(_MAINTENANCE_GUC)
            rows = await session.execute(
                _DEAD_THREADS_SQL, {"max_age_days": max_age_days, "batch": 200}
            )
            threads = [r[0] for r in rows]
            if not threads:
                break
            await session.execute(
                sa.text("DELETE FROM checkpoint_writes WHERE thread_id = ANY(:t)"),
                {"t": threads},
            )
            await session.execute(
                sa.text("DELETE FROM checkpoint_blobs WHERE thread_id = ANY(:t)"),
                {"t": threads},
            )
            await session.execute(
                sa.text("DELETE FROM checkpoints WHERE thread_id = ANY(:t)"),
                {"t": threads},
            )
            await session.commit()
        dead_threads += len(threads)
        await asyncio.sleep(pause_s)

    return {"trimmed_checkpoints": trimmed, "purged_threads": dead_threads}


async def run_checkpoint_retention_cron(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    from nexus_worker.config import get_worker_settings

    ws = get_worker_settings()
    log.info(
        "checkpoint_retention.start",
        keep=ws.checkpoint_keep,
        max_age_days=ws.checkpoint_max_age_days,
    )
    while not stop.is_set():
        try:
            stats = await prune_once(
                keep=ws.checkpoint_keep, max_age_days=ws.checkpoint_max_age_days
            )
            log.info("checkpoint_retention.ok", **stats)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("checkpoint_retention.failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("checkpoint_retention.stopped")
