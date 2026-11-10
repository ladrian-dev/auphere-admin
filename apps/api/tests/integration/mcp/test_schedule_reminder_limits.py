"""Limits of ``notification.schedule_reminder`` (bug recordatorios-sin-tope).

Every reminder that fires is a WhatsApp template Meta bills to the business,
and the one asking the agent for it is the end customer. The tool only
schedules what the agent answering on that number allows in
``policies.scheduled_reminders``: its templates, so many per customer per day
and so many days ahead.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_mcp import MCPRegistry
from nexus_mcp.base import ToolError

from nexus_api.core.tenant_context import (
    customer_context,
    tenant_context,
    tenant_scoped_session,
)
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Agent,
    Channel,
    Conversation,
    ScheduledJob,
    ScheduledJobKind,
    ScheduledJobStatus,
)

from .conftest import (
    all_whitelist,
    seed_channel_and_conversation,
    seed_customer,
    seed_reminder_policy,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

TEMPLATE = "recordatorio_cita"


async def _schedule(
    registry: MCPRegistry,
    conv: Conversation,
    *,
    template: str = TEMPLATE,
    run_at: datetime | str | None = None,
) -> dict[str, Any]:
    when = run_at if run_at is not None else datetime.now(UTC) + timedelta(hours=23)
    return await registry.dispatch(
        "notification.schedule_reminder",
        {
            "conversation_id": str(conv.id),
            "run_at": when if isinstance(when, str) else when.isoformat(),
            "template_name": template,
            "parameters": {"name": "Ana"},
        },
        whitelist=all_whitelist(),
    )


async def _reminders(tenant_id: uuid.UUID) -> list[ScheduledJob]:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        rows = await session.execute(
            sa.select(ScheduledJob).where(ScheduledJob.kind == ScheduledJobKind.REMINDER)
        )
        return list(rows.scalars())


async def _set_reminders(tenant_id: uuid.UUID, **values: Any) -> None:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        await session.execute(
            sa.update(ScheduledJob)
            .where(ScheduledJob.kind == ScheduledJobKind.REMINDER)
            .values(**values)
        )


async def _customer_conversation(db_session, tenant_id: uuid.UUID, identifier: str = "c1"):
    cust = await seed_customer(db_session, tenant_id=tenant_id, identifier=identifier)
    _, conv = await seed_channel_and_conversation(
        db_session,
        tenant_id=tenant_id,
        customer_id=cust.id,
        provider_identifier=f"wa-{identifier}",
    )
    return cust, conv


# ── which templates ─────────────────────────────────────────────────────────


async def test_without_a_policy_nothing_is_scheduled(db_session, two_tenants, mcp_registry):
    """Fails closed: no business has said which template is a reminder."""
    a = two_tenants["a"]
    cust, conv = await _customer_conversation(db_session, a)

    with (
        tenant_context(a),
        customer_context(cust.id),
        pytest.raises(ToolError, match="no template enabled for reminders"),
    ):
        await _schedule(mcp_registry, conv)

    assert await _reminders(a) == []


async def test_an_empty_template_list_schedules_nothing(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    await seed_reminder_policy(db_session, tenant_id=a, templates=[])
    cust, conv = await _customer_conversation(db_session, a)

    with (
        tenant_context(a),
        customer_context(cust.id),
        pytest.raises(ToolError, match="no template enabled for reminders"),
    ):
        await _schedule(mcp_registry, conv)

    assert await _reminders(a) == []


async def test_a_template_outside_the_list_is_refused(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    await seed_reminder_policy(db_session, tenant_id=a, templates=[TEMPLATE])
    cust, conv = await _customer_conversation(db_session, a)

    with tenant_context(a), customer_context(cust.id):
        with pytest.raises(ToolError, match="promo_black_friday") as refused:
            await _schedule(mcp_registry, conv, template="promo_black_friday")
        # The refusal names what the agent may use instead.
        assert TEMPLATE in str(refused.value)

    assert await _reminders(a) == []


async def test_an_allowed_template_is_scheduled(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    await seed_reminder_policy(db_session, tenant_id=a, templates=[TEMPLATE, "control_6_meses"])
    cust, conv = await _customer_conversation(db_session, a)

    with tenant_context(a), customer_context(cust.id):
        envelope = await _schedule(mcp_registry, conv, template="control_6_meses")

    assert envelope["result"]["status"] == "scheduled"
    [job] = await _reminders(a)
    assert job.status == ScheduledJobStatus.PENDING
    assert job.payload["template_name"] == "control_6_meses"


async def test_the_policy_of_the_agent_on_that_number_rules(db_session, two_tenants, mcp_registry):
    """Spec 030: a client may have several agents; the one answering on the
    conversation's number decides, not the principal."""
    a = two_tenants["a"]
    await seed_reminder_policy(db_session, tenant_id=a, templates=["solo_del_principal"])
    second = Agent(tenant_id=a, name="Reservas")
    db_session.add(second)
    await db_session.commit()
    await db_session.refresh(second)
    await seed_reminder_policy(
        db_session, tenant_id=a, templates=[TEMPLATE], agent_id=second.id, version=2
    )
    cust, conv = await _customer_conversation(db_session, a)
    channel = await db_session.get(Channel, conv.channel_id)
    channel.agent_id = second.id
    await db_session.commit()

    with tenant_context(a), customer_context(cust.id):
        with pytest.raises(ToolError, match="solo_del_principal"):
            await _schedule(mcp_registry, conv, template="solo_del_principal")
        envelope = await _schedule(mcp_registry, conv)

    assert envelope["result"]["status"] == "scheduled"


