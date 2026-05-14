"""Async booking cron — drains ``scheduled_jobs`` of kind=async_booking.

Block O / ADR-017: ``booking.create_appointment`` no longer talks to
AgendaPro inline. For tenants with ``agendapro_public_url`` set, the
tool persists the appointment provisionally (``public_booking_status=
pending``) and enqueues a job here. This cron picks up the job,
drives the public booking wizard via the Node MCP, and:

- On ``status="confirmed"`` (with ``external_ref``):
  ``appointments.external_ref`` + ``public_booking_status="confirmed"``,
  then queue ``notification.send_template("booking_confirmation_ack")``
  so the customer sees the final confirmation in a separate WhatsApp
  message (asynchronous pattern from the ``barbershop_v1`` seed).

- On ``status="ambiguous"`` (submit succeeded but external_ref scrape
  failed): ``public_booking_status="manual_escalation"`` + escalate
  to the owner via the backchannel so they verify in the AgendaPro
  panel.

- On ``status="failed"`` (wizard never reached confirm):
  * Increment ``attempts``. Re-schedule with backoff if attempts < 3.
  * After max attempts: ``public_booking_status="failed"`` +
    escalate to the owner.

Tick interval is intentionally tight (5s) — the customer is waiting on
the agent's ACK and the wizard latency itself is the dominant factor;
tick latency on top would be unbearable.

Tenant isolation: same RLS-aware ``tenant_scoped_session`` pattern as
the reminder cron. The dispatch_internal call to ``agendapro_public.*``
requires the in-process caller token (defense in depth).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Appointment,
    Conversation,
    ConversationStatus,
    Customer,
    ScheduledJob,
    ScheduledJobKind,
    ScheduledJobStatus,
    Tenant,
    TenantStatus,
)
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 5.0
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (15, 60, 180)  # per attempt index

# When the cron detects that the ``scheduled_job_kind`` enum doesn't
# yet carry the ``async_booking`` value (migration 0022 not applied on
# this DB) we back off to this longer interval and log only once per
# process. This keeps the worker logs readable during the window
# between code-deploy and migration-apply.
SCHEMA_DESYNC_BACKOFF_SECONDS = 60.0

ACTOR = "system:async_booking_cron"

# Template names used at the boundary of this cron. Both must exist as
# APPROVED templates on the tenant's WABA before this cron fires anything;
# the notification.send_template tool's guard rejects non-APPROVED rows
# so a misconfigured tenant fails loudly here without spamming the customer.
TEMPLATE_BOOKING_CONFIRMED = "booking_confirmation_ack"
TEMPLATE_BOOKING_FAILED = "booking_failed_ack"


async def run_async_booking_cron(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    """Background task. One pass per tick_seconds.

    Tolerant of the ``async_booking`` enum value missing from the DB —
    that means migration 0022 hasn't been applied yet. In that case
    the cron logs a single warning, backs off to ``SCHEMA_DESYNC_BACKOFF_
    SECONDS`` and stops polluting the log with stack traces until the
    migration lands.
    """
    log.info("async_booking_cron.start", tick_seconds=tick_seconds)
    sm = get_sessionmaker()
    schema_warning_logged = False
    while not stop.is_set():
        tick_for_this_iteration = tick_seconds
        try:
            await _process_pending(sm)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if _is_async_booking_enum_missing(exc):
                if not schema_warning_logged:
                    log.warning(
                        "async_booking_cron.schema_desync",
                        hint=(
                            "scheduled_job_kind enum is missing 'async_booking' "
                            "— run `alembic upgrade head` on the DB. Cron will "
                            "back off until the migration is applied."
                        ),
                    )
                    schema_warning_logged = True
                tick_for_this_iteration = SCHEMA_DESYNC_BACKOFF_SECONDS
            else:
                log.error("async_booking_cron.tick_failed", error=str(exc))
        else:
            # Successful pass — re-arm the warning so a *second* episode
            # of desync (e.g. failover to an older replica) would log
            # again instead of staying silent.
            schema_warning_logged = False
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_for_this_iteration)
    log.info("async_booking_cron.stopped")


def _is_async_booking_enum_missing(exc: BaseException) -> bool:
    """True when the error chain carries the postgres
    ``InvalidTextRepresentationError`` for the async_booking enum value.

    SQLAlchemy wraps the asyncpg exception in a DBAPI error; we walk
    the cause chain. Matching on the message keeps the check robust
    across asyncpg / psycopg / psycopg2 drivers in case the worker
    ever swaps.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        message = str(current).lower()
        if (
            "invalid input value for enum scheduled_job_kind" in message
            and "async_booking" in message
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


async def _process_pending(sm: sa.orm.sessionmaker) -> None:  # type: ignore[type-arg]
    async with sm() as session:
        tenant_ids_result = await session.execute(
            sa.select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE)
        )
        tenant_ids = [r[0] for r in tenant_ids_result]

    for tid in tenant_ids:
        async with sm() as session, tenant_scoped_session(session, tid):
            await _drain_tenant(session, tid)


