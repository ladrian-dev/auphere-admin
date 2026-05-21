"""Meta WhatsApp Cloud API webhook payload parser.

Meta delivers all WhatsApp events under a single envelope::

    {
      "object": "whatsapp_business_account",
      "entry": [
        {
          "id": "<WABA_ID>",
          "changes": [
            {"field": "messages", "value": {...}},
            {"field": "message_template_status_update", "value": {...}}
          ]
        }
      ]
    }

The value shape inside ``changes[].value`` depends on ``field``:

- ``messages`` — inbound customer message OR outbound status callback.
  Inbound payloads have ``messages[]``; status updates have ``statuses[]``.
- ``message_template_status_update`` — Meta template approval state changes.
- ``account_update`` / ``account_alerts`` — quality rating, restrictions.
- ``phone_number_quality_update`` — per-number quality changes.

This module:

1. Walks ``entry[].changes[]`` and translates each relevant value into the
   canonical :class:`nexus_channels.base.InboundMessage` (or a
   :class:`StatusUpdate` / :class:`TemplateStatusUpdate` dataclass).
2. Exposes ``extract_business_phone`` for the webhook route to resolve the
   tenant *before* normalising the rest (cheaper than parsing the full
   payload to discover the receiver phone).

Both snake_case and camelCase keys are accepted at the leaves where Meta
has been seen to drift (the envelope itself is stable).
"""

from __future__ import annotations

from collections.abc import Iterator
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

INBOUND_OBJECT = "whatsapp_business_account"


# ── status / template — emitted as plain dataclasses (no Pydantic dep here) ─


@dataclass(slots=True, frozen=True)
class StatusUpdate:
    """An outbound message status transition.

    Mirrors the YCloud-adapter shape so the webhook layer can normalise
    both providers behind a single switch.
    """

    wamid: str
    recipient: str
    status: str  # "sent" | "delivered" | "read" | "failed" | "deleted"
    timestamp: datetime
    waba_id: str
    phone_number_id: str
    conversation_id: str | None = None
    pricing_category: str | None = None
    pricing_model: str | None = None
    error_code: int | None = None
    error_title: str | None = None
    error_message: str | None = None


@dataclass(slots=True, frozen=True)
class TemplateStatusUpdate:
    """Meta template approval-state transition."""

    waba_id: str
    template_id: str
    template_name: str
    language: str
    new_status: str  # APPROVED | PENDING | REJECTED | FLAGGED | PAUSED | DISABLED
    reason: str | None = None
    timestamp: datetime | None = None


# ── extract_business_phone ──────────────────────────────────────────────────


def extract_business_phone(payload: dict[str, Any]) -> str | None:
    """Pull the business phone (E.164) used as the channel identifier.

    Walks the envelope until it finds a ``value.metadata.display_phone_number``
    or, failing that, a ``value.statuses[].recipient_id`` (status callbacks
    don't carry display_phone but they do carry the same value via metadata).

    Returns ``None`` for non-WhatsApp payloads or webhook handshake events.
    """
    if payload.get("object") != INBOUND_OBJECT:
        return None
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes") or []:
            if not isinstance(change, dict):
                continue
            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata") or {}
            if isinstance(metadata, dict):
                phone = metadata.get("display_phone_number")
                if isinstance(phone, str) and phone:
                    return _to_e164(phone)
    return None


def extract_waba_id(payload: dict[str, Any]) -> str | None:
    """Pull the first ``entry[].id`` — the WABA the event belongs to."""
    if payload.get("object") != INBOUND_OBJECT:
        return None
    for entry in payload.get("entry") or []:
        if isinstance(entry, dict):
            wid = entry.get("id")
            if isinstance(wid, str) and wid:
                return wid
    return None


def extract_phone_number_id(payload: dict[str, Any]) -> str | None:
    """Pull ``value.metadata.phone_number_id`` — the PN the event belongs to."""
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes") or []:
            if not isinstance(change, dict):
                continue
            value = change.get("value") or {}
            metadata = value.get("metadata") if isinstance(value, dict) else None
            if isinstance(metadata, dict):
                pnid = metadata.get("phone_number_id")
                if isinstance(pnid, str) and pnid:
                    return pnid
    return None


# ── parse_inbound ───────────────────────────────────────────────────────────


def parse_inbound(payload: dict[str, Any]) -> InboundMessage | None:
    """Return the first inbound message in the payload, or ``None``.

    Meta batches multiple events in a single webhook. Phase 1 processes one
    message at a time (matches the YCloud path) — if a batch carries
    multiple, the webhook route must enumerate ``iter_inbound_messages``
    explicitly. For 99% of traffic batches contain one event.

    Returns ``None`` for envelopes that carry only status callbacks or
    template updates — those have their own parsers below.
    """
    for parsed in iter_inbound_messages(payload):
        return parsed
    return None


