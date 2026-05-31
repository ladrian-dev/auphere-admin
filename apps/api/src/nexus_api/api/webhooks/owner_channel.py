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
from nexus_channels.whatsapp_ycloud.adapter import WhatsAppYCloudAdapter
from nexus_channels.whatsapp_ycloud.ycloud_client import YCloudClient
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
from nexus_api.db.models import (
    Conversation,
    OwnerConsultation,
    OwnerPhoneIndex,
    Tenant,
    TenantStatus,
)
from nexus_api.repositories.auphere_channels import resolve_channel_for_inbound
from nexus_api.services.owner_command_parser import (
    ParsedOwnerMessage,
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


# ── Phase 2 — slash-command vocabulary surfaced to the owner ────────────

_HELP_TEXT = (
    "Comandos disponibles:\n"
    "/yes — confirmar la consulta abierta\n"
    "/no — rechazar la consulta abierta\n"
    "/done — marcar la consulta como resuelta (ya respondiste fuera de WhatsApp)\n"
    "/handoff — tomar control de la conversación con el cliente (agente queda silenciado)\n"
    "/pause — pausar todos los agentes de tu negocio\n"
    "/help — mostrar este mensaje"
)

_NO_OPEN_CONSULTATION_TEXT = (
    "No tienes ninguna consulta abierta de tu agente ahora mismo.\n\n"
    "Si quieres pausar al agente o tomar control de una conversación, "
    "puedes hacerlo desde el panel de administración. Escribe /help para "
    "ver los comandos disponibles."
)

# Phase 2 TOFU — Trust On First Use. When the admin registers an owner
# phone, we wait for an explicit ``/yes`` from that phone before
# unlocking the full surface. Until then we only reply with these
# instructions.
_TOFU_WELCOME_TEXT = (
    "Hola, soy Auphere 👋\n\n"
    "Tu número fue registrado como dueño/encargado de este negocio. "
    "Antes de empezar a recibir consultas del agente, necesito que "
    "confirmes que eres tú.\n\n"
    "Responde /yes para activar tu canal."
)

_TOFU_CONFIRMED_TEXT = (
    "Confirmado ✅ tu canal está activo.\n\n"
    "Cuando el agente necesite tu input te escribiré por aquí. "
    "Escribe /help para ver los comandos disponibles."
)


def _build_ycloud_adapter() -> WhatsAppYCloudAdapter:
    """Construct a YCloud adapter for sending free-form text replies to
    the owner. Override target for tests via
    ``app.dependency_overrides``."""
    settings = get_settings()
    client = YCloudClient(
        api_key=settings.ycloud_api_key,
        base_url=settings.ycloud_api_base_url,
    )
    return WhatsAppYCloudAdapter(client)


async def _send_owner_reply(
    *,
    from_phone: str,
    to_phone: str,
    text: str,
    tenant_id: uuid.UUID | None = None,
) -> None:
    """Best-effort free-form reply to the owner over WhatsApp.

    Used for slash-command acknowledgements, the "no open consultation"
    notice, and the TOFU welcome. Failures are non-fatal: we never want
    the webhook to 5xx because the reply failed — the BSP retries
    inbounds aggressively and a 5xx would re-deliver the same message.
    """
    adapter = _build_ycloud_adapter()
    try:
        await adapter.send_text(
            from_phone=from_phone,
            recipient=to_phone,
            text=text,
            tenant_id=tenant_id or uuid.UUID(int=0),
            channel_id=uuid.UUID(int=0),  # backchannel — no per-tenant channel row
        )
    except Exception as exc:
        log.warning(
            "owner_channel.reply_failed",
            to=_mask_phone(to_phone),
            error=str(exc)[:200],
        )


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

    # Parse the payload BEFORE verifying the signature — we need the
    # ``to`` field to pick the right channel (each channel may carry
    # its own webhook secret). Signature verification still happens
    # against the raw body bytes a few lines down.
    try:
        payload: dict[str, Any] = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid JSON"
        ) from exc

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

    # Resolve which Auphere channel this message is FOR. Multi-number
    # support (migration 0038): the operator can register CL/AR/MX/ES
    # numbers in the DB; we look up the row that matches ``to_phone``.
    # When the DB is empty AND ``settings.auphere_owner_phone`` matches,
    # we fall back to the legacy single-number behaviour so Phase 1
    # keeps working.
    channel = await resolve_channel_for_inbound(session, to_phone=to_phone)
    if channel is None:
        # Either the registry is empty + settings doesn't match, or the
        # ``to`` doesn't belong to any active channel. Quietly ignore so
        # the BSP webhook validation still succeeds.
        log.info(
            "owner_channel.foreign_to_number",
            to=_mask_phone(to_phone),
        )
        return {"status": "ignored:wrong_destination"}

    # Per-channel secret beats the shared one. NULL on the channel row
    # OR a legacy-fallback resolution → use the shared YCloud secret.
    secret = (
        channel.webhook_secret
        or settings.auphere_owner_webhook_secret
        or settings.ycloud_webhook_secret
    )
    sig_header = ycloud_signature or x_ycloud_signature
    try:
        verify_ycloud_signature(
            secret,
            body,
            sig_header or "",
            tolerance_seconds=settings.ycloud_signature_tolerance_seconds,
        )
    except YCloudSignatureError as exc:
        log.warning(
            "owner_channel.signature_failed",
            reason=str(exc),
            channel=channel.display_name,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature"
        ) from exc

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
    is_confirmed = idx.confirmed_at is not None
    bind_tenant(tenant_id)

    if session.in_transaction():
        await session.rollback()

    parsed = parse_owner_message(text)
    if parsed.kind == "empty":
        return {"status": "ignored:empty"}

    # Phase 2 TOFU — refuse to drive consultations / slash side effects
    # until the owner has confirmed they're the right person on this
    # number. The admin registers the phone in the panel; the first
    # ``/yes`` from that phone stamps ``confirmed_at`` and unlocks the
    # rest of the surface. Existing Phase 1 owners were backfilled by
    # migration 0043 so they bypass this check.
    if not is_confirmed:
        if parsed.kind == "yes":
            # Re-fetch under a fresh transaction so the UPDATE rides
            # the session's normal autocommit boundary instead of
            # stamping a stale, expired-after-rollback identity.
            async with session.begin():
                idx_fresh = await session.get(OwnerPhoneIndex, sender)
                if idx_fresh is not None:
                    idx_fresh.confirmed_at = datetime.now(UTC)
            await _send_owner_reply(
                from_phone=channel.phone_e164,
                to_phone=sender,
                text=_TOFU_CONFIRMED_TEXT,
                tenant_id=tenant_id,
            )
            log.info(
                "owner_channel.tofu_confirmed",
                tenant_id=str(tenant_id),
                phone=_mask_phone(sender),
            )
            return {"status": "tofu_confirmed"}

        await _send_owner_reply(
            from_phone=channel.phone_e164,
            to_phone=sender,
            text=_TOFU_WELCOME_TEXT,
            tenant_id=tenant_id,
        )
        log.info(
            "owner_channel.tofu_pending",
            tenant_id=str(tenant_id),
            phone=_mask_phone(sender),
            command_kind=parsed.kind,
        )
        return {"status": "tofu_pending"}

    # /help is special — never touches a consultation, always replies.
    if parsed.kind == "help":
        await _send_owner_reply(
            from_phone=channel.phone_e164,
            to_phone=sender,
            text=_HELP_TEXT,
            tenant_id=tenant_id,
        )
        log.info("owner_channel.help_sent", tenant_id=str(tenant_id))
        return {"status": "help_sent"}

    # Unknown slash verb — reply with help so the owner learns the
    # vocabulary instead of having their message silently swallowed.
    if parsed.kind == "unknown_command":
        await _send_owner_reply(
            from_phone=channel.phone_e164,
            to_phone=sender,
            text=(
                f"No reconozco el comando /{parsed.slash_verb}.\n\n{_HELP_TEXT}"
            ),
            tenant_id=tenant_id,
        )
        log.info(
            "owner_channel.unknown_command",
            tenant_id=str(tenant_id),
            verb=parsed.slash_verb,
        )
        return {"status": "unknown_command_replied"}

    # Everything else (free_text / yes / no / done / handoff / pause)
    # requires an open consultation. Look it up under the tenant scope.
    async with session.begin():
        await apply_tenant_to_session(session, tenant_id)
        consultation = await _resolve_open_consultation(session, parsed.free_text)
        if consultation is None:
            # Phase 2 — reply explaining instead of dropping silently.
            # Two cases:
            # (a) the owner sent free text out of the blue ("hola che");
            # (b) the owner sent a slash command but we have no open
            #     consultation to apply it to (handoff/pause/yes/no/done).
            #
            # Both deserve the same answer: "no abierta + cómo seguir".
            # /handoff and /pause are the exception — they don't NEED a
            # consultation to be useful, but the side effects (toggle
            # agent_active on a specific conversation, pause the whole
            # tenant) need scope that only an open consultation provides.
            # The owner can still pause from the admin panel.
            log.info(
                "owner_channel.no_matching_consultation",
                tenant_id=str(tenant_id),
                phone=_mask_phone(sender),
                command_kind=parsed.kind,
            )
            await _send_owner_reply(
                from_phone=channel.phone_e164,
                to_phone=sender,
                text=_NO_OPEN_CONSULTATION_TEXT,
                tenant_id=tenant_id,
            )
            return {"status": "no_open_consultation_replied"}

        consultation.owner_response_text = parsed.free_text
        consultation.owner_response_at = datetime.now(UTC)
        consultation.owner_command_kind = parsed.kind
        consultation.status = "answered"
        consultation_id = consultation.id
        conv_id_for_handoff = consultation.conversation_id

        # Phase 2 — slash-command side effects on the tenant world.
        side_effect = await _apply_slash_side_effect(
            session,
            tenant_id=tenant_id,
            parsed=parsed,
            conversation_id=conv_id_for_handoff,
        )

    # Outside the transaction — enqueue the fanout. Stream entries
    # survive a Redis restart only via AOF/RDB; the underlying row in
    # ``owner_consultations`` already has ``status='answered'`` so the
    # PR-P2-4 sweep cron re-enqueues if the entry is lost.
    await redis.xadd(
        OWNER_FANOUT_STREAM,
        {
            "tenant_id": str(tenant_id),
            "consultation_id": str(consultation_id),
        },
    )

    # Ack the owner with a short confirmation describing what happened.
    ack_text = _ack_text_for(parsed, side_effect)
    if ack_text:
        await _send_owner_reply(
            from_phone=channel.phone_e164,
            to_phone=sender,
            text=ack_text,
            tenant_id=tenant_id,
        )

    log.info(
        "owner_channel.answered",
        tenant_id=str(tenant_id),
        consultation_id=str(consultation_id),
        command_kind=parsed.kind,
        side_effect=side_effect,
    )
    return {
        "status": "queued_for_fanout",
        "side_effect": side_effect or "none",
    }


