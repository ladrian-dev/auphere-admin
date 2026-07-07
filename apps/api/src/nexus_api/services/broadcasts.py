"""Broadcast fan-out service (ADR-028, Fase 1).

Turns one ``POST /v1/embed/broadcasts`` call into N pending ``messages``
rows that the existing outbound dispatcher drains. Everything runs
inside the caller's tenant-scoped transaction (RLS active), so nothing
here can touch another tenant.

Per-recipient pipeline:
  normalize E.164 → dedupe → opt-out pre-flight → upsert customer (the
  worker's own inbound helpers, so identifiers land in the exact format
  the webhook uses) → get-or-create open conversation → pending message
  with ``template_payload``.

Recipient phone formats — one subtlety, two columns:
  - ``Customer.identifier`` / opt-out ``recipient_phone`` store Meta's
    ``from`` format: digits WITHOUT ``+`` (that's what the inbound
    webhook writes, and both sides must match exactly or history forks).
  - ``broadcast_recipients.phone_e164`` stores the canonical ``+``-form
    for display and the partner-facing API.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

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
    Broadcast,
    BroadcastRecipient,
    BroadcastRecipientStatus,
    Channel,
    ChannelStatus,
    ChannelType,
    Message,
    MessageDirection,
    MessageStatus,
    WhatsAppOptOut,
)
from nexus_api.schemas.embed import (
    BroadcastAcceptedOut,
    BroadcastCreateIn,
    RejectedRecipientOut,
)
from nexus_api.services.whatsapp_templates import TemplateOut, fetch_templates

log = structlog.get_logger(__name__)

# E.164: + followed by 8-15 digits, first digit nonzero.
_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")

# Named template placeholders: {{cliente}}, {{ saldo_pendiente }} …
_NAMED_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
# Positional placeholders: {{1}}, {{2}} — unsupported in Fase 1.
_POSITIONAL_VAR_RE = re.compile(r"\{\{\s*\d+\s*\}\}")


@dataclass(frozen=True)
class _ResolvedTemplate:
    template: TemplateOut
    body_vars: frozenset[str]


def _template_body_vars(template: TemplateOut) -> frozenset[str]:
    for component in template.components:
        if str(component.get("type", "")).upper() == "BODY":
            return frozenset(_NAMED_VAR_RE.findall(str(component.get("text") or "")))
    return frozenset()


async def _resolve_template(
    session: AsyncSession, *, name: str, language: str
) -> _ResolvedTemplate:
    """Live lookup against Meta (source of truth). The modal listed
    templates through the same call moments earlier, so this also
    catches a template paused in between."""
    templates, _waba = await fetch_templates(session)
    match = next(
        (t for t in templates if t.name == name and t.language == language),
        None,
    )
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"template {name!r} ({language}) does not exist for this account",
        )
    if (match.status or "").upper() != "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"template {name!r} ({language}) is {match.status}, not APPROVED",
        )
    body_text = next(
        (
            str(c.get("text") or "")
            for c in match.components
            if str(c.get("type", "")).upper() == "BODY"
        ),
        "",
    )
    if _POSITIONAL_VAR_RE.search(body_text):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"template {name!r} uses positional parameters ({{{{1}}}}); "
                "broadcasts require named parameters"
            ),
        )
    return _ResolvedTemplate(template=match, body_vars=_template_body_vars(match))


async def _active_whatsapp_channel(session: AsyncSession) -> Channel:
    result = await session.execute(
        sa.select(Channel)
        .where(
            Channel.type == ChannelType.WHATSAPP,
            Channel.status == ChannelStatus.ACTIVE,
        )
        .limit(1)
    )
    channel = result.scalar_one_or_none()
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="whatsapp_not_connected",
        )
    return channel


async def _existing_broadcast(
    session: AsyncSession, *, tenant_id: uuid.UUID, idempotency_key: str
) -> BroadcastAcceptedOut | None:
    existing = (
        await session.execute(
            sa.select(Broadcast).where(Broadcast.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    if existing is None:
        return None
    rejected = (
        (
            await session.execute(
                sa.select(BroadcastRecipient).where(
                    BroadcastRecipient.broadcast_id == existing.id,
                    BroadcastRecipient.status == BroadcastRecipientStatus.REJECTED.value,
                )
            )
        )
        .scalars()
        .all()
    )
    return BroadcastAcceptedOut(
        broadcast_id=existing.id,
        accepted=existing.accepted_count,
        rejected=[
            RejectedRecipientOut(phone=r.phone_e164, reason=r.reject_reason or "rejected")
            for r in rejected
        ],
    )


async def create_broadcast(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    partner_id: uuid.UUID,
    recipient_cap: int,
    jti: str,
    payload: BroadcastCreateIn,
) -> tuple[BroadcastAcceptedOut, bool]:
    """Returns ``(result, created)`` — ``created=False`` on idempotent
    replay. Caller must hold the tenant-scoped transaction."""
    if len(payload.recipients) > recipient_cap:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"broadcast exceeds the recipient cap ({len(payload.recipients)} > "
                f"{recipient_cap}); split it or ask Auphere to raise the limit"
            ),
        )

    if payload.idempotency_key:
        replay = await _existing_broadcast(
            session, tenant_id=tenant_id, idempotency_key=payload.idempotency_key
        )
        if replay is not None:
            return replay, False

    channel = await _active_whatsapp_channel(session)
    resolved = await _resolve_template(
        session, name=payload.template_name, language=payload.language
    )

    broadcast = Broadcast(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        partner_id=partner_id,
        channel_id=channel.id,
        template_name=payload.template_name,
        template_language=payload.language,
        total=len(payload.recipients),
        idempotency_key=payload.idempotency_key,
        jti=jti,
    )
    session.add(broadcast)
    await session.flush()

    accepted = 0
    rejected: list[RejectedRecipientOut] = []
    seen: set[str] = set()

    def _reject(reason: str, *, phone: str, variables: dict[str, str]) -> None:
        rejected.append(RejectedRecipientOut(phone=phone, reason=reason))
        session.add(
            BroadcastRecipient(
                tenant_id=tenant_id,
                broadcast_id=broadcast.id,
                phone_e164=phone,
                params=variables,
                status=BroadcastRecipientStatus.REJECTED.value,
                reject_reason=reason,
            )
        )

    for recipient in payload.recipients:
        e164 = to_e164(recipient.phone)
        display_phone = e164 or recipient.phone[:20]

        if e164 is None or not _E164_RE.match(e164):
            _reject("invalid_phone", phone=display_phone, variables=recipient.variables)
            continue
        if e164 in seen:
            # Payload artifact, not a real recipient — report it in the
            # response but skip the DB row (phone is UNIQUE per broadcast).
            rejected.append(RejectedRecipientOut(phone=e164, reason="duplicate"))
            continue
        seen.add(e164)

        missing = resolved.body_vars - set(recipient.variables)
        if missing:
            _reject(
                f"missing_variables:{','.join(sorted(missing))}",
                phone=e164,
                variables=recipient.variables,
            )
            continue

        # Meta's ``from`` format — MUST match what the inbound webhook
        # stores or customers/opt-outs fork per format.
        wa_identifier = e164.removeprefix("+")

        opted_out = await session.scalar(
            sa.select(WhatsAppOptOut.id).where(
                WhatsAppOptOut.channel_id == channel.id,
                WhatsAppOptOut.recipient_phone == wa_identifier,
                WhatsAppOptOut.opted_in_at.is_(None),
            )
        )
        if opted_out is not None:
            _reject("opted_out", phone=e164, variables=recipient.variables)
            continue

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
            template_payload={
                "name": payload.template_name,
                "language": payload.language,
                "params": {"body": dict(recipient.variables)},
            },
        )
        session.add(message)
        await session.flush()
        session.add(
            BroadcastRecipient(
                tenant_id=tenant_id,
                broadcast_id=broadcast.id,
                phone_e164=e164,
                params=recipient.variables,
                status=BroadcastRecipientStatus.QUEUED.value,
                message_id=message.id,
            )
        )
        accepted += 1

    broadcast.accepted_count = accepted
    broadcast.rejected_count = len(rejected)
    await session.flush()
    log.info(
        "broadcast.accepted",
        tenant_id=str(tenant_id),
        partner_id=str(partner_id),
        broadcast_id=str(broadcast.id),
        accepted=accepted,
        rejected=len(rejected),
    )
    return (
        BroadcastAcceptedOut(broadcast_id=broadcast.id, accepted=accepted, rejected=rejected),
        True,
    )