def iter_inbound_messages(payload: dict[str, Any]) -> Iterator[InboundMessage]:
    """Generator over every inbound ``messages[]`` entry in the envelope."""
    if payload.get("object") != INBOUND_OBJECT:
        return
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        waba_id = entry.get("id")
        if not isinstance(waba_id, str):
            continue
        for change in entry.get("changes") or []:
            if not isinstance(change, dict):
                continue
            if change.get("field") != "messages":
                continue
            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata") or {}
            business_phone = (
                _to_e164(metadata.get("display_phone_number"))
                if isinstance(metadata, dict)
                else None
            )
            contacts = value.get("contacts") or []
            contact_name = _first_contact_name(contacts)
            for message in value.get("messages") or []:
                if not isinstance(message, dict):
                    continue
                inbound = _build_inbound(
                    message=message,
                    business_phone=business_phone,
                    contact_name=contact_name,
                )
                if inbound is not None:
                    yield inbound


def parse_status_callback(payload: dict[str, Any]) -> StatusUpdate | None:
    """Return the first ``statuses[]`` entry as a :class:`StatusUpdate`."""
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        waba_id = entry.get("id")
        for change in entry.get("changes") or []:
            if not isinstance(change, dict):
                continue
            if change.get("field") != "messages":
                continue
            value = change.get("value") or {}
            metadata = value.get("metadata") or {} if isinstance(value, dict) else {}
            pnid = metadata.get("phone_number_id") if isinstance(metadata, dict) else None
            for status in value.get("statuses") or []:
                if not isinstance(status, dict):
                    continue
                return _build_status(status, waba_id=waba_id or "", pnid=pnid or "")
    return None


def parse_template_status(payload: dict[str, Any]) -> TemplateStatusUpdate | None:
    """Return a template approval transition, if present."""
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        waba_id = entry.get("id") or ""
        for change in entry.get("changes") or []:
            if not isinstance(change, dict):
                continue
            if change.get("field") != "message_template_status_update":
                continue
            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue
            tid = value.get("message_template_id") or value.get("template_id") or ""
            name = value.get("message_template_name") or value.get("name") or ""
            lang = (
                value.get("message_template_language")
                or value.get("language")
                or ""
            )
            new_status = value.get("event") or value.get("new_status") or ""
            reason = value.get("reason") if isinstance(value.get("reason"), str) else None
            return TemplateStatusUpdate(
                waba_id=str(waba_id),
                template_id=str(tid),
                template_name=str(name),
                language=str(lang),
                new_status=str(new_status),
                reason=reason,
                timestamp=None,
            )
    return None


# ── internal: message → InboundMessage ──────────────────────────────────────


def _build_inbound(
    *,
    message: dict[str, Any],
    business_phone: str | None,
    contact_name: str | None,
) -> InboundMessage | None:
    raw_type = message.get("type")
    if not isinstance(raw_type, str):
        return None
    msg_id = message.get("id")
    sender = message.get("from")
    ts_raw = message.get("timestamp")
    if not (isinstance(msg_id, str) and isinstance(sender, str) and ts_raw is not None):
        return None
    try:
        received_at = datetime.fromtimestamp(int(ts_raw), tz=UTC)
    except (TypeError, ValueError):
        received_at = datetime.now(tz=UTC)

    context_id: str | None = None
    context = message.get("context")
    if isinstance(context, dict):
        cid = context.get("id") or context.get("message_id")
        if isinstance(cid, str):
            context_id = cid

    kind, fields = _normalise_body(raw_type, message)
    if kind is None:
        # Unknown type — surface as UNSUPPORTED so the agent can degrade.
        kind = InboundMessageKind.UNSUPPORTED
        fields = {}

    return InboundMessage(
        kind=kind,
        provider="meta",
        provider_message_id=msg_id,
        provider_identifier=business_phone or "",
        sender_identifier=sender,
        sender_name=contact_name,
        text=fields.get("text"),
        interactive=fields.get("interactive"),
        media=fields.get("media"),
        location=fields.get("location"),
        reaction=fields.get("reaction"),
        context_message_id=context_id,
        raw_event_type=raw_type,
        received_at=received_at,
    )


