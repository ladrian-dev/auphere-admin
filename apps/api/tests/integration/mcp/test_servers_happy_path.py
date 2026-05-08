"""Happy-path coverage for the 21 Block-D tools.

Each tool gets at least one assertion that the dispatch returns a sensible
envelope and (for mutating tools) that the database state changed.

Cross-tenant test asserts a row written under tenant A cannot be read
through ``booking.get_appointments`` from tenant B's context.

Smoke test follows the canonical "Booking with preferred barber" flow
from verticals/barbershop_v1.md, end-to-end through the registry.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from nexus_mcp.base import ToolNotInWhitelist

from nexus_api.core.tenant_context import tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Appointment,
    AppointmentStatus,
    AuditLog,
    Conversation,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageStatus,
    QueueEntry,
    QueueEntryStatus,
    ScheduledJob,
    ScheduledJobStatus,
)

from .conftest import (
    all_whitelist,
    seed_barber,
    seed_channel_and_conversation,
    seed_customer,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


# ── helpers ──────────────────────────────────────────────────────────────────


async def _read_in_tenant(tenant_id, fn):
    """Run a callable that takes a session, inside that tenant's RLS scope."""
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        return await fn(session)


# ── escalate ─────────────────────────────────────────────────────────────────


async def test_escalate_to_human_persists_audit_and_flips_status(
    db_session, two_tenants, mcp_registry
):
    a = two_tenants["a"]
    cust = await seed_customer(db_session, tenant_id=a)
    _, conv = await seed_channel_and_conversation(
        db_session, tenant_id=a, customer_id=cust.id, provider_identifier="esc-1"
    )

    with tenant_context(a):
        envelope = await mcp_registry.dispatch(
            "escalate.escalate_to_human",
            {"conversation_id": str(conv.id), "reason": "agente sin contexto"},
            whitelist=all_whitelist(),
        )

    assert envelope["status"] == "ok"
    assert envelope["result"]["status"] == "operator_notified"

    async def _check(s):
        from sqlalchemy import select

        c = await s.get(Conversation, conv.id)
        assert c is not None
        assert c.status == ConversationStatus.ESCALATED
        rows = (
            (await s.execute(select(AuditLog).where(AuditLog.action == "conversation.escalated")))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].after_json is not None
        assert rows[0].after_json.get("reason") == "agente sin contexto"

    await _read_in_tenant(a, _check)


# ── client ───────────────────────────────────────────────────────────────────


async def test_client_get_preferences_returns_empty_for_new_customer(
    db_session, two_tenants, mcp_registry
):
    a = two_tenants["a"]
    cust = await seed_customer(db_session, tenant_id=a)
    with tenant_context(a):
        envelope = await mcp_registry.dispatch(
            "client.get_preferences",
            {"customer_id": str(cust.id)},
            whitelist=all_whitelist(),
        )
    assert envelope["result"]["preferences"] == {}


