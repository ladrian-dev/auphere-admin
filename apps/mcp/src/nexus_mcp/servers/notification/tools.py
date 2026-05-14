"""notification.* — durable persistence of outbound messages and reminders.

Block D persists. Block F sends. Block N adds:

- **24h customer-service window enforcement** at the tool layer. ``send_text``
  (and the new media tools) refuse to queue when ``now - last_inbound_at >
  24h`` — the agent must use ``send_template`` instead. This validates the
  Cloud API contract server-side rather than trusting the LLM-facing
  description.
- **Template approval guard** in ``send_template``. Reads the cached
  ``whatsapp_template_status`` row populated by the webhook and refuses
  non-APPROVED states with a descriptive error the agent can recover from.
- **Native media tools** — ``send_image``, ``send_audio``, ``send_video``,
  ``send_document``, ``send_location``, ``send_contacts``, ``send_reaction``.
  Each writes a ``Message`` row with the appropriate ``media_kind`` and
  ``media_s3_key``; the outbound dispatcher routes the send.

All tools share the same window check via :func:`_assert_inside_window`
because Cloud API enforces it uniformly across free-form types.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import (
    Channel,
    Conversation,
    Message,
    MessageDirection,
    MessageStatus,
    ScheduledJob,
    ScheduledJobKind,
    ScheduledJobStatus,
    WhatsAppTemplateStatus,
)
from sqlalchemy import select

from nexus_mcp._db import tool_session
from nexus_mcp.base import InputModel, OutputModel, ToolBase, ToolError
from nexus_mcp.servers.notification.schemas import (
    CancelScheduledInput,
    CancelScheduledOutput,
    ScheduleReminderInput,
    ScheduleReminderOutput,
    SendAudioInput,
    SendAudioOutput,
    SendDocumentInput,
    SendDocumentOutput,
    SendImageInput,
    SendImageOutput,
    SendLocationInput,
    SendLocationOutput,
    SendReactionInput,
    SendReactionOutput,
    SendTemplateInput,
    SendTemplateOutput,
    SendTextInput,
    SendTextOutput,
    SendVideoInput,
    SendVideoOutput,
)

# Cloud API enforces a 24h customer-service window for free-form messages.
# We apply the same threshold here so the dispatcher never sends a
# free-form message that Cloud API would reject with 131047.
SERVICE_WINDOW = timedelta(hours=24)


def _summarise_template(name: str, params: dict[str, str | int | float | bool | None]) -> str:
    """Render a debugging-friendly content string for the messages.content
    column — the actual outbound rendering is YCloud's job in Block F."""
    if not params:
        return f"[template:{name}]"
    rendered = ", ".join(f"{k}={v!r}" for k, v in sorted(params.items()))
    return f"[template:{name}] {rendered}"


async def _load_conversation(session: Any, conversation_id: uuid.UUID) -> Conversation:
    conv = await session.get(Conversation, conversation_id)
    if conv is None:
        raise ToolError(f"conversation {conversation_id} not found for this tenant")
    return conv


async def _assert_inside_window(session: Any, conversation: Conversation) -> None:
    """Raise ``ToolError`` if the 24h window has expired.

    A conversation without ``last_inbound_at`` is treated as outside the
    window (the customer has never written) — the agent must use a
    template. This blocks the long-standing class of bugs where the LLM
    hallucinates a free-form reply post-window and Cloud API rejects it
    with 131047.
    """
    last = conversation.last_inbound_at
    if last is None:
        raise ToolError(
            "conversation outside 24h window (no inbound recorded): "
            "use notification.send_template for the customer-service "
            "policy-compliant message"
        )
    now = datetime.now(UTC)
    last_aware = last if last.tzinfo else last.replace(tzinfo=UTC)
    if now - last_aware > SERVICE_WINDOW:
        elapsed_h = (now - last_aware).total_seconds() / 3600
        raise ToolError(
            f"conversation outside 24h window (last inbound {elapsed_h:.1f}h ago): "
            f"use notification.send_template"
        )


