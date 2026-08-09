"""TikTok Business Messaging webhook payload parser.

TikTok delivers messaging events under an envelope of the shape::

    {
      "event": "message_received",
      "business_id": "7123456789012345678",
      "timestamp": 1701234567,
      "data": {
        "conversation_id": "conv_abc",
        "message_id": "msg_123",
        "sender": {"open_id": "_000abc...", "nickname": "Ana"},
        "message_type": "text",
        "content": {"text": "hola, ¿tienen cita mañana?"}
      }
    }

Two things differ meaningfully from the Meta parser next door:

1. **``conversation_id`` is load-bearing.** TikTok has no "send to a user"
   call — every outbound send targets a conversation that the *user* opened.
   The id therefore has to survive from the inbound event all the way to the
   outbound send, so it is carried on
   :attr:`InboundMessage.context_message_id` (the only free-form correlation
   slot the canonical shape offers) as well as being returned by
   :func:`extract_conversation_id` for callers that want it directly.

2. **Media arrives as an id, not a URL.** ``image_id`` must be exchanged for
   bytes via an authenticated download call, which is exactly the two-step
   dance the Meta media path already does, so it maps onto
   :class:`MediaReference` cleanly.

Unknown ``message_type`` values become
:attr:`InboundMessageKind.UNSUPPORTED` rather than being dropped — the
Protocol is explicit that silent discards are not allowed, and an agent that
sees "the customer sent something I can't read" degrades far better than one
that sees nothing at all.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from nexus_channels.base import (
    InboundMessage,
    InboundMessageKind,
    MediaReference,
)

PROVIDER = "tiktok"

# Event names we translate into an InboundMessage.
_MESSAGE_EVENTS = frozenset({"message_received", "message", "im_message"})

# Everything else TikTok can emit. Recognised so the route can log them at
# info instead of warning — a known-but-ignored event is not a defect.
_KNOWN_NON_MESSAGE_EVENTS = frozenset(
    {
        "message_read",
        "message_delivered",
        "conversation_created",
        "conversation_closed",
        "webhook_verify",
    }
)

_KIND_BY_MESSAGE_TYPE: dict[str, InboundMessageKind] = {
    "text": InboundMessageKind.TEXT,
    "image": InboundMessageKind.IMAGE,
    "video": InboundMessageKind.VIDEO,
    # A shared TikTok post. There is no first-class kind for "a link to a
    # video on the platform", and treating it as VIDEO would make the
    # multimodal pipeline try to download something it can't. TEXT with the
    # post reference in the body is the honest degradation.
    "post": InboundMessageKind.TEXT,
    "card": InboundMessageKind.TEXT,
}


@dataclass(slots=True, frozen=True)
class ConversationEvent:
    """A non-message event (read receipts, conversation lifecycle).

    Kept as a dataclass rather than forced into ``InboundMessage`` because
    these must never reach the agent — they only move bookkeeping.
    """

    event: str
    business_id: str
    conversation_id: str | None
    message_id: str | None
    occurred_at: datetime


def extract_business_id(payload: dict[str, Any]) -> str | None:
    """Pull the receiving Business Account id without parsing the rest.

    The webhook route calls this first to resolve the tenant, so it stays
    deliberately cheap and tolerant: a payload we can't attribute to a
    business is unroutable regardless of how well-formed the rest is.
    """
    for key in ("business_id", "businessId"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, int):
            return str(value)
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("business_id", "businessId"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, int):
                return str(value)
    return None


def extract_conversation_id(payload: dict[str, Any]) -> str | None:
    """Pull ``conversation_id`` — the handle every outbound send needs."""
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    for key in ("conversation_id", "conversationId"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def is_message_event(payload: dict[str, Any]) -> bool:
    return _event_name(payload) in _MESSAGE_EVENTS


def is_known_event(payload: dict[str, Any]) -> bool:
    name = _event_name(payload)
    return name in _MESSAGE_EVENTS or name in _KNOWN_NON_MESSAGE_EVENTS


def parse_inbound(payload: dict[str, Any]) -> InboundMessage | None:
    """Return the inbound message in the payload, or ``None``.

    ``None`` means "this envelope carries no customer message" — a read
    receipt, a lifecycle event, or something unattributable. It never means
    "unsupported message type"; those come back as an
    :attr:`InboundMessageKind.UNSUPPORTED` message.
    """
    for parsed in iter_inbound_messages(payload):
        return parsed
    return None


def iter_inbound_messages(payload: dict[str, Any]) -> Iterator[InboundMessage]:
    """Generator over every inbound message in the envelope.

    TikTok sends one message per delivery today, but batching is exactly the
    kind of thing providers add without warning, so the parser is written to
    enumerate from the start and ``parse_inbound`` just takes the first.
    """
    if not is_message_event(payload):
        return

    business_id = extract_business_id(payload)
    if not business_id:
        return

    data = payload.get("data")
    if not isinstance(data, dict):
        return

    received_at = _to_datetime(payload.get("timestamp") or data.get("timestamp"))
    conversation_id = extract_conversation_id(payload)

    messages = data.get("messages")
    entries: list[dict[str, Any]] = (
        [m for m in messages if isinstance(m, dict)] if isinstance(messages, list) else [data]
    )

    for entry in entries:
        inbound = _build_inbound(
            entry,
            business_id=business_id,
            conversation_id=conversation_id,
            received_at=received_at,
        )
        if inbound is not None:
            yield inbound


def parse_conversation_event(payload: dict[str, Any]) -> ConversationEvent | None:
    """Translate a non-message event, or ``None`` if this isn't one."""
    name = _event_name(payload)
    if name in _MESSAGE_EVENTS or not name:
        return None
    business_id = extract_business_id(payload)
    if not business_id:
        return None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    message_id = data.get("message_id") if isinstance(data, dict) else None
    return ConversationEvent(
        event=name,
        business_id=business_id,
        conversation_id=extract_conversation_id(payload),
        message_id=message_id if isinstance(message_id, str) else None,
        occurred_at=_to_datetime(payload.get("timestamp")),
    )


