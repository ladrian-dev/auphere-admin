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


async def _replayed_message(session: AsyncSession, *, idempotency_key: str) -> Message | None:
    """Prior send with this key, if any.

    No explicit tenant filter: RLS scopes the query, and the unique
    index is ``(tenant_id, idempotency_key)`` — another tenant's row
    with the same key is invisible here.
    """
    return await session.scalar(
        sa.select(Message).where(Message.idempotency_key == idempotency_key).limit(1)
    )


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
    if payload.idempotency_key:
        replay = await _replayed_message(session, idempotency_key=payload.idempotency_key)
        if replay is not None:
            log.info(
                "direct_message.replay",
                tenant_id=str(tenant_id),
                message_id=str(replay.id),
                idempotency_key=payload.idempotency_key,
            )
            return TemplateMessageAcceptedOut(
                message_id=replay.id,
                status=replay.status.value,
                to=payload.to,
                duplicate=True,
            )

    e164 = to_e164(payload.to)
    if e164 is None or not E164_RE.match(e164):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"invalid_phone: {payload.to!r} is not a valid phone number — "
                "expected E.164 with country code, e.g. +56912345678"
            ),
        )

    channel = await active_whatsapp_channel(session)
    resolved = await resolve_template(
        session, name=payload.template_name, language=payload.language
    )

    missing = resolved.body_vars - set(payload.variables)
    if missing:
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"opted_out: {e164} has opted out of messages from this number",
        )

    customer = await upsert_customer(session, identifier=wa_identifier)
    conversation = await upsert_conversation_for_customer(
        session, channel_id=channel.id, customer_id=customer.id
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
        template_payload={
            "name": payload.template_name,
            "language": payload.language,
            "params": {"body": dict(payload.variables)},
        },
    )
    session.add(message)
    await session.flush()

    log.info(
        "direct_message.queued",
        tenant_id=str(tenant_id),
        message_id=str(message.id),
        template=payload.template_name,
    )
    return TemplateMessageAcceptedOut(
        message_id=message.id,
        status=MessageStatus.PENDING.value,
        to=e164,
    )
