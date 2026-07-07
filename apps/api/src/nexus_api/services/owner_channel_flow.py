"""Owner backchannel inbound flow — provider-agnostic core.

Handles a WhatsApp message addressed to an **Auphere owner-channel
number** (``auphere_owner_channels`` registry), NOT to any tenant's
business number. Transport concerns (signature verification, payload
parsing) live in the webhook layer — today ``/webhook/meta`` detects
owner-channel traffic by matching the event's ``phone_number_id``
against the registry and delegates here.

Flow (spec architecture/owner-backchannel.md §5):

1. Look the sender phone up in ``owner_phone_index`` (RLS-free; the
   table exists for exactly this discovery step).
2. With a tenant in hand, switch the session into the tenant's RLS
   scope and route the message:
   a) TOFU — refuse to drive consultations until the owner confirmed
      with ``/yes`` (migration 0043).
   b) Slash commands (/help /handoff /pause /yes /no /done).
   c) Match an open consultation via the correlation_id in the text
      (``(ref XYZ12345)``); fall back to the most-recent open
      consultation if there is exactly one.
   d) Update the consultation to ``status='answered'`` and enqueue a
      fanout event so the worker re-enters the pipeline with the
      owner's response as a system addendum.

Replies to the owner go out through the Meta Cloud API using the
channel row's ``provider_phone_id`` + decrypted access token. Failures
are non-fatal — the webhook must never 5xx because a reply failed
(Meta re-drives aggressively and would re-deliver the same message).
"""

from __future__ import annotations

import contextlib
import re
import uuid
from datetime import UTC, datetime

import structlog
from nexus_channels.whatsapp_meta import MetaClient
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from nexus_api.repositories.auphere_channels import ResolvedAuphereChannel
from nexus_api.services.owner_command_parser import (
    ParsedOwnerMessage,
    parse_owner_message,
)

log = structlog.get_logger(__name__)

OWNER_FANOUT_STREAM = "nexus:owner_fanout"

# ``(ref XYZ12345)``, ``ref:XYZ12345``, ``[ref XYZ12345]`` — owner can quote
# the ref however they like as long as the 8-char token is present.
_CORRELATION_RE = re.compile(r"ref\s*[:\-]?\s*([A-Za-z0-9_-]{6,12})", re.IGNORECASE)


def normalize_owner_phone(phone: str) -> str:
    """Meta sends ``wa_id`` without the leading ``+``; the
    ``owner_phone_index`` PK stores E.164 with it. Normalise defensively."""
    p = phone.strip()
    if p and not p.startswith("+"):
        p = "+" + p
    return p


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


def _mask_phone(phone: str) -> str:
    if len(phone) <= 6:
        return "***"
    return phone[:3] + "***" + phone[-3:]


async def _send_owner_reply(
    *,
    channel: ResolvedAuphereChannel,
    to_phone: str,
    text: str,
) -> None:
    """Best-effort free-form reply to the owner over WhatsApp (Meta).

    Used for slash-command acknowledgements, the "no open consultation"
    notice, and the TOFU welcome. Failures are non-fatal.
    """
    if not channel.can_send:
        log.warning(
            "owner_channel.reply_skipped_no_credentials",
            channel=channel.display_name,
        )
        return
    settings = get_settings()
    client = MetaClient(
        app_secret=settings.meta_app_secret,
        require_appsecret_proof=settings.meta_require_appsecret_proof,
    )
    try:
        assert channel.provider_phone_id is not None  # can_send guarantees
        assert channel.access_token is not None
        await client.send_text(
            phone_number_id=channel.provider_phone_id,
            access_token=channel.access_token,
            to=to_phone.lstrip("+"),
            body=text,
        )
    except Exception as exc:
        log.warning(
            "owner_channel.reply_failed",
            to=_mask_phone(to_phone),
            error=str(exc)[:200],
        )
    finally:
        with contextlib.suppress(Exception):  # pragma: no cover - best effort
            await client.close()


async def handle_owner_inbound(
    session: AsyncSession,
    redis: Redis,
    *,
    channel: ResolvedAuphereChannel,
    sender_phone: str,
    text: str | None,
) -> dict[str, str]:
    """Route one inbound owner message. Returns a status dict the webhook
    serialises verbatim (always 200 upstream)."""
    if not isinstance(text, str) or not text.strip():
        # Audio / image / sticker — not transcribed on the backchannel.
        # Leave the consultation open so the owner can retry with text.
        log.info(
            "owner_channel.non_text_message",
            from_phone=_mask_phone(sender_phone),
        )
        return {"status": "ignored:non_text"}

    sender = normalize_owner_phone(sender_phone)
    idx = await session.get(OwnerPhoneIndex, sender)
    if idx is None:
        log.warning("owner_channel.unknown_phone", phone=_mask_phone(sender))
        return {"status": "ignored:unknown_phone"}
    if not idx.active:
        log.info("owner_channel.inactive_phone", phone=_mask_phone(sender))
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
    # number.
    if not is_confirmed:
        if parsed.kind == "yes":
            # Re-fetch under a fresh transaction so the UPDATE rides
            # the session's normal autocommit boundary instead of
            # stamping a stale, expired-after-rollback identity.
            async with session.begin():
                idx_fresh = await session.get(OwnerPhoneIndex, sender)
                if idx_fresh is not None:
                    idx_fresh.confirmed_at = datetime.now(UTC)
            await _send_owner_reply(channel=channel, to_phone=sender, text=_TOFU_CONFIRMED_TEXT)
            log.info(
                "owner_channel.tofu_confirmed",
                tenant_id=str(tenant_id),
                phone=_mask_phone(sender),
            )
            return {"status": "tofu_confirmed"}

        await _send_owner_reply(channel=channel, to_phone=sender, text=_TOFU_WELCOME_TEXT)
        log.info(
            "owner_channel.tofu_pending",
            tenant_id=str(tenant_id),
            phone=_mask_phone(sender),
            command_kind=parsed.kind,
        )
        return {"status": "tofu_pending"}

    # /help is special — never touches a consultation, always replies.
    if parsed.kind == "help":
        await _send_owner_reply(channel=channel, to_phone=sender, text=_HELP_TEXT)
        log.info("owner_channel.help_sent", tenant_id=str(tenant_id))
        return {"status": "help_sent"}

    # Unknown slash verb — reply with help so the owner learns the
    # vocabulary instead of having their message silently swallowed.
    if parsed.kind == "unknown_command":
        await _send_owner_reply(
            channel=channel,
            to_phone=sender,
            text=f"No reconozco el comando /{parsed.slash_verb}.\n\n{_HELP_TEXT}",
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
            log.info(
                "owner_channel.no_matching_consultation",
                tenant_id=str(tenant_id),
                phone=_mask_phone(sender),
                command_kind=parsed.kind,
            )
            await _send_owner_reply(
                channel=channel, to_phone=sender, text=_NO_OPEN_CONSULTATION_TEXT
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
        await _send_owner_reply(channel=channel, to_phone=sender, text=ack_text)

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
    ambiguous (>1 open and no ref) — the caller logs + 200."""
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
