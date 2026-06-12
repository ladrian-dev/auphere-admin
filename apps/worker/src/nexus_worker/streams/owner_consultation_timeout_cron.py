"""Periodic sweep over ``owner_consultations`` for SLA enforcement.

Phase 1 scope: scan ``sent`` rows whose age exceeds the tenant's SLA
window for the row's urgency. For each match:

- If the row has not been reminded yet → re-enqueue the dispatcher by
  setting ``status='pending'`` again. The outbox dispatcher resends the
  template (idempotent because the template + correlation_id
  haven't changed). The ``reminded_count`` is bumped to record the nudge.
- If the row has already been reminded once and is still ``sent`` past
  a second SLA window → mark ``status='timed_out'``. Phase 1 logs and
  parks the row; Phase 2 escalates to Lee via OperatorNotification.

Tenant-by-tenant: the outer loop discovers tenants that have at least
one open consultation; each tenant gets its own scoped session.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import OwnerConsultation, Tenant

log = structlog.get_logger(__name__)


DEFAULT_TICK_SECONDS = 60.0


def _sla_minutes_for(tenant: Tenant, urgency: str) -> int:
    # SQLAlchemy Mapped[int] reads as Any under mypy --strict;
    # widen via int(...) so the function honours its return type.
    if urgency == "high":
        return int(tenant.backchannel_sla_high_min)
    if urgency == "low":
        return int(tenant.backchannel_sla_low_min)
    return int(tenant.backchannel_sla_normal_min)


async def run_owner_consultation_timeout_sweep(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    """Background task. Returns when ``stop`` is set."""
    log.info("owner_consultation_sweep.start", tick_seconds=tick_seconds)
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            await _tick(sm)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("owner_consultation_sweep.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("owner_consultation_sweep.stopped")


async def _tick(sm: sa.orm.sessionmaker) -> None:  # type: ignore[type-arg]
    tenant_ids = await _list_tenants_with_open(sm)
    for tid in tenant_ids:
        await _sweep_tenant(sm, tid)


async def _list_tenants_with_open(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
) -> list[uuid.UUID]:
    async with sm() as session:
        rows = await session.execute(
            sa.select(OwnerConsultation.tenant_id)
            .where(OwnerConsultation.status.in_(("pending", "sent")))
            .distinct()
        )
        return [row[0] for row in rows]


async def _sweep_tenant(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
    tenant_id: uuid.UUID,
) -> None:
    now = datetime.now(UTC)
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:  # pragma: no cover
            return
        rows = await session.execute(
            sa.select(OwnerConsultation)
            .where(OwnerConsultation.status == "sent")
            .with_for_update(skip_locked=True)
        )
        for row in rows.scalars():
            if row.sent_at is None:
                continue
            sla_minutes = _sla_minutes_for(tenant, row.urgency)
            elapsed = now - row.sent_at
            if elapsed < timedelta(minutes=sla_minutes):
                continue
            if row.reminded_count == 0:
                # First nudge — flip to pending so the outbox dispatcher
                # resends the template. Phase 1 does not have a separate
                # reminder template; the same body is re-sent and the
                # owner sees a duplicate prompt.
                row.status = "pending"
                row.reminded_at = now
                row.reminded_count += 1
                log.info(
                    "owner_consultation_sweep.reminded",
                    tenant_id=str(tenant_id),
                    consultation_id=str(row.id),
                    urgency=row.urgency,
                    sla_minutes=sla_minutes,
                )
                continue
            # Already reminded once and still no answer — park as
            # timed_out. Phase 2 escalates to Lee via OperatorNotification.
            row.status = "timed_out"
            row.timed_out_at = now
            log.info(
                "owner_consultation_sweep.timed_out",
                tenant_id=str(tenant_id),
                consultation_id=str(row.id),
                urgency=row.urgency,
                sla_minutes=sla_minutes,
            )