async def _drain_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    rows_result = await session.execute(
        sa.select(ScheduledJob)
        .where(
            ScheduledJob.kind == ScheduledJobKind.ASYNC_BOOKING,
            ScheduledJob.status == ScheduledJobStatus.PENDING,
            ScheduledJob.run_at <= now,
        )
        .order_by(ScheduledJob.run_at.asc())
        .limit(5)
        .with_for_update(skip_locked=True)
    )
    jobs = list(rows_result.scalars())
    if not jobs:
        return
    log.info(
        "async_booking_cron.batch",
        tenant_id=str(tenant_id),
        count=len(jobs),
    )
    for job in jobs:
        await _execute_one(session, tenant_id, job)


async def _execute_one(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    job: ScheduledJob,
) -> None:
    """Drive the public wizard for one job.

    The session is held across the dispatch_internal call so we can
    atomically update both ``ScheduledJob`` and ``Appointment``. The
    Node MCP call is bounded by its own timeout (90s); the SQL
    transaction here will live for the same duration. That's
    acceptable at expected volumes (one or two booking jobs per
    tenant per minute peak).
    """
    payload = job.payload or {}
    appointment_id_raw = payload.get("appointment_id")
    if not isinstance(appointment_id_raw, str):
        await _mark_job_failed(job, "malformed payload: appointment_id missing")
        await session.flush()
        return
    try:
        appointment_id = uuid.UUID(appointment_id_raw)
    except ValueError:
        await _mark_job_failed(job, "malformed payload: appointment_id not uuid")
        await session.flush()
        return

    appointment = await session.get(Appointment, appointment_id)
    if appointment is None:
        await _mark_job_failed(job, "appointment row missing (tenant scope?)")
        await session.flush()
        return

    # Already done by a previous tick (idempotency / double-fire safety).
    if appointment.public_booking_status == "confirmed":
        job.status = ScheduledJobStatus.SENT
        await session.flush()
        return

    tenant = await session.get(Tenant, tenant_id)
    public_url = getattr(tenant, "agendapro_public_url", None) if tenant else None
    if not isinstance(public_url, str) or not public_url:
        await _mark_job_failed(
            job, "tenant.agendapro_public_url missing — was it cleared mid-flight?"
        )
        await session.flush()
        return

    # Resolve customer details + conversation_id for the confirmation send.
    customer = await session.get(Customer, appointment.customer_id)
    conversation_id = await _resolve_conversation_id(session, appointment)
    if customer is None or conversation_id is None:
        await _mark_job_failed(
            job,
            f"missing customer={customer is not None} or conversation_id "
            f"for appointment {appointment.id}",
        )
        await session.flush()
        return

    appointment.public_booking_status = "in_progress"
    await session.flush()

    log.info(
        "async_booking_cron.dispatch",
        tenant_id=str(tenant_id),
        appointment_id=str(appointment.id),
        attempts=job.attempts,
    )

    try:
        result = await _call_public_mcp(
            appointment=appointment,
            customer=customer,
            payload=payload,
            public_url=public_url,
        )
    except Exception as exc:
        log.warning(
            "async_booking_cron.transport_error",
            tenant_id=str(tenant_id),
            appointment_id=str(appointment.id),
            error=str(exc),
        )
        await _handle_attempt_failure(
            session,
            tenant_id=tenant_id,
            appointment=appointment,
            job=job,
            conversation_id=conversation_id,
            reason=f"transport: {type(exc).__name__}: {exc}"[:500],
        )
        await session.flush()
        return

    status = (result.get("status") or "").lower()
    external_ref = result.get("external_ref")

    if status == "confirmed" and isinstance(external_ref, str) and external_ref:
        appointment.external_ref = external_ref
        appointment.public_booking_status = "confirmed"
        job.status = ScheduledJobStatus.SENT
        job.last_error = None
        log.info(
            "async_booking_cron.confirmed",
            tenant_id=str(tenant_id),
            appointment_id=str(appointment.id),
            external_ref=external_ref,
        )
        await _queue_confirmation_template(
            session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            appointment=appointment,
            customer=customer,
            external_ref=external_ref,
        )
        await session.flush()
        return

    if status == "ambiguous":
        # Submit went through but we couldn't scrape the confirmation
        # code. Escalate to the owner so they verify manually in the
        # AgendaPro panel before we tell the customer it's confirmed.
        appointment.public_booking_status = "manual_escalation"
        job.status = ScheduledJobStatus.SENT  # terminal: the cron's done
        job.last_error = "ambiguous result — escalated to owner"
        log.warning(
            "async_booking_cron.ambiguous_escalating",
            tenant_id=str(tenant_id),
            appointment_id=str(appointment.id),
        )
        await _queue_owner_escalation(
            session,
            tenant_id=tenant_id,
            appointment=appointment,
            kind="manual_verify",
            note=str(result.get("failure_reason") or ""),
        )
        await session.flush()
        return

    # status == "failed" or unknown → counts as a failed attempt.
    failure_reason = str(result.get("failure_reason") or status or "unknown")
    await _handle_attempt_failure(
        session,
        tenant_id=tenant_id,
        appointment=appointment,
        job=job,
        conversation_id=conversation_id,
        reason=failure_reason,
    )
    await session.flush()


