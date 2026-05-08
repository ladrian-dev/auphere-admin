"""notification.* — durable persistence of outbound messages and reminders.

Block D persists. Block F sends. Two surfaces:

- ``send_template`` / ``send_text`` insert a row into ``messages`` with
  ``direction='outbound'`` and ``status='pending'``. Block F's outbound
  dispatcher polls pending rows, pushes them through YCloud and flips the
  status to ``'sent'`` (or ``'failed'`` with retries).

- ``schedule_reminder`` / ``cancel_scheduled`` write to ``scheduled_jobs``
  with ``kind='reminder'``. Block H wires the cron dispatcher; Block D
  only stores the durable record and returns the id.

Note: the existing checkpoint node in the worker pipeline persists the
agent's reply with default ``status='sent'`` — we keep that behaviour for
backwards-compat with block C tests. Block F will revisit and unify both
paths under ``status='pending'``.
"""

from __future__ import annotations

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import (
    Conversation,
    Message,
    MessageDirection,
    MessageStatus,
    ScheduledJob,
    ScheduledJobKind,
    ScheduledJobStatus,
)
from sqlalchemy import select

from nexus_mcp._db import tool_session
from nexus_mcp.base import InputModel, OutputModel, ToolBase, ToolError
from nexus_mcp.servers.notification.schemas import (
    CancelScheduledInput,
    CancelScheduledOutput,
    ScheduleReminderInput,
    ScheduleReminderOutput,
    SendTemplateInput,
    SendTemplateOutput,
    SendTextInput,
    SendTextOutput,
)


def _summarise_template(name: str, params: dict[str, str | int | float | bool | None]) -> str:
    """Render a debugging-friendly content string for the messages.content
    column — the actual outbound rendering is YCloud's job in Block F."""
    if not params:
        return f"[template:{name}]"
    rendered = ", ".join(f"{k}={v!r}" for k, v in sorted(params.items()))
    return f"[template:{name}] {rendered}"


# ── send_template ────────────────────────────────────────────────────────────


class SendTemplate(ToolBase):
    name = "notification.send_template"
    description = (
        "Queue a Meta-approved WhatsApp template for delivery. The row is written "
        "with status='pending'; Block F's outbound dispatcher pushes it through "
        "YCloud and flips the status to 'sent'. Use templates when the conversation "
        "is OUTSIDE the 24h customer service window."
    )
    input_model = SendTemplateInput
    output_model = SendTemplateOutput
    side_effects = ("sends_message",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, SendTemplateInput)
        tenant_id = require_current_tenant()
        async with tool_session() as session:
            conv = await session.get(Conversation, payload.conversation_id)
            if conv is None:
                raise ToolError(f"conversation {payload.conversation_id} not found for this tenant")
            content = _summarise_template(payload.template_name, payload.parameters)
            msg = Message(
                tenant_id=tenant_id,
                conversation_id=conv.id,
                direction=MessageDirection.OUTBOUND,
                status=MessageStatus.PENDING,
                content=content,
                tool_calls=[
                    {
                        "tool": "notification.send_template",
                        "template": payload.template_name,
                        "parameters": payload.parameters,
                    }
                ],
            )
            session.add(msg)
            await session.flush()
            await session.refresh(msg)
            msg_id = msg.id
        return SendTemplateOutput(message_id=msg_id, status="pending")


# ── send_text ────────────────────────────────────────────────────────────────


class SendText(ToolBase):
    name = "notification.send_text"
    description = (
        "Queue a free-form text message. Only valid INSIDE the 24h customer "
        "service window — outside, use send_template. The row is persisted with "
        "status='pending'; Block F sends it via YCloud."
    )
    input_model = SendTextInput
    output_model = SendTextOutput
    side_effects = ("sends_message",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, SendTextInput)
        tenant_id = require_current_tenant()
        async with tool_session() as session:
            conv = await session.get(Conversation, payload.conversation_id)
            if conv is None:
                raise ToolError(f"conversation {payload.conversation_id} not found for this tenant")
            msg = Message(
                tenant_id=tenant_id,
                conversation_id=conv.id,
                direction=MessageDirection.OUTBOUND,
                status=MessageStatus.PENDING,
                content=payload.body,
                tool_calls=[{"tool": "notification.send_text"}],
            )
            session.add(msg)
            await session.flush()
            await session.refresh(msg)
            msg_id = msg.id
        return SendTextOutput(message_id=msg_id, status="pending")


# ── schedule_reminder ────────────────────────────────────────────────────────


class ScheduleReminder(ToolBase):
    name = "notification.schedule_reminder"
    description = (
        "Persist a future-dated reminder. Block H's cron dispatcher reads the "
        "scheduled_jobs table, finds rows where run_at<=now() and status='pending', "
        "and fires the corresponding template. Returns the reminder_id so the "
        "caller can later cancel it via notification.cancel_scheduled."
    )
    input_model = ScheduleReminderInput
    output_model = ScheduleReminderOutput
    side_effects = ("mutates_db",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, ScheduleReminderInput)
        tenant_id = require_current_tenant()
        async with tool_session() as session:
            conv = await session.get(Conversation, payload.conversation_id)
            if conv is None:
                raise ToolError(f"conversation {payload.conversation_id} not found for this tenant")
            job_payload = {
                "conversation_id": str(payload.conversation_id),
                "appointment_id": (str(payload.appointment_id) if payload.appointment_id else None),
                "template_name": payload.template_name,
                "parameters": payload.parameters,
            }
            job = ScheduledJob(
                tenant_id=tenant_id,
                kind=ScheduledJobKind.REMINDER,
                run_at=payload.run_at,
                payload=job_payload,
                status=ScheduledJobStatus.PENDING,
            )
            session.add(job)
            await session.flush()
            await session.refresh(job)
            job_id = job.id
            run_at = job.run_at
        return ScheduleReminderOutput(reminder_id=job_id, run_at=run_at, status="scheduled")


# ── cancel_scheduled ─────────────────────────────────────────────────────────


class CancelScheduled(ToolBase):
    name = "notification.cancel_scheduled"
    description = (
        "Cancel a previously-scheduled reminder. Idempotent: cancelling an "
        "already-cancelled or already-sent reminder is a no-op."
    )
    input_model = CancelScheduledInput
    output_model = CancelScheduledOutput
    side_effects = ("mutates_db",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, CancelScheduledInput)
        async with tool_session() as session:
            stmt = select(ScheduledJob).where(ScheduledJob.id == payload.reminder_id)
            job = (await session.execute(stmt)).scalar_one_or_none()
            if job is None:
                raise ToolError(f"reminder {payload.reminder_id} not found for this tenant")
            if job.status == ScheduledJobStatus.PENDING:
                job.status = ScheduledJobStatus.CANCELLED
                await session.flush()
                final = "cancelled"
            else:
                final = f"noop:{job.status.value}"
        return CancelScheduledOutput(reminder_id=payload.reminder_id, status=final)


NOTIFICATION_TOOLS: tuple[type[ToolBase], ...] = (
    SendTemplate,
    SendText,
    ScheduleReminder,
    CancelScheduled,
)