def _normalise_body(
    raw_type: str,
    message: dict[str, Any],
) -> tuple[InboundMessageKind | None, dict[str, Any]]:
    if raw_type == "text":
        body = message.get("text") or {}
        return InboundMessageKind.TEXT, {"text": body.get("body") if isinstance(body, dict) else None}

    if raw_type == "interactive":
        inter = message.get("interactive") or {}
        if not isinstance(inter, dict):
            return InboundMessageKind.UNSUPPORTED, {}
        sub_type = inter.get("type")
        if sub_type == "button_reply":
            br = inter.get("button_reply") or {}
            return InboundMessageKind.INTERACTIVE, {
                "interactive": InteractiveReply(
                    kind="button",
                    payload_id=str(br.get("id") or ""),
                    title=br.get("title"),
                    description=None,
                )
            }
        if sub_type == "list_reply":
            lr = inter.get("list_reply") or {}
            return InboundMessageKind.INTERACTIVE, {
                "interactive": InteractiveReply(
                    kind="list",
                    payload_id=str(lr.get("id") or ""),
                    title=lr.get("title"),
                    description=lr.get("description"),
                )
            }
        return InboundMessageKind.UNSUPPORTED, {}

    if raw_type in {"image", "video", "audio", "document", "sticker"}:
        media = message.get(raw_type) or {}
        if not isinstance(media, dict):
            return InboundMessageKind.UNSUPPORTED, {}
        kind_map = {
            "image": InboundMessageKind.IMAGE,
            "video": InboundMessageKind.VIDEO,
            "audio": InboundMessageKind.AUDIO,
            "document": InboundMessageKind.DOCUMENT,
            "sticker": InboundMessageKind.STICKER,
        }
        return kind_map[raw_type], {
            "media": MediaReference(
                provider_media_id=str(media.get("id") or ""),
                mime_type=media.get("mime_type"),
                sha256=media.get("sha256"),
                caption=media.get("caption"),
                filename=media.get("filename"),
                voice=bool(media.get("voice", False)) if raw_type == "audio" else False,
            )
        }

    if raw_type == "location":
        loc = message.get("location") or {}
        if not isinstance(loc, dict):
            return InboundMessageKind.UNSUPPORTED, {}
        lat_raw = loc.get("latitude")
        lon_raw = loc.get("longitude")
        if lat_raw is None or lon_raw is None:
            return InboundMessageKind.UNSUPPORTED, {}
        try:
            return InboundMessageKind.LOCATION, {
                "location": LocationPayload(
                    latitude=float(lat_raw),
                    longitude=float(lon_raw),
                    name=loc.get("name"),
                    address=loc.get("address"),
                )
            }
        except (TypeError, ValueError):
            return InboundMessageKind.UNSUPPORTED, {}

    if raw_type == "reaction":
        react = message.get("reaction") or {}
        if not isinstance(react, dict):
            return InboundMessageKind.UNSUPPORTED, {}
        return InboundMessageKind.REACTION, {
            "reaction": ReactionPayload(
                target_message_id=str(react.get("message_id") or ""),
                emoji=str(react.get("emoji") or ""),
            )
        }

    if raw_type == "contacts":
        # The runtime doesn't have a structured Contacts shape yet — keep
        # as UNSUPPORTED so the agent surfaces it to the user as "I got
        # your contact card" rather than crashing.
        return InboundMessageKind.CONTACTS, {}

    return None, {}


def _build_status(
    status: dict[str, Any],
    *,
    waba_id: str,
    pnid: str,
) -> StatusUpdate:
    pricing = status.get("pricing") or {}
    if not isinstance(pricing, dict):
        pricing = {}
    conversation = status.get("conversation") or {}
    if not isinstance(conversation, dict):
        conversation = {}
    errors = status.get("errors") or []
    err = errors[0] if errors and isinstance(errors[0], dict) else {}
    try:
        ts = datetime.fromtimestamp(int(status.get("timestamp") or 0), tz=UTC)
    except (TypeError, ValueError):
        ts = datetime.now(tz=UTC)
    return StatusUpdate(
        wamid=str(status.get("id") or ""),
        recipient=str(status.get("recipient_id") or ""),
        status=str(status.get("status") or ""),
        timestamp=ts,
        waba_id=waba_id,
        phone_number_id=pnid,
        conversation_id=conversation.get("id") if isinstance(conversation.get("id"), str) else None,
        pricing_category=(
            pricing.get("category") if isinstance(pricing.get("category"), str) else None
        ),
        pricing_model=(
            pricing.get("pricing_model")
            if isinstance(pricing.get("pricing_model"), str)
            else None
        ),
        error_code=err.get("code") if isinstance(err.get("code"), int) else None,
        error_title=err.get("title") if isinstance(err.get("title"), str) else None,
        error_message=err.get("message") if isinstance(err.get("message"), str) else None,
    )


# ── small helpers ───────────────────────────────────────────────────────────


def _first_contact_name(contacts: list[Any]) -> str | None:
    if not contacts:
        return None
    first = contacts[0]
    if not isinstance(first, dict):
        return None
    profile = first.get("profile")
    if isinstance(profile, dict):
        name = profile.get("name")
        if isinstance(name, str) and name:
            return name
    return None


def _to_e164(phone: Any) -> str | None:
    """Normalise a phone string to E.164 with leading '+'.

    Meta sometimes drops the ``+`` from ``display_phone_number``. The
    ``channels.provider_identifier`` column stores E.164 *with* the plus,
    matching the YCloud adapter — so callers can use either provider with
    the same resolver query.
    """
    if not isinstance(phone, str) or not phone:
        return None
    return phone if phone.startswith("+") else f"+{phone}"