# ── how far ahead ───────────────────────────────────────────────────────────


async def test_more_than_30_days_ahead_is_refused_by_default(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    await seed_reminder_policy(db_session, tenant_id=a, templates=[TEMPLATE])
    cust, conv = await _customer_conversation(db_session, a)
    now = datetime.now(UTC)

    with tenant_context(a), customer_context(cust.id):
        with pytest.raises(ToolError, match="at most 30 days ahead"):
            await _schedule(mcp_registry, conv, run_at=now + timedelta(days=31))
        ok = await _schedule(mcp_registry, conv, run_at=now + timedelta(days=29))

    assert ok["result"]["status"] == "scheduled"
    assert len(await _reminders(a)) == 1


async def test_the_business_can_reach_further(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    await seed_reminder_policy(db_session, tenant_id=a, templates=[TEMPLATE], max_days_ahead=180)
    cust, conv = await _customer_conversation(db_session, a)

    with tenant_context(a), customer_context(cust.id):
        envelope = await _schedule(
            mcp_registry, conv, run_at=datetime.now(UTC) + timedelta(days=170)
        )

    assert envelope["result"]["status"] == "scheduled"


async def test_no_policy_reaches_beyond_a_year(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    await seed_reminder_policy(db_session, tenant_id=a, templates=[TEMPLATE], max_days_ahead=5000)
    cust, conv = await _customer_conversation(db_session, a)

    with (
        tenant_context(a),
        customer_context(cust.id),
        pytest.raises(ToolError, match="at most 365 days ahead"),
    ):
        await _schedule(mcp_registry, conv, run_at=datetime.now(UTC) + timedelta(days=400))

    assert await _reminders(a) == []


async def test_a_run_at_without_offset_counts_as_utc(db_session, two_tenants, mcp_registry):
    """The LLM sometimes drops the offset; that must not crash the check."""
    a = two_tenants["a"]
    await seed_reminder_policy(db_session, tenant_id=a, templates=[TEMPLATE])
    cust, conv = await _customer_conversation(db_session, a)
    naive_far = (datetime.now(UTC) + timedelta(days=40)).replace(tzinfo=None).isoformat()
    naive_near = (datetime.now(UTC) + timedelta(days=2)).replace(tzinfo=None)

    with tenant_context(a), customer_context(cust.id):
        with pytest.raises(ToolError, match="at most 30 days ahead"):
            await _schedule(mcp_registry, conv, run_at=naive_far)
        await _schedule(mcp_registry, conv, run_at=naive_near.isoformat())

    [job] = await _reminders(a)
    assert job.run_at == naive_near.replace(tzinfo=UTC)


async def test_a_run_at_already_due_is_still_scheduled(db_session, two_tenants, mcp_registry):
    """Decision: a booking under 24 h away still gets its "24 h before"
    reminder, sent on the next tick. The daily cap bounds it."""
    a = two_tenants["a"]
    await seed_reminder_policy(db_session, tenant_id=a, templates=[TEMPLATE])
    cust, conv = await _customer_conversation(db_session, a)

    with tenant_context(a), customer_context(cust.id):
        envelope = await _schedule(
            mcp_registry, conv, run_at=datetime.now(UTC) - timedelta(hours=1)
        )

    assert envelope["result"]["status"] == "scheduled"


# ── how many per customer and day ───────────────────────────────────────────


async def test_the_fourth_reminder_of_the_day_is_refused(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    await seed_reminder_policy(db_session, tenant_id=a, templates=[TEMPLATE])
    cust, conv = await _customer_conversation(db_session, a)

    with tenant_context(a), customer_context(cust.id):
        for _ in range(3):
            await _schedule(mcp_registry, conv)
        with pytest.raises(ToolError, match=r"3 reminders .* last 24 hours"):
            await _schedule(mcp_registry, conv)

    assert len(await _reminders(a)) == 3


async def test_the_cap_follows_the_customer_across_conversations(
    db_session, two_tenants, mcp_registry
):
    a = two_tenants["a"]
    await seed_reminder_policy(db_session, tenant_id=a, templates=[TEMPLATE])
    cust, first = await _customer_conversation(db_session, a)
    _, second = await seed_channel_and_conversation(
        db_session, tenant_id=a, customer_id=cust.id, provider_identifier="wa-otro-numero"
    )

    with tenant_context(a), customer_context(cust.id):
        for _ in range(3):
            await _schedule(mcp_registry, first)
        with pytest.raises(ToolError, match="last 24 hours"):
            await _schedule(mcp_registry, second)


async def test_another_customer_is_not_affected(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    await seed_reminder_policy(db_session, tenant_id=a, templates=[TEMPLATE])
    ana, ana_conv = await _customer_conversation(db_session, a, "ana")
    luis, luis_conv = await _customer_conversation(db_session, a, "luis")

    with tenant_context(a), customer_context(ana.id):
        for _ in range(3):
            await _schedule(mcp_registry, ana_conv)
    with tenant_context(a), customer_context(luis.id):
        envelope = await _schedule(mcp_registry, luis_conv)

    assert envelope["result"]["status"] == "scheduled"


async def test_cancelled_reminders_do_not_count(db_session, two_tenants, mcp_registry):
    """A rescheduled booking cancels its two reminders and creates two more."""
    a = two_tenants["a"]
    await seed_reminder_policy(db_session, tenant_id=a, templates=[TEMPLATE])
    cust, conv = await _customer_conversation(db_session, a)

    with tenant_context(a), customer_context(cust.id):
        for _ in range(3):
            await _schedule(mcp_registry, conv)
    await _set_reminders(a, status=ScheduledJobStatus.CANCELLED)
    with tenant_context(a), customer_context(cust.id):
        envelope = await _schedule(mcp_registry, conv)

    assert envelope["result"]["status"] == "scheduled"


async def test_reminders_older_than_a_day_do_not_count(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    await seed_reminder_policy(db_session, tenant_id=a, templates=[TEMPLATE])
    cust, conv = await _customer_conversation(db_session, a)

    with tenant_context(a), customer_context(cust.id):
        for _ in range(3):
            await _schedule(mcp_registry, conv)
    await _set_reminders(
        a,
        status=ScheduledJobStatus.SENT,
        created_at=datetime.now(UTC) - timedelta(hours=25),
    )
    with tenant_context(a), customer_context(cust.id):
        envelope = await _schedule(mcp_registry, conv)

    assert envelope["result"]["status"] == "scheduled"


async def test_the_business_sets_its_own_cap(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    await seed_reminder_policy(
        db_session, tenant_id=a, templates=[TEMPLATE], max_per_customer_per_day=1
    )
    cust, conv = await _customer_conversation(db_session, a)

    with tenant_context(a), customer_context(cust.id):
        await _schedule(mcp_registry, conv)
        with pytest.raises(ToolError, match=r"limit 1\b"):
            await _schedule(mcp_registry, conv)


async def test_no_policy_goes_beyond_ten_a_day(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    await seed_reminder_policy(
        db_session, tenant_id=a, templates=[TEMPLATE], max_per_customer_per_day=1000
    )
    cust, conv = await _customer_conversation(db_session, a)

    with tenant_context(a), customer_context(cust.id):
        for _ in range(10):
            await _schedule(mcp_registry, conv)
        with pytest.raises(ToolError, match=r"limit 10\b"):
            await _schedule(mcp_registry, conv)

    assert len(await _reminders(a)) == 10


async def test_two_calls_at_once_cannot_both_take_the_last_slot(
    db_session, two_tenants, mcp_registry
):
    """Without a lock both read the same count and both insert."""
    a = two_tenants["a"]
    await seed_reminder_policy(
        db_session, tenant_id=a, templates=[TEMPLATE], max_per_customer_per_day=1
    )
    cust, conv = await _customer_conversation(db_session, a)

    with tenant_context(a), customer_context(cust.id):
        outcomes = await asyncio.gather(
            *(_schedule(mcp_registry, conv) for _ in range(4)),
            return_exceptions=True,
        )

    scheduled = [o for o in outcomes if isinstance(o, dict)]
    refused = [o for o in outcomes if isinstance(o, ToolError)]
    assert (len(scheduled), len(refused)) == (1, 3), outcomes
    assert len(await _reminders(a)) == 1