async def _resolve_conversation_id(
    session: AsyncSession, appointment: Appointment
) -> uuid.UUID | None:
    """Find the active conversation for the appointment's customer.

    The booking flow always runs inside an active conversation, so the
    open conversation for ``(customer, any channel)`` is the one the
    notification should target. If multiple are open we pick the most
    recent — best-effort; the conversation_id is only used to route
    the WhatsApp confirmation back to the right thread.
    """
    result = await session.execute(
        sa.select(Conversation.id)
        .where(
            Conversation.customer_id == appointment.customer_id,
            Conversation.status == ConversationStatus.OPEN,
        )
        .order_by(Conversation.updated_at.desc())
        .limit(1)
    )
    row = result.first()
    return row[0] if row else None


async def _call_public_mcp(
    *,
    appointment: Appointment,
    customer: Customer,
    payload: dict[str, Any],
    public_url: str,
) -> dict[str, Any]:
    """Run ``dispatch_internal('agendapro_public.create_appointment', ...)``.

    The MCP registry's internal-call surface enforces the caller token
    invariant; we never expose the token to caller code other than this
    function (and the booking facade if we ever need it there).
    """
    from nexus_mcp import build_default_registry, get_internal_caller_token

    registry = build_default_registry()
    args: dict[str, Any] = {
        "public_url": public_url,
        "slot": {
            "starts_at_iso": appointment.starts_at.isoformat(),
            "duration_min": appointment.service_duration_min,
            # The cron doesn't know the slot_token from the wizard's
            # observe() call. Fall back to a text-match slot_token; the
            # Node flow handles the fallback path.
            "barber_slot_token": (
                payload.get("barber_slot_token") or f"text:{_format_time(appointment.starts_at)}"
            ),
        },
        "customer": {
            "name": customer.name or "Cliente",
            "phone_e164": customer.identifier,
            # AgendaPro's wizard insists on email. Use a synthetic one
            # if the customer didn't share theirs — Auphere owns the
            # domain so noreply addresses don't bounce visibly.
            "email": _customer_email(customer),
        },
        "service_hint": appointment.service_name,
        "idempotency_key": appointment.idempotency_key or f"appt:{appointment.id}",
    }
    envelope = await registry.dispatch_internal(
        "agendapro_public.create_appointment",
        args,
        caller_token=get_internal_caller_token(),
    )
    # The envelope shape is {"tool": ..., "result": {...}, "status": "ok"}
    # — we want the inner ``result``.
    result = envelope.get("result") or {}
    return result if isinstance(result, dict) else {}


def _format_time(dt: datetime) -> str:
    """HH:MM string the Node fallback matcher uses."""
    return dt.astimezone(UTC).strftime("%H:%M")


def _customer_email(customer: Customer) -> str:
    prefs = customer.preferences or {}
    email = prefs.get("email") if isinstance(prefs, dict) else None
    if isinstance(email, str) and "@" in email:
        return email
    # Synthetic email derived from the customer identifier — needed for
    # the AgendaPro wizard's required field. We use an Auphere-owned
    # subdomain so AgendaPro can't bounce or spam.
    safe = "".join(c if c.isalnum() else "_" for c in customer.identifier)[:40]
    return f"noreply+{safe}@notifications.auphere.com"


