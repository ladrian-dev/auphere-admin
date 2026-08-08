"""Phase 2 backchannel — sweep ``owner_consultations`` for fanout entries
that never got applied.

The happy path is:

1. Owner replies on WhatsApp → ``owner_channel`` webhook updates
   ``owner_consultations`` to ``status='answered'`` and XADDs a job onto
   ``nexus:owner_fanout``.
2. ``run_owner_fanout_consumer`` pulls the job, re-enters the pipeline,
   stamps ``result_applied_at = now()`` on the row.

If step 2 never lands (Redis restart with stale AOF, worker crash mid-ack,
consumer-group rebalance edge cases) the row is already
``status='answered'`` so the data isn't lost — but the downstream fanout
never runs and the customer never sees the agent's follow-up.

This sweep periodically re-enqueues those orphans:

- Scan ``owner_consultations`` WHERE ``status='answered'`` AND
  ``result_applied_at IS NULL`` AND ``owner_response_at`` falls inside a
  bounded window (``MIN_AGE`` to skip just-published entries the consumer
  is about to pick up; ``MAX_AGE`` to skip ancient entries that would
  flood the pipeline if we revived them).
- For each match, XADD to ``nexus:owner_fanout``. The consumer will pick
  up the new entry; on success it stamps ``result_applied_at`` and the
  sweep stops seeing the row.

The partial index ``ix_owner_consultations_sweep`` (migration 0042)
keeps the scan cheap as the log grows.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
import structlog
from nexus_api.core.streams import xadd_capped
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import OwnerConsultation, Tenant
from redis.asyncio import Redis

log = structlog.get_logger(__name__)


OWNER_FANOUT_STREAM = "nexus:owner_fanout"

# Tunables. The min age gives the live consumer a chance to drain
# before the sweep tries to re-enqueue. The max age prevents reviving
# very old answers that would surprise the customer.
DEFAULT_TICK_SECONDS = 300.0  # 5 min — sweep cadence
DEFAULT_MIN_AGE_SECONDS = 30
DEFAULT_MAX_AGE_HOURS = 24
DEFAULT_BATCH_SIZE = 100


async def run_owner_fanout_sweep(
    redis: Redis,
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
    min_age_seconds: int = DEFAULT_MIN_AGE_SECONDS,
    max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    """Background task. Returns when ``stop`` is set."""
    log.info(
        "owner_fanout_sweep.start",
        tick_seconds=tick_seconds,
        min_age_seconds=min_age_seconds,
        max_age_hours=max_age_hours,
    )
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            await _tick(
                sm,
                redis,
                min_age_seconds=min_age_seconds,
                max_age_hours=max_age_hours,
                batch_size=batch_size,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("owner_fanout_sweep.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("owner_fanout_sweep.stopped")


async def _tick(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
    redis: Redis,
    *,
    min_age_seconds: int,
    max_age_hours: int,
    batch_size: int,
) -> None:
    """One sweep pass — group orphans by tenant and re-enqueue each one."""
    tenant_ids = await _list_tenants_with_orphans(sm)
    if not tenant_ids:
        return
    total_reenqueued = 0
    for tid in tenant_ids:
        count = await _reenqueue_tenant(
            sm,
            redis,
            tenant_id=tid,
            min_age_seconds=min_age_seconds,
            max_age_hours=max_age_hours,
            batch_size=batch_size,
        )
        total_reenqueued += count
    if total_reenqueued:
        log.info(
            "owner_fanout_sweep.tick_done",
            reenqueued=total_reenqueued,
            tenants=len(tenant_ids),
        )


async def _list_tenants_with_orphans(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
) -> list[uuid.UUID]:
    """Discover tenants with at least one ``answered`` row whose fanout
    never landed. The partial index on
    ``(status, owner_response_at) WHERE result_applied_at IS NULL`` makes
    this lookup index-only."""
    async with sm() as session:
        rows = await session.execute(
            sa.select(OwnerConsultation.tenant_id)
            .where(OwnerConsultation.status == "answered")
            .where(OwnerConsultation.result_applied_at.is_(None))
            .distinct()
        )
        return [row[0] for row in rows]


async def _reenqueue_tenant(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
    redis: Redis,
    *,
    tenant_id: uuid.UUID,
    min_age_seconds: int,
    max_age_hours: int,
    batch_size: int,
) -> int:
    """Find orphan rows within the configured age window for this tenant
    and XADD a fanout job for each. Returns the number of jobs enqueued.

    The actual ``result_applied_at`` write happens in the consumer
    (apps/worker/.../owner_fanout.py) so an idempotent re-enqueue is safe:
    a duplicate that races a successful consume just becomes a no-op
    when the consumer sees the row already has ``result_applied_at`` set.
    """
    now = datetime.now(UTC)
    min_cutoff = now - timedelta(seconds=min_age_seconds)
    max_cutoff = now - timedelta(hours=max_age_hours)
    enqueued = 0
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            return 0
        rows = await session.execute(
            sa.select(OwnerConsultation.id)
            .where(OwnerConsultation.status == "answered")
            .where(OwnerConsultation.result_applied_at.is_(None))
            .where(OwnerConsultation.owner_response_at <= min_cutoff)
            .where(OwnerConsultation.owner_response_at >= max_cutoff)
            .order_by(OwnerConsultation.owner_response_at.asc())
            .limit(batch_size)
        )
        for row in rows.scalars():
            await xadd_capped(
                redis,
                OWNER_FANOUT_STREAM,
                {
                    "tenant_id": str(tenant_id),
                    "consultation_id": str(row),
                },
            )
            enqueued += 1
            log.info(
                "owner_fanout_sweep.reenqueued",
                tenant_id=str(tenant_id),
                consultation_id=str(row),
            )
    return enqueued
