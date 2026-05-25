"""Integration tests for ``run_owner_fanout_sweep`` — the Phase 2 cron
that re-enqueues ``answered`` consultations whose fanout never landed.

The sweep is what closes the durability gap between the webhook XADD
and the consumer ack: if Redis loses the entry between those two
moments, the row stays at ``status='answered'`` with
``result_applied_at IS NULL`` and the customer never sees the agent's
follow-up. The sweep catches those by scanning the partial index added
in migration 0042 and re-publishing.

Tests cover:

- A row inside the age window (between min and max) gets re-enqueued.
- A row too fresh (younger than ``min_age_seconds``) is skipped — the
  live consumer is about to pick it up.
- A row too old (older than ``max_age_hours``) is skipped — reviving
  ancient answers would surprise the customer.
- A row with ``result_applied_at`` already set is skipped (idempotent).
- The XADD payload carries the expected ``tenant_id`` /
  ``consultation_id`` shape so the existing consumer can pick it up
  without changes.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    Customer,
    OwnerConsultation,
    Tenant,
    TenantPlan,
    TenantStatus,
)
from nexus_worker.streams.owner_fanout_sweep import (
    OWNER_FANOUT_STREAM,
    run_owner_fanout_sweep,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _seed_tenant_with_conversation(db_session: Any) -> dict[str, Any]:
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name=f"sweep-{tenant_id.hex[:6]}",
            slug=f"sweep-{tenant_id.hex[:6]}",
            plan=TenantPlan.INTERNAL,
            status=TenantStatus.ACTIVE,
        )
    )
    await db_session.commit()
    channel = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="ycloud",
        provider_identifier=f"biz-{tenant_id.hex[:6]}",
        status=ChannelStatus.ACTIVE,
    )
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)
    customer = Customer(
        tenant_id=tenant_id,
        identifier=f"+5699000{tenant_id.hex[:4]}",
        preferences={},
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    conv = Conversation(
        tenant_id=tenant_id,
        channel_id=channel.id,
        customer_id=customer.id,
        agent_active=True,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    return {"tenant_id": tenant_id, "conversation_id": conv.id}


async def _seed_answered_row(
    db_session: Any,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    owner_response_at: datetime,
    result_applied_at: datetime | None = None,
) -> uuid.UUID:
    """Create an ``answered`` row at an explicit ``owner_response_at`` so
    the sweep window logic can be exercised deterministically."""
    asked_at = owner_response_at - timedelta(minutes=10)
    sent_at = owner_response_at - timedelta(minutes=9)
    row = OwnerConsultation(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        correlation_id=f"REF{uuid.uuid4().hex[:8]}",
        asked_at=asked_at,
        question_text="¿confirmamos?",
        urgency="normal",
        expected_reply_kind="free_text",
        template_name="auphere_owner_consult",
        template_params_json={},
        status="answered",
        sent_at=sent_at,
        owner_response_at=owner_response_at,
        owner_response_text="sí dale",
        owner_command_kind="yes",
        result_applied_at=result_applied_at,
        created_by="agent:test",
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row.id


async def _run_one_tick(redis, *, min_age_seconds: int = 30) -> None:
    """Run the sweep with stop already set so it exits after one tick.
    The loop checks ``stop`` before the first body, so we need to let
    one full iteration execute by setting stop AFTER scheduling."""
    stop = asyncio.Event()

    async def _stop_after_tick():
        await asyncio.sleep(0.05)
        stop.set()

    await asyncio.gather(
        run_owner_fanout_sweep(
            redis,
            stop=stop,
            tick_seconds=10.0,
            min_age_seconds=min_age_seconds,
        ),
        _stop_after_tick(),
    )


async def _drain_stream(redis) -> list[dict[str, str]]:
    """Read everything currently in the fanout stream and return decoded
    field dicts. Uses XREAD from id=0 so we see every entry."""
    raw = await redis.xread({OWNER_FANOUT_STREAM: "0"}, count=1000)
    if not raw:
        return []
    out: list[dict[str, str]] = []
    for _stream_name, entries in raw:
        for _entry_id, fields in entries:
            decoded: dict[str, str] = {}
            for k, v in fields.items():
                ks = k.decode() if isinstance(k, bytes) else k
                vs = v.decode() if isinstance(v, bytes) else v
                decoded[ks] = vs
            out.append(decoded)
    return out


class TestOwnerFanoutSweep:
    async def test_in_window_row_is_reenqueued(self, db_session, fake_redis):
        ctx = await _seed_tenant_with_conversation(db_session)
        # 5 min ago — well past min_age (30s), under max_age (24h).
        consultation_id = await _seed_answered_row(
            db_session,
            tenant_id=ctx["tenant_id"],
            conversation_id=ctx["conversation_id"],
            owner_response_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        await _run_one_tick(fake_redis)
        entries = await _drain_stream(fake_redis)
        assert len(entries) == 1
        assert entries[0]["tenant_id"] == str(ctx["tenant_id"])
        assert entries[0]["consultation_id"] == str(consultation_id)

    async def test_too_fresh_row_is_skipped(self, db_session, fake_redis):
        """A row younger than min_age is still in the live consumer's
        path; re-enqueuing would race."""
        ctx = await _seed_tenant_with_conversation(db_session)
        await _seed_answered_row(
            db_session,
            tenant_id=ctx["tenant_id"],
            conversation_id=ctx["conversation_id"],
            owner_response_at=datetime.now(UTC) - timedelta(seconds=5),
        )
        await _run_one_tick(fake_redis, min_age_seconds=30)
        entries = await _drain_stream(fake_redis)
        assert entries == []

    async def test_too_old_row_is_skipped(self, db_session, fake_redis):
        """A row older than max_age would surface stale answers; skip."""
        ctx = await _seed_tenant_with_conversation(db_session)
        await _seed_answered_row(
            db_session,
            tenant_id=ctx["tenant_id"],
            conversation_id=ctx["conversation_id"],
            owner_response_at=datetime.now(UTC) - timedelta(hours=48),
        )
        await _run_one_tick(fake_redis)
        entries = await _drain_stream(fake_redis)
        assert entries == []

    async def test_already_applied_row_is_skipped(self, db_session, fake_redis):
        """Idempotent — once the consumer stamped result_applied_at the
        sweep must not re-publish the same row."""
        ctx = await _seed_tenant_with_conversation(db_session)
        await _seed_answered_row(
            db_session,
            tenant_id=ctx["tenant_id"],
            conversation_id=ctx["conversation_id"],
            owner_response_at=datetime.now(UTC) - timedelta(minutes=5),
            result_applied_at=datetime.now(UTC) - timedelta(minutes=4),
        )
        await _run_one_tick(fake_redis)
        entries = await _drain_stream(fake_redis)
        assert entries == []

    async def test_mixed_tenants_one_orphan_each(self, db_session, fake_redis):
        """Sweep is multi-tenant: each tenant gets its own scoped session
        pass and orphans from both surface."""
        ctx_a = await _seed_tenant_with_conversation(db_session)
        ctx_b = await _seed_tenant_with_conversation(db_session)
        await _seed_answered_row(
            db_session,
            tenant_id=ctx_a["tenant_id"],
            conversation_id=ctx_a["conversation_id"],
            owner_response_at=datetime.now(UTC) - timedelta(minutes=2),
        )
        await _seed_answered_row(
            db_session,
            tenant_id=ctx_b["tenant_id"],
            conversation_id=ctx_b["conversation_id"],
            owner_response_at=datetime.now(UTC) - timedelta(minutes=3),
        )
        await _run_one_tick(fake_redis)
        entries = await _drain_stream(fake_redis)
        assert len(entries) == 2
        tenants_in_stream = {e["tenant_id"] for e in entries}
        assert tenants_in_stream == {str(ctx_a["tenant_id"]), str(ctx_b["tenant_id"])}