async def test_client_update_preferences_merges(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    cust = await seed_customer(db_session, tenant_id=a)
    with tenant_context(a):
        await mcp_registry.dispatch(
            "client.update_preferences",
            {"customer_id": str(cust.id), "preferences": {"preferred_barber": "Luis"}},
            whitelist=all_whitelist(),
        )
        e2 = await mcp_registry.dispatch(
            "client.update_preferences",
            {"customer_id": str(cust.id), "preferences": {"language": "es"}},
            whitelist=all_whitelist(),
        )
    assert e2["result"]["preferences"] == {"preferred_barber": "Luis", "language": "es"}


async def test_client_get_history_returns_appointments_in_recent_first_order(
    db_session, two_tenants, mcp_registry
):
    a = two_tenants["a"]
    cust = await seed_customer(db_session, tenant_id=a)
    barber = await seed_barber(db_session, tenant_id=a)

    sm = get_sessionmaker()
    now = datetime.now(UTC)
    async with sm() as session, tenant_scoped_session(session, a):
        for i, days_back in enumerate([10, 3, 30]):
            session.add(
                Appointment(
                    tenant_id=a,
                    customer_id=cust.id,
                    barber_id=barber.id,
                    service_name="corte",
                    service_duration_min=30,
                    starts_at=now - timedelta(days=days_back),
                    ends_at=now - timedelta(days=days_back) + timedelta(minutes=30),
                    price_cents=12000,
                    currency="CLP",
                    status=AppointmentStatus.COMPLETED,
                    idempotency_key=f"hist-{i}",
                )
            )

    with tenant_context(a):
        env = await mcp_registry.dispatch(
            "client.get_history",
            {"customer_id": str(cust.id), "limit": 10},
            whitelist=all_whitelist(),
        )
    rows = env["result"]["appointments"]
    assert len(rows) == 3
    # Sorted descending by starts_at
    starts = [r["starts_at"] for r in rows]
    assert starts == sorted(starts, reverse=True)


# ── booking ──────────────────────────────────────────────────────────────────


async def test_booking_check_availability_returns_slots(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    with tenant_context(a):
        env = await mcp_registry.dispatch(
            "booking.check_availability",
            {
                "on_date": (date.today() + timedelta(days=1)).isoformat(),
                "service_name": "corte",
                "duration_min": 30,
            },
            whitelist=all_whitelist(),
        )
    slots = env["result"]["slots"]
    # Default 10:00-19:00 = 9h, in 30-min steps with 30-min duration -> 17 slots.
    assert len(slots) >= 1
    assert all("starts_at" in s and "ends_at" in s for s in slots)


async def test_booking_create_appointment_idempotent_on_replay(
    db_session, two_tenants, mcp_registry
):
    a = two_tenants["a"]
    cust = await seed_customer(db_session, tenant_id=a)
    args = {
        "customer_id": str(cust.id),
        "service_name": "corte",
        "starts_at": (datetime.now(UTC) + timedelta(days=1, hours=2)).isoformat(),
        "duration_min": 30,
        "price_cents": 12000,
        "idempotency_key": "conv:abc:create_appt:hash1",
    }
    with tenant_context(a):
        e1 = await mcp_registry.dispatch(
            "booking.create_appointment", args, whitelist=all_whitelist()
        )
        e2 = await mcp_registry.dispatch(
            "booking.create_appointment", args, whitelist=all_whitelist()
        )
    assert (
        e1["result"]["appointment"]["appointment_id"]
        == e2["result"]["appointment"]["appointment_id"]
    )
    assert e1["result"]["idempotent_replay"] is False
    assert e2["result"]["idempotent_replay"] is True


async def test_booking_modify_appointment_changes_starts_at(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    cust = await seed_customer(db_session, tenant_id=a)
    starts = datetime.now(UTC) + timedelta(days=1, hours=3)
    new_starts = starts + timedelta(hours=1)
    with tenant_context(a):
        created = await mcp_registry.dispatch(
            "booking.create_appointment",
            {
                "customer_id": str(cust.id),
                "service_name": "corte",
                "starts_at": starts.isoformat(),
                "duration_min": 30,
                "price_cents": 12000,
                "idempotency_key": "mod-1",
            },
            whitelist=all_whitelist(),
        )
        modify = await mcp_registry.dispatch(
            "booking.modify_appointment",
            {
                "appointment_id": created["result"]["appointment"]["appointment_id"],
                "new_starts_at": new_starts.isoformat(),
            },
            whitelist=all_whitelist(),
        )
    assert modify["result"]["status"] == "modified"
    assert modify["result"]["appointment"]["starts_at"].startswith(new_starts.isoformat()[:16])


async def test_booking_cancel_appointment_applies_fee_for_short_notice(
    db_session, two_tenants, mcp_registry
):
    a = two_tenants["a"]
    cust = await seed_customer(db_session, tenant_id=a)
    starts = datetime.now(UTC) + timedelta(hours=2)  # <24h → 50% fee
    with tenant_context(a):
        created = await mcp_registry.dispatch(
            "booking.create_appointment",
            {
                "customer_id": str(cust.id),
                "service_name": "corte",
                "starts_at": starts.isoformat(),
                "duration_min": 30,
                "price_cents": 12000,
                "idempotency_key": "cancel-1",
            },
            whitelist=all_whitelist(),
        )
        cancelled = await mcp_registry.dispatch(
            "booking.cancel_appointment",
            {
                "appointment_id": created["result"]["appointment"]["appointment_id"],
                "reason": "client emergency",
            },
            whitelist=all_whitelist(),
        )
    assert cancelled["result"]["status"] == "cancelled"
    assert cancelled["result"]["fee_pct"] == 50


async def test_booking_get_appointments_filters_by_customer_and_upcoming(
    db_session, two_tenants, mcp_registry
):
    a = two_tenants["a"]
    cust = await seed_customer(db_session, tenant_id=a)
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, a):
        # one past, one future
        for i, delta in enumerate([-2, 5]):
            session.add(
                Appointment(
                    tenant_id=a,
                    customer_id=cust.id,
                    service_name="corte",
                    service_duration_min=30,
                    starts_at=datetime.now(UTC) + timedelta(days=delta),
                    ends_at=datetime.now(UTC) + timedelta(days=delta, minutes=30),
                    price_cents=10000,
                    currency="CLP",
                    status=AppointmentStatus.BOOKED,
                    idempotency_key=f"ga-{i}",
                )
            )

    with tenant_context(a):
        env = await mcp_registry.dispatch(
            "booking.get_appointments",
            {"customer_id": str(cust.id), "only_upcoming": True},
            whitelist=all_whitelist(),
        )
    assert len(env["result"]["appointments"]) == 1


# ── queue ────────────────────────────────────────────────────────────────────


async def test_queue_join_get_position_estimated_wait_check_in_remove(
    db_session, two_tenants, mcp_registry
):
    a = two_tenants["a"]
    cust = await seed_customer(db_session, tenant_id=a)
    with tenant_context(a):
        join = await mcp_registry.dispatch(
            "queue.join_queue",
            {"customer_id": str(cust.id), "service_name": "corte"},
            whitelist=all_whitelist(),
        )
        assert join["result"]["position"] == 1

        pos = await mcp_registry.dispatch(
            "queue.get_position",
            {"customer_id": str(cust.id)},
            whitelist=all_whitelist(),
        )
        assert pos["result"]["position"] == 1

        wait = await mcp_registry.dispatch(
            "queue.get_estimated_wait",
            {},
            whitelist=all_whitelist(),
        )
        assert wait["result"]["queue_length"] == 1

        ci = await mcp_registry.dispatch(
            "queue.check_in",
            {"customer_id": str(cust.id)},
            whitelist=all_whitelist(),
        )
        assert ci["result"]["status"] == "checked_in"

        rm = await mcp_registry.dispatch(
            "queue.remove_from_queue",
            {"customer_id": str(cust.id)},
            whitelist=all_whitelist(),
        )
        assert rm["result"]["status"] == "removed"

    # Queue entry rows reflect the lifecycle.
    async def _check(s):
        from sqlalchemy import select

        rows = (
            (await s.execute(select(QueueEntry).where(QueueEntry.customer_id == cust.id)))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].status == QueueEntryStatus.LEFT

    await _read_in_tenant(a, _check)


# ── commission ───────────────────────────────────────────────────────────────


async def test_commission_calculate_and_reports(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    barber = await seed_barber(db_session, tenant_id=a, commission_pct=0.4)
    cust = await seed_customer(db_session, tenant_id=a)

    sm = get_sessionmaker()
    today = datetime.now(UTC).replace(hour=14, minute=0, second=0, microsecond=0)
    async with sm() as session, tenant_scoped_session(session, a):
        for i in range(2):
            session.add(
                Appointment(
                    tenant_id=a,
                    customer_id=cust.id,
                    barber_id=barber.id,
                    service_name="corte",
                    service_duration_min=30,
                    starts_at=today + timedelta(hours=i),
                    ends_at=today + timedelta(hours=i, minutes=30),
                    price_cents=10000,
                    currency="CLP",
                    status=AppointmentStatus.COMPLETED,
                    idempotency_key=f"com-{i}",
                )
            )

    with tenant_context(a):
        calc = await mcp_registry.dispatch(
            "commission.calculate_commission",
            {"barber_id": str(barber.id), "service_amount_cents": 10000, "tip_amount_cents": 1000},
            whitelist=all_whitelist(),
        )
        assert calc["result"]["commission_cents"] == 4000  # 40% of 10000
        assert calc["result"]["total_cents"] == 5000  # commission + tip

        earnings = await mcp_registry.dispatch(
            "commission.get_barber_earnings",
            {
                "barber_id": str(barber.id),
                "from_date": today.date().isoformat(),
                "to_date": today.date().isoformat(),
            },
            whitelist=all_whitelist(),
        )
        assert earnings["result"]["appointments_count"] == 2
        assert earnings["result"]["gross_revenue_cents"] == 20000
        assert earnings["result"]["commission_cents"] == 8000

        report = await mcp_registry.dispatch(
            "commission.get_daily_report",
            {"on_date": today.date().isoformat()},
            whitelist=all_whitelist(),
        )
        assert report["result"]["appointments_count"] == 2
        assert report["result"]["gross_revenue_cents"] == 20000
        assert len(report["result"]["by_barber"]) == 1


# ── notification ─────────────────────────────────────────────────────────────


async def test_notification_send_template_and_text_and_schedule_and_cancel(
    db_session, two_tenants, mcp_registry
):
    a = two_tenants["a"]
    cust = await seed_customer(db_session, tenant_id=a)
    _, conv = await seed_channel_and_conversation(
        db_session, tenant_id=a, customer_id=cust.id, provider_identifier="not-1"
    )

    with tenant_context(a):
        tpl = await mcp_registry.dispatch(
            "notification.send_template",
            {
                "conversation_id": str(conv.id),
                "template_name": "reminder_24h",
                "parameters": {"name": "Luis"},
            },
            whitelist=all_whitelist(),
        )
        txt = await mcp_registry.dispatch(
            "notification.send_text",
            {"conversation_id": str(conv.id), "body": "Te esperamos."},
            whitelist=all_whitelist(),
        )
        sched = await mcp_registry.dispatch(
            "notification.schedule_reminder",
            {
                "conversation_id": str(conv.id),
                "run_at": (datetime.now(UTC) + timedelta(hours=23)).isoformat(),
                "template_name": "reminder_24h",
                "parameters": {"name": "Luis"},
            },
            whitelist=all_whitelist(),
        )
        cancel = await mcp_registry.dispatch(
            "notification.cancel_scheduled",
            {"reminder_id": sched["result"]["reminder_id"]},
            whitelist=all_whitelist(),
        )

    assert tpl["result"]["status"] == "pending"
    assert txt["result"]["status"] == "pending"
    assert sched["result"]["status"] == "scheduled"
    assert cancel["result"]["status"] == "cancelled"

    async def _check(s):
        from sqlalchemy import select

        msgs = (
            (
                await s.execute(
                    select(Message)
                    .where(Message.conversation_id == conv.id)
                    .where(Message.direction == MessageDirection.OUTBOUND)
                )
            )
            .scalars()
            .all()
        )
        assert len(msgs) == 2
        assert all(m.status == MessageStatus.PENDING for m in msgs)

        jobs = (await s.execute(select(ScheduledJob))).scalars().all()
        assert len(jobs) == 1
        assert jobs[0].status == ScheduledJobStatus.CANCELLED

    await _read_in_tenant(a, _check)


# ── cross-tenant isolation ───────────────────────────────────────────────────


async def test_booking_get_appointments_does_not_leak_across_tenants(
    db_session, two_tenants, mcp_registry
):
    a, b = two_tenants["a"], two_tenants["b"]
    cust_a = await seed_customer(db_session, tenant_id=a)

    # A creates an appointment.
    with tenant_context(a):
        await mcp_registry.dispatch(
            "booking.create_appointment",
            {
                "customer_id": str(cust_a.id),
                "service_name": "corte",
                "starts_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                "duration_min": 30,
                "price_cents": 12000,
                "idempotency_key": "cross-1",
            },
            whitelist=all_whitelist(),
        )

    # B asks for appointments — RLS filters out everything from A.
    with tenant_context(b):
        env = await mcp_registry.dispatch(
            "booking.get_appointments",
            {"only_upcoming": True},
            whitelist=all_whitelist(),
        )
    assert env["result"]["appointments"] == []


# ── whitelist enforcement ────────────────────────────────────────────────────


async def test_dispatch_refuses_outside_whitelist(db_session, two_tenants, mcp_registry):
    a = two_tenants["a"]
    cust = await seed_customer(db_session, tenant_id=a)
    with tenant_context(a), pytest.raises(ToolNotInWhitelist):
        await mcp_registry.dispatch(
            "booking.create_appointment",
            {
                "customer_id": str(cust.id),
                "service_name": "corte",
                "starts_at": datetime.now(UTC).isoformat(),
                "duration_min": 30,
                "price_cents": 0,
                "idempotency_key": "wl-1",
            },
            whitelist=["client.get_history"],
        )


# ── flow 1 smoke: booking with preferred barber ──────────────────────────────


async def test_flow1_booking_with_preferred_barber_smoke(db_session, two_tenants, mcp_registry):
    """Exercises the canonical flow 1 from verticals/barbershop_v1.md
    using only the booking + client + notification servers (AgendaPro is
    Block E)."""
    a = two_tenants["a"]
    cust = await seed_customer(db_session, tenant_id=a, identifier="+56-99-flow1")
    barber = await seed_barber(db_session, tenant_id=a, name="Luis")
    _, conv = await seed_channel_and_conversation(
        db_session, tenant_id=a, customer_id=cust.id, provider_identifier="flow1"
    )

    with tenant_context(a):
        # Step 1: agent checks history (returning customer recognised).
        hist = await mcp_registry.dispatch(
            "client.get_history",
            {"customer_id": str(cust.id), "limit": 5},
            whitelist=all_whitelist(),
        )
        assert hist["result"]["appointments"] == []

        # Step 2: check availability with preferred barber.
        avail = await mcp_registry.dispatch(
            "booking.check_availability",
            {
                "on_date": (date.today() + timedelta(days=1)).isoformat(),
                "service_name": "corte",
                "barber_id": str(barber.id),
                "duration_min": 30,
            },
            whitelist=all_whitelist(),
        )
        slots = avail["result"]["slots"]
        assert slots, "expected at least one slot"
        chosen = slots[2]  # third slot ~ 11am

        # Step 3: customer confirms — create appointment with idempotency key.
        created = await mcp_registry.dispatch(
            "booking.create_appointment",
            {
                "customer_id": str(cust.id),
                "service_name": "corte",
                "starts_at": chosen["starts_at"],
                "duration_min": 30,
                "barber_id": str(barber.id),
                "price_cents": 12000,
                "idempotency_key": f"conv:{conv.id}:flow1:luis",
            },
            whitelist=all_whitelist(),
        )
        appt = created["result"]["appointment"]

        # Step 4: schedule 24h + 1h reminders.
        run_24h = (datetime.fromisoformat(chosen["starts_at"]) - timedelta(hours=24)).isoformat()
        run_1h = (datetime.fromisoformat(chosen["starts_at"]) - timedelta(hours=1)).isoformat()
        for run_at in (run_24h, run_1h):
            sched = await mcp_registry.dispatch(
                "notification.schedule_reminder",
                {
                    "conversation_id": str(conv.id),
                    "appointment_id": appt["appointment_id"],
                    "run_at": run_at,
                    "template_name": "reminder_24h",
                    "parameters": {"barber": "Luis"},
                },
                whitelist=all_whitelist(),
            )
            assert sched["result"]["status"] == "scheduled"

    # Verify durable state.
    async def _check(s):
        from sqlalchemy import select

        appts = (
            (await s.execute(select(Appointment).where(Appointment.customer_id == cust.id)))
            .scalars()
            .all()
        )
        assert len(appts) == 1
        assert appts[0].status == AppointmentStatus.BOOKED

        jobs = (await s.execute(select(ScheduledJob))).scalars().all()
        assert len(jobs) == 2
        assert {j.status for j in jobs} == {ScheduledJobStatus.PENDING}

    await _read_in_tenant(a, _check)
