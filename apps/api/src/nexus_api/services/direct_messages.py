"""Single-recipient template send for the ``/v1/messages`` surface.

The per-recipient pipeline is the same one ``services/broadcasts`` runs
N times, and it deliberately reuses that module's helpers rather than
reimplementing them: channel lookup, live template resolution against
Meta, and E.164 normalisation. Two copies of "which template is this
and is it approved" would drift, and the drift would only show up as a
message that silently fails to send.

What differs is the error contract, and it is not a detail. A broadcast
collects rejections into a list because 999 good recipients should not
be lost to one bad phone number. A single send has no such trade-off:
if the phone is malformed or the customer opted out, the caller needs a
4xx it can branch on, not a 202 with an empty result buried inside.

Everything runs inside the caller's tenant-scoped transaction (RLS
active), so this cannot reach another tenant's channel or customers.

Observability
-------------
Every branch of this function emits one ``direct_message.*`` event with
the same identifying keys (``tenant_id``, ``idempotency_key``,
``template``, ``to_masked``), so a campaign run can be reconstructed
from the log alone: which calls queued, which replayed, which were
rejected and why. The recipient is masked — a campaign log is not a
place to accumulate a customer phone list in clear text.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
import structlog
from fastapi import HTTPException, status
from nexus_channels.whatsapp_meta.phone import to_e164
from nexus_worker.persistence.messages import (
    upsert_conversation_for_customer,
    upsert_customer,
)
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    Message,
    MessageDirection,
    MessageStatus,
    WhatsAppOptOut,
)
from nexus_api.schemas.messages import TemplateMessageAcceptedOut, TemplateMessageIn
from nexus_api.services.broadcasts import (
    E164_RE,
    active_whatsapp_channel,
    resolve_template,
)

log = structlog.get_logger(__name__)


def mask_phone(raw: str | None) -> str:
    """``+56912345678`` → ``+5691***5678``.

    Enough to correlate a log line with a spreadsheet row, not enough to
    turn the log into a contact list.
    """
    if not raw:
        return ""
    if len(raw) <= 8:
        return f"{raw[:2]}***"
    return f"{raw[:5]}***{raw[-4:]}"


async def _replayed_message(session: AsyncSession, *, idempotency_key: str) -> Message | None:
    """Prior send with this key, if any.

    No explicit tenant filter: RLS scopes the query, and the unique
    index is ``(tenant_id, idempotency_key)`` — another tenant's row
    with the same key is invisible here.
    """
    return await session.scalar(
        sa.select(Message).where(Message.idempotency_key == idempotency_key).limit(1)
    )


def _log_key_collision(
    replay: Message,
    payload: TemplateMessageIn,
    *,
    tenant_id: uuid.UUID,
) -> bool:
    """Warn when the key matches but the *message* does not.

    An idempotency key is a promise that the same key means the same
    message. Callers derive it from spreadsheet data (``tipo-telefono-
    fecha``), and two different rows that happen to share those fields
    collide: the second send is swallowed and answered ``duplicate=true``
    even though that customer never received anything for it.

    That failure is invisible from the response — it looks exactly like
    a legitimate retry — so it has to be visible here. Returns whether a
    collision was detected, for the caller's response log.
    """
    prior_template = (replay.template_payload or {}).get("name")
    prior_language = (replay.template_payload or {}).get("language")
    prior_vars = ((replay.template_payload or {}).get("params") or {}).get("body") or {}
    template_differs = prior_template != payload.template_name or (
        prior_language is not None and prior_language != payload.language
    )
    vars_differ = dict(prior_vars) != dict(payload.variables)
    if not (template_differs or vars_differ):
        return False
    log.warning(
        "direct_message.idempotency_collision",
        tenant_id=str(tenant_id),
        idempotency_key=payload.idempotency_key,
        message_id=str(replay.id),
        prior_template=prior_template,
        prior_language=prior_language,
        prior_variables=sorted(prior_vars) if isinstance(prior_vars, dict) else None,
        requested_template=payload.template_name,
        requested_language=payload.language,
        requested_variables=sorted(payload.variables),
        template_differs=template_differs,
        variables_differ=vars_differ,
        hint=(
            "same idempotency_key, different message — the caller's key is not "
            "unique per row (add the source row id to it). This send was dropped."
        ),
    )
    return True


async def send_template_message(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    payload: TemplateMessageIn,
) -> TemplateMessageAcceptedOut:
    """Queue one template message. Caller holds the tenant-scoped transaction.

    Returns as soon as the row is committed as ``pending`` — the
    outbound dispatcher picks it up and talks to Meta. That is the point
    of 202: retries, backoff, reauth and rate limiting already live in
    the dispatcher, and duplicating them behind a synchronous call would
    mean two paths to keep correct.
    """
    to_masked = mask_phone(payload.to)
    log.info(
        "direct_message.received",
        tenant_id=str(tenant_id),
        template=payload.template_name,
        language=payload.language,
        to_masked=to_masked,
        variables=sorted(payload.variables),
        idempotency_key=payload.idempotency_key,
        has_idempotency_key=payload.idempotency_key is not None,
    )

    revive: Message | None = None
    if payload.idempotency_key:
        replay = await _replayed_message(session, idempotency_key=payload.idempotency_key)
        if replay is not None:
            collided = _log_key_collision(replay, payload, tenant_id=tenant_id)
            if replay.status is MessageStatus.FAILED:
                # A terminal failure answered ``duplicate=true`` is the
                # worst of both worlds: the caller is told the message is
                # handled, and nothing is queued — so the recipient never
                # hears from us and the automation marks the row as sent.
                # An explicit retry with the same key is a request to try
                # again, so we re-drive the SAME row (the unique index
                # forbids a second one) after re-running every validation
                # below. ``revive`` carries it to the end of the pipeline.
                revive = replay
                log.warning(
                    "direct_message.replay_of_failed_send",
                    tenant_id=str(tenant_id),
                    message_id=str(replay.id),
                    idempotency_key=payload.idempotency_key,
                    prior_status=replay.status.value,
                    prior_failure_code=replay.failure_code,
                    prior_attempts=replay.attempts,
                    prior_error=replay.last_error,
                    to_masked=to_masked,
                    action="requeue_same_row",
                )
            else:
                log.info(
                    "direct_message.replay",
                    tenant_id=str(tenant_id),
                    message_id=str(replay.id),
                    idempotency_key=payload.idempotency_key,
                    prior_status=replay.status.value,
                    prior_created_at=replay.created_at.isoformat() if replay.created_at else None,
                    prior_provider_message_id=replay.provider_message_id,
                    to_masked=to_masked,
                    key_collision=collided,
                    outcome="duplicate",
                )
                return TemplateMessageAcceptedOut(
                    message_id=replay.id,
                    status=replay.status.value,
                    to=payload.to,
                    duplicate=True,
                )

    e164 = to_e164(payload.to)
    if e164 is None or not E164_RE.match(e164):
        log.warning(
            "direct_message.rejected",
            tenant_id=str(tenant_id),
            reason="invalid_phone",
            to_masked=to_masked,
            normalised=mask_phone(e164),
            idempotency_key=payload.idempotency_key,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"invalid_phone: {payload.to!r} is not a valid phone number — "
                "expected E.164 with country code, e.g. +56912345678"
            ),
        )

    channel = await active_whatsapp_channel(session)
    log.info(
        "direct_message.channel_resolved",
        tenant_id=str(tenant_id),
        channel_id=str(channel.id),
        provider=channel.provider,
        provider_identifier=channel.provider_identifier,
        channel_status=channel.status.value,
    )
    resolved = await resolve_template(
        session, name=payload.template_name, language=payload.language
    )
    log.info(
        "direct_message.template_resolved",
        tenant_id=str(tenant_id),
        template=payload.template_name,
        language=payload.language,
        template_status=resolved.template.status,
        category=resolved.template.category,
        body_vars=sorted(resolved.body_vars),
    )

    missing = resolved.body_vars - set(payload.variables)
    if missing:
        log.warning(
            "direct_message.rejected",
            tenant_id=str(tenant_id),
            reason="missing_variables",
            template=payload.template_name,
            missing=sorted(missing),
            provided=sorted(payload.variables),
            idempotency_key=payload.idempotency_key,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"missing_variables: template {payload.template_name!r} requires "
                f"{', '.join(sorted(missing))}"
            ),
        )
    # Extra variables are a silent no-op in a broadcast. Here they almost
    # always mean a typo in the caller's mapping ({{nombre}} vs "name"),
    # and a message that sends with an unfilled placeholder is worse than
    # one that fails loudly.
    unexpected = set(payload.variables) - resolved.body_vars
    if unexpected:
        log.warning(
            "direct_message.rejected",
            tenant_id=str(tenant_id),
            reason="unexpected_variables",
            template=payload.template_name,
            unexpected=sorted(unexpected),
            expected=sorted(resolved.body_vars),
            idempotency_key=payload.idempotency_key,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"unexpected_variables: template {payload.template_name!r} does not "
                f"use {', '.join(sorted(unexpected))} — it expects "
                f"{', '.join(sorted(resolved.body_vars)) or 'no variables'}"
            ),
        )

    # Meta's ``from`` format — MUST match what the inbound webhook stores
    # or customers and opt-outs fork per format.
    wa_identifier = e164.removeprefix("+")

    opted_out = await session.scalar(
        sa.select(WhatsAppOptOut.id).where(
            WhatsAppOptOut.channel_id == channel.id,
            WhatsAppOptOut.recipient_phone == wa_identifier,
            WhatsAppOptOut.opted_in_at.is_(None),
        )
    )
    if opted_out is not None:
        log.warning(
            "direct_message.rejected",
            tenant_id=str(tenant_id),
            reason="opted_out",
            channel_id=str(channel.id),
            to_masked=to_masked,
            idempotency_key=payload.idempotency_key,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"opted_out: {e164} has opted out of messages from this number",
        )

    customer = await upsert_customer(session, identifier=wa_identifier)
    conversation = await upsert_conversation_for_customer(
        session, channel_id=channel.id, customer_id=customer.id
    )
    template_payload = {
        "name": payload.template_name,
        "language": payload.language,
        "params": {"body": dict(payload.variables)},
    }

    if revive is not None:
        # Same row, reset to pending. ``attempts`` goes back to zero so the
        # dispatcher gives this send its full retry budget rather than
        # inheriting an exhausted one from the previous run.
        revive.status = MessageStatus.PENDING
        revive.conversation_id = conversation.id
        revive.template_payload = template_payload
        revive.content = f"[template:{payload.template_name}]"
        revive.attempts = 0
        revive.failed_at = None
        revive.failure_code = None
        revive.last_error = None
        # ``created_at`` is deliberately left alone: it is the row's
        # identity for the operator panel and for the dispatcher's
        # oldest-first ordering, which puts a re-driven send at the front
        # of the queue — where a retry belongs.
        await session.flush()
        log.info(
            "direct_message.requeued",
            tenant_id=str(tenant_id),
            message_id=str(revive.id),
            conversation_id=str(conversation.id),
            channel_id=str(channel.id),
            customer_id=str(customer.id),
            template=payload.template_name,
            to_masked=to_masked,
            idempotency_key=payload.idempotency_key,
            outcome="requeued",
        )
        return TemplateMessageAcceptedOut(
            message_id=revive.id,
            status=MessageStatus.PENDING.value,
            to=e164,
        )

    message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.PENDING,
        content=f"[template:{payload.template_name}]",
        tool_calls=[],
        actor_kind="system",
        idempotency_key=payload.idempotency_key,
        template_payload=template_payload,
    )
    session.add(message)
    await session.flush()

    log.info(
        "direct_message.queued",
        tenant_id=str(tenant_id),
        message_id=str(message.id),
        conversation_id=str(conversation.id),
        channel_id=str(channel.id),
        customer_id=str(customer.id),
        template=payload.template_name,
        language=payload.language,
        to_masked=to_masked,
        idempotency_key=payload.idempotency_key,
        outcome="queued",
    )
    return TemplateMessageAcceptedOut(
        message_id=message.id,
        status=MessageStatus.PENDING.value,
        to=e164,
    )