async def _resolve_waba_id_for_conversation(session: Any, conversation: Conversation) -> str | None:
    """Best-effort lookup of the WABA id from the conversation's channel.

    Used by the template guard to scope template approval state.
    Returns ``None`` if the channel config doesn't carry waba_id (e.g.
    non-WhatsApp channels, or pre-Block-N channels) — in which case the
    guard is bypassed (the template send proceeds without state check).
    """
    channel = await session.get(Channel, conversation.channel_id)
    if channel is None:
        return None
    cfg = channel.config or {}
    waba_id = cfg.get("waba_id")
    return waba_id if isinstance(waba_id, str) and waba_id else None


async def _assert_template_approved(
    session: Any,
    *,
    waba_id: str | None,
    template_name: str,
    language: str,
) -> None:
    """Refuse to enqueue a non-APPROVED template. Skip when waba_id is
    unknown (no row to check against — let the dispatcher discover the
    issue at send time)."""
    if not waba_id:
        return
    row = await session.scalar(
        select(WhatsAppTemplateStatus).where(
            WhatsAppTemplateStatus.waba_id == waba_id,
            WhatsAppTemplateStatus.template_name == template_name,
            WhatsAppTemplateStatus.language == language,
        )
    )
    if row is None:
        # Template approval state hasn't been seeded yet (Meta hasn't
        # emitted a webhook for this name). Permissive default — better
        # to try the send and let Cloud API tell us.
        return
    if row.status == "approved":
        return
    reason = f" ({row.reason})" if row.reason else ""
    raise ToolError(
        f"template {template_name!r} in {language!r} is {row.status} for "
        f"WABA {waba_id}{reason}; choose an approved template or wait for "
        "Meta to re-approve this one"
    )


async def _queue_outbound(
    session: Any,
    *,
    conversation: Conversation,
    content: str,
    tool_name: str,
    extra_tool_call: dict[str, Any] | None = None,
    media_kind: str | None = None,
    media_s3_key: str | None = None,
    media_filename: str | None = None,
    reaction_emoji: str | None = None,
    reaction_target_wamid: str | None = None,
    context_message_id: str | None = None,
) -> uuid.UUID:
    tenant_id = require_current_tenant()
    payload: dict[str, Any] = {"tool": tool_name}
    if extra_tool_call:
        payload.update(extra_tool_call)
    msg = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.PENDING,
        content=content,
        tool_calls=[payload],
        media_kind=media_kind,
        media_s3_key=media_s3_key,
        media_filename=media_filename,
        reaction_emoji=reaction_emoji,
        reaction_target_wamid=reaction_target_wamid,
        context_message_id=context_message_id,
    )
    session.add(msg)
    await session.flush()
    await session.refresh(msg)
    # SQLAlchemy Mapped[UUID] resolves to Any under mypy --strict;
    # an explicit cast keeps the return type honest.
    msg_id: uuid.UUID = msg.id
    return msg_id


# ── send_template ────────────────────────────────────────────────────────────


class SendTemplate(ToolBase):
    name = "notification.send_template"
    description = (
        "Queue a Meta-approved WhatsApp template for delivery. The row is written "
        "with status='pending'; the outbound dispatcher pushes it through "
        "YCloud and flips the status to 'sent'. Use templates when the conversation "
        "is OUTSIDE the 24h customer service window, when sending a notification "
        "without an inbound trigger, or when the message is MARKETING/UTILITY "
        "category."
    )
    input_model = SendTemplateInput
    output_model = SendTemplateOutput
    side_effects = ("sends_message",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, SendTemplateInput)
        async with tool_session() as session:
            conv = await _load_conversation(session, payload.conversation_id)
            waba_id = await _resolve_waba_id_for_conversation(session, conv)
            await _assert_template_approved(
                session,
                waba_id=waba_id,
                template_name=payload.template_name,
                language=payload.language,
            )
            content = _summarise_template(payload.template_name, payload.parameters)
            msg_id = await _queue_outbound(
                session,
                conversation=conv,
                content=content,
                tool_name="notification.send_template",
                extra_tool_call={
                    "template": payload.template_name,
                    "language": payload.language,
                    "parameters": payload.parameters,
                },
            )
        return SendTemplateOutput(message_id=msg_id, status="pending")