# ── internals ───────────────────────────────────────────────────────────────


def _event_name(payload: dict[str, Any]) -> str:
    for key in ("event", "event_type", "eventType"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def _build_inbound(
    entry: dict[str, Any],
    *,
    business_id: str,
    conversation_id: str | None,
    received_at: datetime,
) -> InboundMessage | None:
    message_id = _first_str(entry, "message_id", "messageId", "id")
    if not message_id:
        # Without a stable id we cannot deduplicate, and TikTok redrives
        # aggressively. Processing it would risk answering the same customer
        # turn twice, which is worse than dropping one malformed event.
        return None

    sender = entry.get("sender") if isinstance(entry.get("sender"), dict) else {}
    sender_id = _first_str(sender, "open_id", "openId", "user_id", "id") or _first_str(
        entry, "sender_id", "senderId"
    )
    if not sender_id:
        return None
    sender_name = _first_str(sender, "nickname", "display_name", "name")

    message_type = (_first_str(entry, "message_type", "messageType") or "text").lower()
    raw_content = entry.get("content")
    content: dict[str, Any] = raw_content if isinstance(raw_content, dict) else {}
    kind = _KIND_BY_MESSAGE_TYPE.get(message_type, InboundMessageKind.UNSUPPORTED)

    text = _extract_text(message_type, content, entry)
    media = _extract_media(message_type, content)

    # An image whose id we couldn't find is not an image we can fetch. Mark
    # it unsupported so the agent knows something arrived rather than
    # receiving an empty message with no explanation.
    if kind in (InboundMessageKind.IMAGE, InboundMessageKind.VIDEO) and media is None:
        kind = InboundMessageKind.UNSUPPORTED

    return InboundMessage(
        kind=kind,
        provider=PROVIDER,
        provider_message_id=message_id,
        provider_identifier=business_id,
        sender_identifier=sender_id,
        sender_name=sender_name,
        text=text,
        media=media,
        # Not a quoted reply: this is the conversation handle the outbound
        # path needs, and it is the only correlation slot the canonical
        # shape offers. See the module docstring.
        context_message_id=conversation_id,
        raw_event_type=message_type,
        received_at=received_at,
    )


def _extract_text(
    message_type: str,
    content: dict[str, Any],
    entry: dict[str, Any],
) -> str | None:
    if message_type in ("text", ""):
        return _first_str(content, "text", "body") or _first_str(entry, "text")
    if message_type == "post":
        # Surface whatever identifies the shared post so the agent can at
        # least acknowledge it concretely.
        ref = _first_str(content, "share_url", "url", "item_id", "video_id")
        return f"[TikTok post: {ref}]" if ref else "[TikTok post]"
    if message_type == "card":
        return _first_str(content, "title", "text")
    # Media types may still carry a caption.
    return _first_str(content, "caption", "text")


def _extract_media(message_type: str, content: dict[str, Any]) -> MediaReference | None:
    if message_type not in ("image", "video"):
        return None
    media_id = _first_str(content, "image_id", "imageId", "media_id", "video_id")
    if not media_id:
        return None
    return MediaReference(
        provider_media_id=media_id,
        mime_type=_first_str(content, "mime_type", "mimeType"),
        caption=_first_str(content, "caption"),
    )


def _first_str(source: Any, *keys: str) -> str | None:
    if not isinstance(source, dict):
        return None
    for key in keys:
        value = source.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, int):
            return str(value)
    return None


def _to_datetime(raw: Any) -> datetime:
    """TikTok sends unix seconds. Fall back to now() rather than failing —
    a message with a slightly wrong timestamp still needs answering."""
    if isinstance(raw, int | float) and raw > 0:
        # Milliseconds are a common provider drift; anything past year ~2286
        # in seconds is really milliseconds.
        seconds = raw / 1000 if raw > 1e11 else raw
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return datetime.now(UTC)
    if isinstance(raw, str):
        try:
            return _to_datetime(int(raw))
        except ValueError:
            return datetime.now(UTC)
    return datetime.now(UTC)
