"""YCloud webhook endpoint for the Auphere ↔ Owner backchannel.

This endpoint receives WhatsApp messages addressed to the **Auphere
multi-tenant owner number** (``settings.auphere_owner_phone``), NOT to
any tenant's business number. Inbound flow (spec §5):

1. Verify the signature (separate secret from the tenant webhooks so
   the BSP can rotate one without affecting the other).
2. Confirm the ``to`` field matches our owner number — anything else
   means the BSP routed by mistake, return 204.
3. Look the ``from`` phone up in ``owner_phone_index`` (RLS-free; the
   table exists for exactly this discovery step).
4. With a tenant in hand, switch the session into the tenant's RLS
   scope and route the message:
   a) Try to match an open consultation via the correlation_id in the
      message text (``(ref XYZ12345)``); fall back to the most-recent
      open consultation if there is exactly one.
   b) Parse the message (free_text / yes / no — Phase 1).
   c) Update the consultation row to ``status='answered'`` and enqueue
      a fanout event so the worker re-enters the pipeline with the
      owner's response as a system addendum.

Phase 1 deliberately keeps the "reply back to the owner" surface minimal:
- Unknown sender → log + 204.
- No open consultation → log + 204 (the owner sees no reply; Phase 2
  adds an admin reply).
- Multiple open consultations and the owner didn't cite a ref → log +
  204 (Phase 2 replies asking the owner to cite the ref).
- Slash command → log + 204 (Phase 2 implements them).
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from nexus_channels.whatsapp_ycloud.signature import (
    YCloudSignatureError,
    verify_ycloud_signature,
)
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.config import get_settings
from nexus_api.core.logging_context import bind_tenant
from nexus_api.core.tenant_context import apply_tenant_to_session
from nexus_api.db.models import OwnerConsultation, OwnerPhoneIndex
from nexus_api.services.owner_command_parser import (
    parse_owner_message,
)

router = APIRouter()
log = structlog.get_logger()


OWNER_FANOUT_STREAM = "nexus:owner_fanout"

# ``(ref XYZ12345)``, ``ref:XYZ12345``, ``[ref XYZ12345]`` — owner can quote
# the ref however they like as long as the 8-char token is present.
_CORRELATION_RE = re.compile(r"ref\s*[:\-]?\s*([A-Za-z0-9_-]{6,12})", re.IGNORECASE)


def _normalize_e164(phone: str) -> str:
    """Strip whitespace; keep the leading ``+`` if present. YCloud sends
    phones in E.164 already so this is mostly defensive."""
    return phone.strip()


def _mask_phone(phone: str) -> str:
    if len(phone) <= 6:
        return "***"
    return phone[:3] + "***" + phone[-3:]


@router.post("/ycloud/owner-channel", status_code=status.HTTP_200_OK)
async def auphere_owner_inbound(
    request: Request,
    ycloud_signature: str | None = Header(default=None, alias="YCloud-Signature"),
    x_ycloud_signature: str | None = Header(default=None, alias="X-YCloud-Signature"),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> dict[str, str]:
    body = await request.body()
    settings = get_settings()

    if not settings.auphere_owner_phone:
        # Feature off in this environment — accept and ignore so the BSP
        # webhook validation succeeds.
        log.info("owner_channel.disabled.no_phone_configured")
        return {"status": "ignored:disabled"}

    secret = settings.auphere_owner_webhook_secret or settings.ycloud_webhook_secret
    sig_header = ycloud_signature or x_ycloud_signature
    try:
        verify_ycloud_signature(
            secret,
            body,
            sig_header or "",
            tolerance_seconds=settings.ycloud_signature_tolerance_seconds,
        )
    except YCloudSignatureError as exc:
        log.warning("owner_channel.signature_failed", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature"
        ) from exc

    try:
        payload: dict[str, Any] = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid JSON") from exc

    event_type = payload.get("type")
    if event_type != "whatsapp.inbound_message.received":
        log.info("owner_channel.non_inbound_event", type=event_type)
        return {"status": "ignored:non_inbound"}

    msg = payload.get("whatsappInboundMessage") or {}
    if not isinstance(msg, dict):
        return {"status": "ignored:malformed"}

    to_phone = msg.get("to")
    from_phone = msg.get("from")
    text = (msg.get("text") or {}).get("body") if isinstance(msg.get("text"), dict) else None

    if not isinstance(to_phone, str) or not isinstance(from_phone, str):
        return {"status": "ignored:missing_addresses"}

    if to_phone != settings.auphere_owner_phone:
        # Not for the backchannel — the BSP also delivers tenant business
        # number events here when both share an endpoint config. Quietly
        # ignore; the regular ``/webhooks/ycloud`` route handles them.
        log.info(
            "owner_channel.foreign_to_number",
            to=_mask_phone(to_phone),
        )
        return {"status": "ignored:wrong_destination"}

    if not isinstance(text, str) or not text.strip():
        # Audio / image / sticker — Phase 1 doesn't transcribe. Log and
        # leave the consultation open so the owner has a chance to retry
        # with text.
        log.info(
            "owner_channel.non_text_message",
            from_phone=_mask_phone(from_phone),
        )
        return {"status": "ignored:non_text"}

    sender = _normalize_e164(from_phone)
    idx = await session.get(OwnerPhoneIndex, sender)
    if idx is None:
        log.warning(
            "owner_channel.unknown_phone",
            phone=_mask_phone(sender),
        )
        return {"status": "ignored:unknown_phone"}
    if not idx.active:
        log.info(
            "owner_channel.inactive_phone",
            phone=_mask_phone(sender),
        )
        return {"status": "ignored:inactive_phone"}

    tenant_id: uuid.UUID = idx.tenant_id
    bind_tenant(tenant_id)

    if session.in_transaction():
        await session.rollback()

    parsed = parse_owner_message(text)
    if parsed.kind == "empty":
        return {"status": "ignored:empty"}
    if parsed.kind == "unknown_command":
        # Phase 2 implements slash commands. For Phase 1 we surface them
        # via logs so the operator can spot owners trying to use them.
        log.info(
            "owner_channel.unknown_command",
            tenant_id=str(tenant_id),
            verb=parsed.slash_verb,
        )
        return {"status": "ignored:slash_unsupported"}

    async with session.begin():
        await apply_tenant_to_session(session, tenant_id)
        consultation = await _resolve_open_consultation(session, parsed.free_text)
        if consultation is None:
            log.info(
                "owner_channel.no_matching_consultation",
                tenant_id=str(tenant_id),
                phone=_mask_phone(sender),
            )
            return {"status": "ignored:no_open_consultation"}

        consultation.owner_response_text = parsed.free_text
        consultation.owner_response_at = datetime.now(UTC)
        consultation.owner_command_kind = parsed.kind
        consultation.status = "answered"
        consultation_id = consultation.id

    # Outside the transaction — enqueue the fanout. Stream entries
    # survive a Redis restart only via AOF/RDB; the underlying row in
    # ``owner_consultations`` already has ``status='answered'`` so a
    # cron sweep can re-enqueue if the entry is lost. Phase 1 ships
    # without that sweep but the data model supports it.
    await redis.xadd(
        OWNER_FANOUT_STREAM,
        {
            "tenant_id": str(tenant_id),
            "consultation_id": str(consultation_id),
        },
    )

    log.info(
        "owner_channel.answered",
        tenant_id=str(tenant_id),
        consultation_id=str(consultation_id),
        command_kind=parsed.kind,
    )
    return {"status": "queued_for_fanout"}


async def _resolve_open_consultation(session: AsyncSession, text: str) -> OwnerConsultation | None:
    """Try (in order): correlation_id in text, then the most-recent open
    consultation if there is exactly one. Returns None if the lookup is
    ambiguous (>1 open and no ref) — the caller logs + 204."""
    m = _CORRELATION_RE.search(text)
    if m:
        correlation_id = m.group(1)
        row = await session.execute(
            select(OwnerConsultation).where(
                OwnerConsultation.correlation_id == correlation_id,
                OwnerConsultation.status.in_(("pending", "sent")),
            )
        )
        candidate = row.scalar_one_or_none()
        if candidate is not None:
            return candidate
        # ref present but didn't match — fall through to the "single open"
        # heuristic, but only if the owner just got the ref wrong (typo).

    open_rows = await session.execute(
        select(OwnerConsultation)
        .where(OwnerConsultation.status.in_(("pending", "sent")))
        .order_by(OwnerConsultation.asked_at.desc())
        .limit(2)
    )
    candidates = list(open_rows.scalars())
    if len(candidates) == 1:
        return candidates[0]
    # 0 or >1 → ambiguous; refuse to guess.
    return None
