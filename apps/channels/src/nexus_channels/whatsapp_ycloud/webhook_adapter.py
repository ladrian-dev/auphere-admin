"""YCloud inbound webhook payload normaliser.

YCloud envelopes::

    {
      "id": "...",
      "type": "whatsapp.inbound_message.received",
      "createTime": "2026-05-09T...",
      "whatsappInboundMessage": {
        "wabaId": "...",
        "from": "+56911112222",
        "to": "+56933334444",        # business number, == provider_identifier
        "wamid": "wamid.HBg...",
        "type": "text" | "interactive" | "audio" | "image" | ...,
        "text": {"body": "hola"},
        "interactive": {
          "type": "button_reply",
          "button_reply": {"id": "btn_yes", "title": "Sí"}
        },
        "customerProfile": {"name": "Juan"}
      }
    }

We normalise into :class:`nexus_channels.base.InboundMessage`. Phase 1 covers
text + interactive (button + list). Media types degrade to ``UNSUPPORTED``
so the agent can answer something instead of dropping the event.

Status callbacks (``whatsapp.message.updated`` and similar) return ``None``
because they don't represent a customer turn.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nexus_channels.base import (
    InboundMessage,
    InboundMessageKind,
    InteractiveReply,
)

INBOUND_MESSAGE_EVENT = "whatsapp.inbound_message.received"


def extract_business_phone(payload: dict[str, Any]) -> str | None:
    """Pull the receiver phone (E.164) used as the channel identifier.

    The webhook layer calls this before normalising the rest, so it can
    resolve the tenant via Redis cache without parsing the entire envelope.
    """
    msg = payload.get("whatsappInboundMessage")
    if not isinstance(msg, dict):
        return None
    to = msg.get("to")
    if isinstance(to, str) and to:
        return to
    return None


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
    else:
        # Audio, image, document, video, location, sticker, button, order etc.
        # Phase 1 acknowledges receipt and lets the agent reply with a graceful
        # "no puedo procesar este tipo de mensaje todavía". The text channel
        # is the primary surface; richer media follows in Phase 2/3.
        kind = InboundMessageKind.UNSUPPORTED

    received_at = _parse_timestamp(payload.get("createTime")) or datetime.now(UTC)

    customer_profile = msg.get("customerProfile") or {}
    sender_name: str | None = None
    if isinstance(customer_profile, dict):
        name = customer_profile.get("name")
        if isinstance(name, str) and name:
            sender_name = name

    return InboundMessage(
        kind=kind,
        provider="ycloud",
        provider_message_id=wamid,
        provider_identifier=business_phone,
        sender_identifier=sender_phone,
        sender_name=sender_name,
        text=text_body,
        interactive=interactive,
        raw_event_type=raw_type if isinstance(raw_type, str) else None,
        received_at=received_at,
    )


def _parse_interactive(raw: Any) -> InteractiveReply | None:
    if not isinstance(raw, dict):
        return None
    # YCloud has historically used both snake_case and camelCase for
    # interactive replies. Match both.
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


def _parse_timestamp(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        # YCloud emits RFC3339 strings.
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