async def _handle_attempt_failure(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    appointment: Appointment,
    job: ScheduledJob,
    conversation_id: uuid.UUID | None,
    reason: str,
) -> None:
    """Increment attempts; either retry with backoff or terminally fail."""
    job.attempts += 1
    job.last_error = reason[:500]
    if job.attempts >= MAX_ATTEMPTS:
        appointment.public_booking_status = "failed"
        job.status = ScheduledJobStatus.FAILED
        log.warning(
            "async_booking_cron.failed_terminal",
            tenant_id=str(tenant_id),
            appointment_id=str(appointment.id),
            attempts=job.attempts,
            reason=reason,
        )
        await _queue_owner_escalation(
            session,
            tenant_id=tenant_id,
            appointment=appointment,
            kind="failed_max_attempts",
            note=reason,
        )
        if conversation_id is not None:
            await _queue_failure_template(
                session,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                appointment=appointment,
            )
        return
    # Reschedule with backoff.
    backoff = RETRY_BACKOFF_SECONDS[min(job.attempts - 1, len(RETRY_BACKOFF_SECONDS) - 1)]
    job.run_at = datetime.now(UTC) + timedelta(seconds=backoff)
    appointment.public_booking_status = "pending"
    log.info(
        "async_booking_cron.retry_scheduled",
        tenant_id=str(tenant_id),
        appointment_id=str(appointment.id),
        attempts=job.attempts,
        retry_in_s=backoff,
        reason=reason,
    )


def _mark_job_failed_sync(job: ScheduledJob, reason: str) -> None:
    job.status = ScheduledJobStatus.FAILED
    job.last_error = reason[:500]
    job.attempts += 1


async def _mark_job_failed(job: ScheduledJob, reason: str) -> None:
    _mark_job_failed_sync(job, reason)
    log.warning("async_booking_cron.malformed_job_failed", reason=reason)


# ── notifications / escalation ────────────────────────────────────────────


async def _queue_confirmation_template(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    appointment: Appointment,
    customer: Customer,
    external_ref: str,
) -> None:
    from nexus_api.db.models import Message, MessageDirection, MessageStatus

    params: dict[str, Any] = {
        "customer_name": customer.name or "cliente",
        "service": appointment.service_name,
        "starts_at": appointment.starts_at.isoformat(),
        "external_ref": external_ref,
    }
    content = f"[template:{TEMPLATE_BOOKING_CONFIRMED}] " + ", ".join(
        f"{k}={v!r}" for k, v in sorted(params.items())
    )
    msg = Message(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.PENDING,
        content=content,
        tool_calls=[
            {
                "tool": "notification.send_template",
                "template": TEMPLATE_BOOKING_CONFIRMED,
                "language": "es",
                "parameters": params,
                "source": "async_booking_cron",
            }
        ],
    )
    session.add(msg)


async def _queue_failure_template(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    appointment: Appointment,
) -> None:
    from nexus_api.db.models import Message, MessageDirection, MessageStatus

    params = {
        "service": appointment.service_name,
        "starts_at": appointment.starts_at.isoformat(),
    }
    content = f"[template:{TEMPLATE_BOOKING_FAILED}] " + ", ".join(
        f"{k}={v!r}" for k, v in sorted(params.items())
    )
    msg = Message(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.PENDING,
        content=content,
        tool_calls=[
            {
                "tool": "notification.send_template",
                "template": TEMPLATE_BOOKING_FAILED,
                "language": "es",
                "parameters": params,
                "source": "async_booking_cron",
            }
        ],
    )
    session.add(msg)


async def _queue_owner_escalation(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    appointment: Appointment,
    kind: str,
    note: str,
) -> None:
    """Persist an audit log entry the operator alerter consumes.

    Phase 1 doesn't yet call ``operator.consult_owner`` directly from
    here — the alerter picks up audit_log rows and dispatches the owner
    backchannel template. This keeps the cron's surface small and lets
    the existing ADR-018 pipeline handle owner notification consistently.
    """
    from nexus_api.db.models import AuditLog

    audit = AuditLog(
        tenant_id=tenant_id,
        actor=ACTOR,
        action="async_booking.escalation",
        target=f"appointment:{appointment.id}",
        before_json=None,
        after_json={
            "kind": kind,
            "note": note[:500],
            "service": appointment.service_name,
            "starts_at": appointment.starts_at.isoformat(),
        },
    )
    session.add(audit)
