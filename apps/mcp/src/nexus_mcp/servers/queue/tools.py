"""queue.* — Redis-backed live walk-in queue + Postgres history.

Hot state is a Redis list ``nexus:queue:tenant:{tenant_id}`` whose elements
are the customer_ids in arrival order. ``join_queue`` RPUSHes; ``check_in``
sets a Redis hash field (the customer is still in line until the operator
removes them); ``remove_from_queue`` LREMs.

Every mutating event also writes a row into ``queue_entries`` so the wait
history survives a Redis flush and feeds ``commission.get_daily_report``.

The estimated-wait calculation combines:

- ``queue_length`` — current Redis length (live).
- ``average_service_minutes`` — avg of the last 30 ``queue_entries`` whose
  status is ``served`` (Postgres). If there's no history yet we fall back
  to a sensible default (12 minutes).

The barber argument is informational in Block D — Block E will refine
estimates when AgendaPro supplies real per-barber average pace.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from nexus_api.core.redis_client import get_redis
from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import Customer, QueueEntry, QueueEntryStatus
from redis.asyncio import Redis
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_mcp._db import tool_session
from nexus_mcp.base import InputModel, OutputModel, ToolBase, ToolError
from nexus_mcp.servers.queue.schemas import (
    CheckInInput,
    CheckInOutput,
    GetEstimatedWaitInput,
    GetEstimatedWaitOutput,
    GetPositionInput,
    GetPositionOutput,
    JoinQueueInput,
    JoinQueueOutput,
    RemoveFromQueueInput,
    RemoveFromQueueOutput,
)

DEFAULT_AVG_MINUTES = 12
HISTORY_WINDOW = 30


def _list_key(tenant_id: uuid.UUID) -> str:
    return f"nexus:queue:tenant:{tenant_id}:list"


def _meta_key(tenant_id: uuid.UUID, customer_id: uuid.UUID) -> str:
    return f"nexus:queue:tenant:{tenant_id}:meta:{customer_id}"


async def _redis() -> Redis:
    return get_redis()  # type: ignore[no-any-return]


async def _list_position(redis: Redis, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> int | None:
    members = await redis.lrange(_list_key(tenant_id), 0, -1)  # type: ignore[misc]
    target = str(customer_id)
    for idx, m in enumerate(members):
        decoded = m if isinstance(m, str) else m.decode()
        if decoded == target:
            return idx + 1  # 1-based
    return None


async def _avg_minutes_from_history(session: AsyncSession) -> int:
    stmt = (
        select(QueueEntry)
        .where(QueueEntry.status == QueueEntryStatus.SERVED)
        .where(QueueEntry.served_at.is_not(None))
        .order_by(desc(QueueEntry.served_at))
        .limit(HISTORY_WINDOW)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        return DEFAULT_AVG_MINUTES
    total_minutes = 0
    counted = 0
    for entry in rows:
        if entry.served_at is None or entry.joined_at is None:
            continue
        delta = (entry.served_at - entry.joined_at).total_seconds() / 60.0
        if delta > 0:
            total_minutes += int(delta)
            counted += 1
    if counted == 0:
        return DEFAULT_AVG_MINUTES
    return max(1, total_minutes // counted)


# ── join_queue ───────────────────────────────────────────────────────────────


class JoinQueue(ToolBase):
    name = "queue.join_queue"
    description = (
        "Add a customer to the walk-in queue. Returns their 1-based position and "
        "an estimated wait time. Idempotent for the same customer: if already in "
        "queue, returns the existing position rather than enqueuing twice."
    )
    input_model = JoinQueueInput
    output_model = JoinQueueOutput
    side_effects = ("mutates_db",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, JoinQueueInput)
        tenant_id = require_current_tenant()
        redis = await _redis()
        list_key = _list_key(tenant_id)

        async with tool_session() as session:
            customer = await session.get(Customer, payload.customer_id)
            if customer is None:
                raise ToolError(f"customer {payload.customer_id} not found for this tenant")

            # Already enqueued? Return the existing entry (idempotent).
            existing_pos = await _list_position(redis, tenant_id, payload.customer_id)
            if existing_pos is not None:
                # Recover the queue_entry_id from the meta hash.
                meta_raw = await redis.get(_meta_key(tenant_id, payload.customer_id))
                meta = json.loads(meta_raw) if meta_raw else {}
                avg = await _avg_minutes_from_history(session)
                return JoinQueueOutput(
                    queue_entry_id=uuid.UUID(meta["queue_entry_id"]),
                    position=existing_pos,
                    estimated_wait_minutes=existing_pos * avg,
                )

            entry = QueueEntry(
                tenant_id=tenant_id,
                customer_id=payload.customer_id,
                service_name=payload.service_name,
                barber_id=payload.barber_id,
                status=QueueEntryStatus.WAITING,
                joined_at=datetime.now(UTC),
            )
            session.add(entry)
            await session.flush()
            await session.refresh(entry)
            entry_id = entry.id

            avg_minutes = await _avg_minutes_from_history(session)

        await redis.rpush(list_key, str(payload.customer_id))  # type: ignore[misc]
        await redis.set(
            _meta_key(tenant_id, payload.customer_id),
            json.dumps(
                {
                    "queue_entry_id": str(entry_id),
                    "service_name": payload.service_name,
                    "barber_id": str(payload.barber_id) if payload.barber_id else None,
                }
            ),
            ex=24 * 3600,
        )
        position = await _list_position(redis, tenant_id, payload.customer_id) or 1
        return JoinQueueOutput(
            queue_entry_id=entry_id,
            position=position,
            estimated_wait_minutes=position * avg_minutes,
        )


# ── get_position ─────────────────────────────────────────────────────────────


class GetPosition(ToolBase):
    name = "queue.get_position"
    description = (
        "Return the customer's current 1-based position in the queue, or null if "
        "they are not enqueued. Read-only — does not modify state."
    )
    input_model = GetPositionInput
    output_model = GetPositionOutput

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, GetPositionInput)
        tenant_id = require_current_tenant()
        redis = await _redis()
        position = await _list_position(redis, tenant_id, payload.customer_id)
        if position is None:
            return GetPositionOutput(
                customer_id=payload.customer_id,
                position=None,
                estimated_wait_minutes=None,
            )
        async with tool_session() as session:
            avg = await _avg_minutes_from_history(session)
        return GetPositionOutput(
            customer_id=payload.customer_id,
            position=position,
            estimated_wait_minutes=position * avg,
        )


# ── get_estimated_wait ───────────────────────────────────────────────────────


class GetEstimatedWait(ToolBase):
    name = "queue.get_estimated_wait"
    description = (
        "Estimate the wait time for a NEW customer joining now (i.e. queue length "
        "x average service time). Use to answer 'how long is the wait?' before "
        "the customer commits to joining."
    )
    input_model = GetEstimatedWaitInput
    output_model = GetEstimatedWaitOutput

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, GetEstimatedWaitInput)
        tenant_id = require_current_tenant()
        redis = await _redis()
        length = await redis.llen(_list_key(tenant_id))  # type: ignore[misc]
        async with tool_session() as session:
            avg = await _avg_minutes_from_history(session)
        return GetEstimatedWaitOutput(
            queue_length=length,
            average_service_minutes=avg,
            estimated_wait_minutes=length * avg,
        )


# ── check_in ─────────────────────────────────────────────────────────────────


class CheckIn(ToolBase):
    name = "queue.check_in"
    description = (
        "Mark a queued customer as 'arrived at the shop'. Updates the queue entry "
        "status to ``checked_in``; the customer remains in queue order until "
        "served. Block F will fire a notification to the barber here."
    )
    input_model = CheckInInput
    output_model = CheckInOutput
    side_effects = ("mutates_db", "sends_message")

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, CheckInInput)
        tenant_id = require_current_tenant()
        redis = await _redis()
        meta_raw = await redis.get(_meta_key(tenant_id, payload.customer_id))
        if not meta_raw:
            raise ToolError(f"customer {payload.customer_id} is not in the queue")
        meta = json.loads(meta_raw)
        entry_id = uuid.UUID(meta["queue_entry_id"])

        async with tool_session() as session:
            entry = await session.get(QueueEntry, entry_id)
            if entry is None:
                raise ToolError(
                    f"queue entry {entry_id} not found for this tenant — Redis/Postgres drift"
                )
            entry.status = QueueEntryStatus.CHECKED_IN
            entry.checked_in_at = datetime.now(UTC)
            await session.flush()

        return CheckInOutput(
            customer_id=payload.customer_id,
            queue_entry_id=entry_id,
            status="checked_in",
        )


# ── remove_from_queue ────────────────────────────────────────────────────────


class RemoveFromQueue(ToolBase):
    name = "queue.remove_from_queue"
    description = (
        "Remove a customer from the queue. Records a ``left`` event in the "
        "history. Use when a walk-in cancels, gets served (operator-initiated), "
        "or no-shows."
    )
    input_model = RemoveFromQueueInput
    output_model = RemoveFromQueueOutput
    side_effects = ("mutates_db",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, RemoveFromQueueInput)
        tenant_id = require_current_tenant()
        redis = await _redis()
        meta_raw = await redis.get(_meta_key(tenant_id, payload.customer_id))
        entry_id: uuid.UUID | None = None
        if meta_raw:
            meta = json.loads(meta_raw)
            entry_id = uuid.UUID(meta["queue_entry_id"])

        # Best-effort Redis cleanup; LREM of 0 if not present is fine.
        await redis.lrem(_list_key(tenant_id), 0, str(payload.customer_id))  # type: ignore[misc]
        await redis.delete(_meta_key(tenant_id, payload.customer_id))

        if entry_id is not None:
            async with tool_session() as session:
                entry = await session.get(QueueEntry, entry_id)
                if entry is not None and entry.status not in (
                    QueueEntryStatus.SERVED,
                    QueueEntryStatus.LEFT,
                ):
                    entry.status = QueueEntryStatus.LEFT
                    entry.left_at = datetime.now(UTC)
                    await session.flush()

        return RemoveFromQueueOutput(
            customer_id=payload.customer_id,
            queue_entry_id=entry_id,
            status="removed",
        )


QUEUE_TOOLS: tuple[type[ToolBase], ...] = (
    JoinQueue,
    GetPosition,
    GetEstimatedWait,
    CheckIn,
    RemoveFromQueue,
)
