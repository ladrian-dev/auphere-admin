"""YCloud inbound webhook payload normaliser.

YCloud forwards Meta Cloud API events through its own envelope. The four
event types we care about as of Block N:

- ``whatsapp.inbound_message.received`` — customer-side message; the
  payload's ``whatsappInboundMessage`` block carries text / interactive /
  media / location / contacts / reaction / order events. We turn it into
  an :class:`InboundMessage` and the worker pipeline handles it.

- ``whatsapp.message.updated`` — status callback for a previous *outbound*
  send. Maps to ``Message.status`` transitions: ``sent`` → ``delivered``
  → ``read`` or → ``failed``. The webhook layer routes this to
  :func:`parse_status_callback`.

- ``whatsapp.template.updated`` (and the legacy
  ``whatsapp.template_status_update`` alias) — Meta template approval
  state changes (APPROVED / PENDING / REJECTED / FLAGGED / PAUSED /
  DISABLED). Routed to :func:`parse_template_status`.

- Everything else is ignored. We never raise on unknown event types — the
  webhook acks with 200 to prevent YCloud from re-driving the same
  payload until something cleans up the dead-letter on their side.

YCloud has historically used both snake_case and camelCase keys; parsers
accept either to be robust against minor version drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from nexus_channels.base import (
    InboundMessage,
    InboundMessageKind,
    InteractiveReply,
    LocationPayload,
    MediaReference,
    ReactionPayload,
)

INBOUND_MESSAGE_EVENT = "whatsapp.inbound_message.received"
MESSAGE_UPDATED_EVENT = "whatsapp.message.updated"
TEMPLATE_UPDATED_EVENT = "whatsapp.template.updated"
TEMPLATE_UPDATED_EVENT_LEGACY = "whatsapp.template_status_update"

# Stop keywords that trigger an opt-out registration. Comparison is
# case-insensitive, trimmed, and matches the whole inbound text body.
# Meta also enforces "STOP" globally for marketing templates; we honour
# Spanish equivalents because Auphere's tenants are LATAM-focused.
_OPT_OUT_KEYWORDS: frozenset[str] = frozenset(
    {
        "stop",
        "unsubscribe",
        "baja",
        "cancelar",
        "cancela",
        "darme de baja",
        "no quiero más mensajes",
        "salir",
    }
)


def extract_business_phone(payload: dict[str, Any]) -> str | None:
    """Pull the receiver phone (E.164) used as the channel identifier.

    The webhook layer calls this before normalising the rest, so it can
    resolve the tenant via Redis cache without parsing the entire envelope.
    Works on both inbound message events and status callbacks (the latter
    carry the business phone under ``whatsappMessage``).
    """
    inbound = payload.get("whatsappInboundMessage")
    if isinstance(inbound, dict):
        to = inbound.get("to")
        if isinstance(to, str) and to:
            return to
    update = payload.get("whatsappMessage")
    if isinstance(update, dict):
        # On outbound status callbacks YCloud echoes ``from`` (the business
        # phone we sent FROM) — that's still our channel identifier.
        from_phone = update.get("from") or update.get("from_phone")
        if isinstance(from_phone, str) and from_phone:
            return from_phone
    return None


def is_opt_out_text(body: str | None) -> tuple[bool, str | None]:
    """Return ``(matched, keyword)`` if ``body`` is an opt-out request.

    Match policy: exact equality on trimmed/lowercased body OR keyword
    surrounded only by whitespace/punctuation. Conservative on purpose —
    a "no me molesten más" inside a paragraph is the LLM's job, not the
    webhook's.
    """
    if not body:
        return False, None
    normalised = body.strip().lower().rstrip(".!?,")
    if normalised in _OPT_OUT_KEYWORDS:
        return True, normalised
    # Single-token messages where the token alone is the keyword.
    tokens = normalised.split()
    if len(tokens) == 1 and tokens[0] in _OPT_OUT_KEYWORDS:
        return True, tokens[0]
    return False, None


def parse_inbound(payload: dict[str, Any]) -> InboundMessage | None:
    """Return an :class:`InboundMessage` for customer-turn events; ``None``
    for status callbacks or other non-message events.
    """
    event_type = payload.get("type")
    if event_type != INBOUND_MESSAGE_EVENT:
        return None

    msg = payload.get("whatsappInboundMessage")
    if not isinstance(msg, dict):
        return None

    business_phone = msg.get("to")
    sender_phone = msg.get("from")
    wamid = msg.get("wamid") or msg.get("id")
    if not isinstance(business_phone, str) or not isinstance(sender_phone, str):
        return None
    if not isinstance(wamid, str) or not wamid:
        return None

    raw_type = msg.get("type")
    text_body: str | None = None
    interactive: InteractiveReply | None = None
    media: MediaReference | None = None
    location: LocationPayload | None = None
    reaction: ReactionPayload | None = None
    kind: InboundMessageKind

    if raw_type == "text":
        text = msg.get("text")
        if isinstance(text, dict):
            body = text.get("body")
            if isinstance(body, str):
                text_body = body
        kind = InboundMessageKind.TEXT
    elif raw_type == "interactive":
        interactive = _parse_interactive(msg.get("interactive"))
        kind = InboundMessageKind.INTERACTIVE if interactive else InboundMessageKind.UNSUPPORTED
    elif raw_type in {"audio", "image", "document", "video", "sticker"}:
        media = _parse_media(msg.get(raw_type), raw_type=raw_type)
        # Body fallback for image/video captions surfaces to ``text`` so
        # the pipeline can use it directly when the media itself can't be
        # processed.
        if media and media.caption:
            text_body = media.caption
        kind = _MEDIA_KIND_MAP.get(raw_type, InboundMessageKind.UNSUPPORTED)
    elif raw_type == "location":
        location = _parse_location(msg.get("location"))
        kind = InboundMessageKind.LOCATION if location else InboundMessageKind.UNSUPPORTED
    elif raw_type == "contacts":
        # Pydantic-validate the list at the channel layer would be overkill;
        # we surface the raw list through ``text`` as a JSON-serialised hint
        # for the agent so it can ask "¿este es el contacto que querías
        # compartir?" without losing data.
        kind = InboundMessageKind.CONTACTS
        contacts = msg.get("contacts")
        if isinstance(contacts, list) and contacts:
            first = contacts[0]
            if isinstance(first, dict):
                name = first.get("name") or {}
                if isinstance(name, dict):
                    text_body = (
                        name.get("formatted_name") or name.get("first_name") or "[contact shared]"
                    )
    elif raw_type == "reaction":
        reaction = _parse_reaction(msg.get("reaction"))
        kind = InboundMessageKind.REACTION if reaction else InboundMessageKind.UNSUPPORTED
    elif raw_type == "button":
        # Legacy template button reply (Cloud API "button" type, distinct
        # from the modern "interactive.button_reply"). Surface its text.
        button = msg.get("button")
        if isinstance(button, dict):
            text_body = button.get("text") or button.get("payload")
        kind = InboundMessageKind.INTERACTIVE
    else:
        kind = InboundMessageKind.UNSUPPORTED

    received_at = _parse_timestamp(payload.get("createTime")) or datetime.now(UTC)

    customer_profile = msg.get("customerProfile") or msg.get("customer_profile") or {}
    sender_name: str | None = None
    if isinstance(customer_profile, dict):
        name = customer_profile.get("name")
        if isinstance(name, str) and name:
            sender_name = name

    context_message_id = _parse_context_message_id(msg.get("context"))

    return InboundMessage(
        kind=kind,
        provider="ycloud",
        provider_message_id=wamid,
        provider_identifier=business_phone,
        sender_identifier=sender_phone,
        sender_name=sender_name,
        text=text_body,
        interactive=interactive,
        media=media,
        location=location,
        reaction=reaction,
        context_message_id=context_message_id,
        raw_event_type=raw_type if isinstance(raw_type, str) else None,
        received_at=received_at,
    )


# ── status callback parsing ─────────────────────────────────────────────────


@dataclass(frozen=True)
class StatusCallback:
    """Normalised status callback. The webhook layer maps these onto
    ``Message`` columns. ``failure_code`` is the Meta error code (string;
    e.g. "131026") so the dispatcher can decide retry vs no-retry."""

    wamid: str
    business_phone: str
    recipient_phone: str | None
    status: str  # sent / delivered / read / failed / deleted
    timestamp: datetime
    failure_code: str | None = None
    failure_title: str | None = None
    failure_detail: str | None = None
    pricing_category: str | None = None
    conversation_provider_id: str | None = None


def parse_status_callback(payload: dict[str, Any]) -> StatusCallback | None:
    """Normalise a ``whatsapp.message.updated`` event.

    Returns ``None`` for non-status events. The shape YCloud forwards is
    Meta-compatible:

    ::

        {
          "type": "whatsapp.message.updated",
          "whatsappMessage": {
            "wamid": "...",
            "from": "+56933334444",     # business phone
            "to":   "+56911112222",     # recipient
            "status": "delivered",
            "timestamp": "...",
            "errors": [{"code": 131026, "title": "...", "detail": "..."}],
            "pricing": {"category": "service"},
            "conversation": {"id": "...", "origin": {"type": "service"}}
          }
        }
    """
    if payload.get("type") not in {MESSAGE_UPDATED_EVENT, "whatsapp.message_status_update"}:
        return None
    block = payload.get("whatsappMessage") or payload.get("whatsappMessageStatus")
    if not isinstance(block, dict):
        return None
    wamid = block.get("wamid") or block.get("id")
    raw_status = block.get("status")
    business_phone = block.get("from") or block.get("from_phone")
    if not isinstance(wamid, str) or not isinstance(raw_status, str):
        return None
    if not isinstance(business_phone, str):
        return None

    failure_code = None
    failure_title = None
    failure_detail = None
    errors = block.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict):
            raw_code = first.get("code")
            if raw_code is not None:
                failure_code = str(raw_code)
            failure_title = first.get("title")
            failure_detail = first.get("detail") or first.get("message")

    pricing_category = None
    pricing = block.get("pricing")
    if isinstance(pricing, dict):
        pricing_category = pricing.get("category")

    conversation_id = None
    conversation = block.get("conversation")
    if isinstance(conversation, dict):
        conversation_id = conversation.get("id")

    return StatusCallback(
        wamid=wamid,
        business_phone=business_phone,
        recipient_phone=block.get("to") or block.get("recipient_phone"),
        status=raw_status.lower(),
        timestamp=_parse_timestamp(block.get("timestamp")) or datetime.now(UTC),
        failure_code=failure_code,
        failure_title=failure_title if isinstance(failure_title, str) else None,
        failure_detail=failure_detail if isinstance(failure_detail, str) else None,
        pricing_category=pricing_category if isinstance(pricing_category, str) else None,
        conversation_provider_id=conversation_id if isinstance(conversation_id, str) else None,
    )


# ── template status parsing ─────────────────────────────────────────────────


@dataclass(frozen=True)
class TemplateStatusUpdate:
    """Normalised template approval event from Meta (via YCloud).

    The webhook layer upserts a row in ``whatsapp_template_status`` so the
    ``notification.send_template`` tool can refuse to enqueue a paused or
    rejected template.
    """

    waba_id: str
    template_name: str
    language: str
    status: str  # approved / pending / rejected / flagged / paused / disabled
    category: str | None
    reason: str | None
    raw: dict[str, Any]
    event_at: datetime


def parse_template_status(payload: dict[str, Any]) -> TemplateStatusUpdate | None:
    if payload.get("type") not in {TEMPLATE_UPDATED_EVENT, TEMPLATE_UPDATED_EVENT_LEGACY}:
        return None
    block = (
        payload.get("whatsappTemplate")
        or payload.get("whatsappMessageTemplate")
        or payload.get("templateStatus")
    )
    if not isinstance(block, dict):
        return None
    waba_id = block.get("wabaId") or block.get("waba_id")
    name = block.get("name") or block.get("template_name")
    language = block.get("language") or "es"
    status = block.get("status")
    if not (
        isinstance(waba_id, str)
        and isinstance(name, str)
        and isinstance(language, str)
        and isinstance(status, str)
    ):
        return None
    category = block.get("category")
    reason = block.get("reason") or block.get("rejectedReason")
    return TemplateStatusUpdate(
        waba_id=waba_id,
        template_name=name,
        language=language,
        status=status.lower(),
        category=category if isinstance(category, str) else None,
        reason=reason if isinstance(reason, str) else None,
        raw=block,
        event_at=_parse_timestamp(payload.get("createTime")) or datetime.now(UTC),
    )


# ── helpers ─────────────────────────────────────────────────────────────────


_MEDIA_KIND_MAP: dict[str, InboundMessageKind] = {
    "audio": InboundMessageKind.AUDIO,
    "image": InboundMessageKind.IMAGE,
    "document": InboundMessageKind.DOCUMENT,
    "video": InboundMessageKind.VIDEO,
    "sticker": InboundMessageKind.STICKER,
}


def _parse_interactive(raw: Any) -> InteractiveReply | None:
    if not isinstance(raw, dict):
        return None
    button = raw.get("button_reply") or raw.get("buttonReply")
    if isinstance(button, dict):
        bid = button.get("id")
        title = button.get("title")
        if isinstance(bid, str):
            return InteractiveReply(
                kind="button",
                payload_id=bid,
                title=title if isinstance(title, str) else None,
            )
    list_reply = raw.get("list_reply") or raw.get("listReply")
    if isinstance(list_reply, dict):
        lid = list_reply.get("id")
        title = list_reply.get("title")
        description = list_reply.get("description")
        if isinstance(lid, str):
            return InteractiveReply(
                kind="list",
                payload_id=lid,
                title=title if isinstance(title, str) else None,
                description=description if isinstance(description, str) else None,
            )
    return None


def _parse_media(raw: Any, *, raw_type: str) -> MediaReference | None:
    if not isinstance(raw, dict):
        return None
    media_id = raw.get("id")
    if not isinstance(media_id, str) or not media_id:
        return None
    return MediaReference(
        provider_media_id=media_id,
        mime_type=raw.get("mime_type") or raw.get("mimeType"),
        sha256=raw.get("sha256") or raw.get("sha_256"),
        caption=raw.get("caption") if isinstance(raw.get("caption"), str) else None,
        filename=raw.get("filename") if isinstance(raw.get("filename"), str) else None,
        voice=bool(raw.get("voice", False)) if raw_type == "audio" else False,
    )


def _parse_location(raw: Any) -> LocationPayload | None:
    if not isinstance(raw, dict):
        return None
    lat_raw = raw.get("latitude")
    lon_raw = raw.get("longitude")
    if lat_raw is None or lon_raw is None:
        return None
    try:
        lat = float(lat_raw)
        lon = float(lon_raw)
    except (TypeError, ValueError):
        return None
    return LocationPayload(
        latitude=lat,
        longitude=lon,
        name=raw.get("name") if isinstance(raw.get("name"), str) else None,
        address=raw.get("address") if isinstance(raw.get("address"), str) else None,
    )


def _parse_reaction(raw: Any) -> ReactionPayload | None:
    if not isinstance(raw, dict):
        return None
    target = raw.get("message_id") or raw.get("messageId")
    if not isinstance(target, str) or not target:
        return None
    emoji = raw.get("emoji")
    if not isinstance(emoji, str):
        emoji = ""
    return ReactionPayload(target_message_id=target, emoji=emoji)


def _parse_context_message_id(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    cid = raw.get("id") or raw.get("message_id")
    return cid if isinstance(cid, str) and cid else None


def _parse_timestamp(raw: Any) -> datetime | None:
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(float(raw), tz=UTC)
        except (OSError, OverflowError, ValueError):
            return None
    if not isinstance(raw, str) or not raw:
        return None
    # Bare unix timestamp as string.
    if raw.isdigit():
        try:
            return datetime.fromtimestamp(int(raw), tz=UTC)
        except (OSError, OverflowError, ValueError):
            return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