async def _apply_slash_side_effect(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    parsed: ParsedOwnerMessage,
    conversation_id: uuid.UUID,
) -> str | None:
    """Apply the tenant-world side effect of a slash command.

    Called inside the tenant-scoped transaction so the writes share the
    same commit boundary as the consultation update. Returns a short
    label for logging / ack messages.

    - ``handoff`` → set ``conversations.agent_active=false`` on the
      conversation the consultation belongs to. The dispatcher already
      respects this flag and stops invoking the pipeline on new
      inbounds.
    - ``pause`` → set ``tenants.status=paused``. The dispatcher refuses
      ALL inbounds for the tenant. Reversible: the operator clicks
      "Resume" in the admin panel.
    - ``yes`` / ``no`` / ``done`` / ``free_text`` → no side effect; the
      consultation row carries the verdict and the pipeline picks it up
      on fanout.
    """
    if parsed.kind == "handoff":
        conv = await session.get(Conversation, conversation_id)
        if conv is not None and conv.agent_active:
            conv.agent_active = False
            conv.agent_active_version = (conv.agent_active_version or 0) + 1
            conv.takeover_context = {
                "reason": "owner /handoff",
                "notes": parsed.slash_arg or None,
                "started_at": datetime.now(UTC).isoformat(),
                "operator_id": "owner:backchannel",
            }
        return "handoff_applied"
    if parsed.kind == "pause":
        # Tenant table is global (no RLS) but writing while in a
        # tenant-scoped session is fine — the row lookup goes through
        # the primary key.
        tenant = await session.get(Tenant, tenant_id)
        if tenant is not None and tenant.status != TenantStatus.PAUSED:
            tenant.status = TenantStatus.PAUSED
        return "tenant_paused"
    return None


def _ack_text_for(parsed: ParsedOwnerMessage, side_effect: str | None) -> str:
    """Build the WhatsApp ack message the owner sees after each slash
    command (or natural yes/no). Keep it terse — the owner doesn't want
    a paragraph back, just confirmation.
    """
    if parsed.kind == "yes":
        return "Recibido ✅ marqué la consulta como confirmada."
    if parsed.kind == "no":
        return "Recibido ❌ marqué la consulta como rechazada."
    if parsed.kind == "done":
        return "Marqué la consulta como resuelta. Gracias."
    if parsed.kind == "handoff":
        return (
            "Tomaste control de la conversación con el cliente. El agente "
            "queda silenciado hasta que vuelvas a activarlo desde el panel."
        )
    if parsed.kind == "pause":
        return (
            "Pausé todos tus agentes. Ninguna conversación nueva va a recibir "
            "respuesta automática hasta que reanudes desde el panel."
        )
    if parsed.kind == "free_text":
        # The pipeline will pick up the free_text via fanout; no ack
        # needed (the customer is the one who'll see the agent's
        # downstream message).
        return ""
    return ""


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