# ── send_text ────────────────────────────────────────────────────────────────


class SendText(ToolBase):
    name = "notification.send_text"
    description = (
        "Queue a free-form text message. Only valid INSIDE the 24h customer "
        "service window — outside, use send_template. The row is persisted with "
        "status='pending'; the outbound dispatcher sends it via YCloud. The tool "
        "enforces the window server-side and rejects with a descriptive error "
        "if the last inbound is too old."
    )
    input_model = SendTextInput
    output_model = SendTextOutput
    side_effects = ("sends_message",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, SendTextInput)
        async with tool_session() as session:
            conv = await _load_conversation(session, payload.conversation_id)
            await _assert_inside_window(session, conv)
            msg_id = await _queue_outbound(
                session,
                conversation=conv,
                content=payload.body,
                tool_name="notification.send_text",
                context_message_id=payload.context_message_id,
            )
        return SendTextOutput(message_id=msg_id, status="pending")


# ── send_image / audio / video / document ───────────────────────────────────


class SendImage(ToolBase):
    name = "notification.send_image"
    description = (
        "Queue an image for delivery. Pass ``media_s3_key`` of a previously "
        "uploaded image (operator's catalog, tool output, or inbound piece "
        "the agent wants to forward). Optional ``caption`` renders below the "
        "image. Subject to the 24h customer-service window."
    )
    input_model = SendImageInput
    output_model = SendImageOutput
    side_effects = ("sends_message",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, SendImageInput)
        async with tool_session() as session:
            conv = await _load_conversation(session, payload.conversation_id)
            await _assert_inside_window(session, conv)
            content = payload.caption or "[image]"
            msg_id = await _queue_outbound(
                session,
                conversation=conv,
                content=content,
                tool_name="notification.send_image",
                media_kind="image",
                media_s3_key=payload.media_s3_key,
                context_message_id=payload.context_message_id,
            )
        return SendImageOutput(message_id=msg_id, status="pending")


class SendAudio(ToolBase):
    name = "notification.send_audio"
    description = (
        "Queue an audio message (voice note). Pass ``media_s3_key`` of an OGG "
        "or M4A audio file. WhatsApp Cloud API requires audio to be a single "
        "OGG/Opus or M4A/AAC stream. Subject to the 24h customer-service window."
    )
    input_model = SendAudioInput
    output_model = SendAudioOutput
    side_effects = ("sends_message",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, SendAudioInput)
        async with tool_session() as session:
            conv = await _load_conversation(session, payload.conversation_id)
            await _assert_inside_window(session, conv)
            msg_id = await _queue_outbound(
                session,
                conversation=conv,
                content="[audio]",
                tool_name="notification.send_audio",
                media_kind="audio",
                media_s3_key=payload.media_s3_key,
                context_message_id=payload.context_message_id,
            )
        return SendAudioOutput(message_id=msg_id, status="pending")


class SendVideo(ToolBase):
    name = "notification.send_video"
    description = (
        "Queue a video for delivery. Pass ``media_s3_key`` of an MP4 file. "
        "Optional ``caption`` renders below the video. Subject to the 24h "
        "customer-service window."
    )
    input_model = SendVideoInput
    output_model = SendVideoOutput
    side_effects = ("sends_message",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, SendVideoInput)
        async with tool_session() as session:
            conv = await _load_conversation(session, payload.conversation_id)
            await _assert_inside_window(session, conv)
            content = payload.caption or "[video]"
            msg_id = await _queue_outbound(
                session,
                conversation=conv,
                content=content,
                tool_name="notification.send_video",
                media_kind="video",
                media_s3_key=payload.media_s3_key,
                context_message_id=payload.context_message_id,
            )
        return SendVideoOutput(message_id=msg_id, status="pending")


class SendDocument(ToolBase):
    name = "notification.send_document"
    description = (
        "Queue a document (PDF / DOCX / image of a document) for delivery. "
        "Pass ``media_s3_key`` and an optional ``filename`` so the recipient "
        "sees a useful name on the file card. Subject to the 24h customer-"
        "service window."
    )
    input_model = SendDocumentInput
    output_model = SendDocumentOutput
    side_effects = ("sends_message",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, SendDocumentInput)
        async with tool_session() as session:
            conv = await _load_conversation(session, payload.conversation_id)
            await _assert_inside_window(session, conv)
            content = payload.caption or (payload.filename or "[document]")
            msg_id = await _queue_outbound(
                session,
                conversation=conv,
                content=content,
                tool_name="notification.send_document",
                media_kind="document",
                media_s3_key=payload.media_s3_key,
                media_filename=payload.filename,
                context_message_id=payload.context_message_id,
            )
        return SendDocumentOutput(message_id=msg_id, status="pending")


class SendLocation(ToolBase):
    name = "notification.send_location"
    description = (
        "Send a location pin. Useful for the barbershop's address when the "
        "customer asks how to get there. Subject to the 24h customer-service "
        "window."
    )
    input_model = SendLocationInput
    output_model = SendLocationOutput
    side_effects = ("sends_message",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, SendLocationInput)
        async with tool_session() as session:
            conv = await _load_conversation(session, payload.conversation_id)
            await _assert_inside_window(session, conv)
            # Location lives in tool_calls so the dispatcher can rebuild
            # the Cloud API payload. ``content`` carries a human-readable
            # rendering for the operator panel.
            content = (
                f"[location:lat={payload.latitude:.6f},"
                f"lon={payload.longitude:.6f}]"
                f"{payload.name or ''}".strip()
            )
            msg_id = await _queue_outbound(
                session,
                conversation=conv,
                content=content,
                tool_name="notification.send_location",
                extra_tool_call={
                    "latitude": payload.latitude,
                    "longitude": payload.longitude,
                    "name": payload.name,
                    "address": payload.address,
                },
                # No media_kind=location yet; the dispatcher uses
                # tool_calls to rebuild the payload. We keep media_kind
                # reserved for actual S3-backed media.
                context_message_id=payload.context_message_id,
            )
        return SendLocationOutput(message_id=msg_id, status="pending")


class SendReaction(ToolBase):
    name = "notification.send_reaction"
    description = (
        "React to a previous customer message with an emoji. Pass the wamid "
        "of the target message via ``target_message_id``. Pass an empty "
        "``emoji`` to remove a previously-set reaction. Reactions are "
        "*outside* the 24h window concept — they're treated as service "
        "callbacks by Meta and always allowed."
    )
    input_model = SendReactionInput
    output_model = SendReactionOutput
    side_effects = ("sends_message",)

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, SendReactionInput)
        async with tool_session() as session:
            conv = await _load_conversation(session, payload.conversation_id)
            # Reactions are not subject to the 24h window check — Meta
            # allows reacting to any message in scope.
            content = f"[reaction:{payload.emoji or '(removed)'}:on={payload.target_message_id}]"
            msg_id = await _queue_outbound(
                session,
                conversation=conv,
                content=content,
                tool_name="notification.send_reaction",
                reaction_emoji=payload.emoji,
                reaction_target_wamid=payload.target_message_id,
            )
        return SendReactionOutput(message_id=msg_id, status="pending")


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
    SendImage,
    SendAudio,
    SendVideo,
    SendDocument,
    SendLocation,
    SendReaction,
    ScheduleReminder,
    CancelScheduled,
)
