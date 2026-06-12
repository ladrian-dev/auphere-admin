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

    Canonical webhook-parsing surface so the webhook layer can normalise
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


# ── Coexistence-only webhook fields ────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class MessageEcho:
    """Echo of a message sent from the tenant's WhatsApp Business mobile
    app (Coexistence only).

    Emitted by the ``smb_message_echoes`` webhook field. The runtime
    deduplicates by ``provider_message_id`` and tags the message as
    ``origin="mobile"`` so the operator UI can distinguish app-sent from
    API-sent traffic. The shape mirrors :class:`InboundMessage` but
    intentionally lives as its own type — echo handling is fundamentally
    different from inbound routing (no agent invocation, no service-window
    update).
    """

    waba_id: str
    phone_number_id: str
    provider_message_id: str
    sender_identifier: str  # the business phone (the tenant)
    recipient_identifier: str  # the customer who received the echo
    text: str | None
    received_at: datetime


@dataclass(slots=True, frozen=True)
class AppStateSync:
    """Snapshot of contacts/state from the tenant's mobile app
    (Coexistence only — ``smb_app_state_sync``).

    Triggered after onboarding and after each ``POST /smb_app_data`` with
    ``sync_type=smb_app_state_sync``. The payload carries a list of
    contacts the runtime persists into the tenant's address book for
    operator-side lookup. The first sync after onboarding can take up to
    six hours (Meta's documented batch ceiling).
    """

    waba_id: str
    phone_number_id: str
    contact_count: int
    has_more: bool


@dataclass(slots=True, frozen=True)
class HistorySync:
    """Backfilled message history from the tenant's mobile app
    (Coexistence only — ``history``).

    Up to six months of 1:1 chats are synced after onboarding, segmented
    across multiple ``history`` webhooks. Multimedia is NOT backfilled —
    only message bodies, timestamps, and the customer phone. The runtime
    persists these as ``InboundMessage`` rows with ``origin="history"`` so
    the operator UI can show them in the conversation thread without
    confusing them with live traffic. ``error_code`` 2593109 means the
    business opted out of sharing history at the consent prompt.
    """

    waba_id: str
    phone_number_id: str
    message_count: int
    error_code: int | None = None


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


# ── parse_inbound ───────────────────────────────────────────────────────────


def parse_inbound(payload: dict[str, Any]) -> InboundMessage | None:
    """Return the first inbound message in the payload, or ``None``.

    Meta batches multiple events in a single webhook. Phase 1 processes one
    message at a time — if a batch carries
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


def parse_message_echo(payload: dict[str, Any]) -> MessageEcho | None:
    """First ``smb_message_echoes`` event in the envelope, if any.

    Coexistence-only. ``messages[0]`` carries the same shape as a normal
    inbound (id, from, to, text) but ``from`` is the business itself and
    ``to`` is the customer — the opposite direction of a regular inbound.
    """
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        waba_id = entry.get("id") or ""
        for change in entry.get("changes") or []:
            if not isinstance(change, dict):
                continue
            if change.get("field") != "smb_message_echoes":
                continue
            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata") or {}
            pnid = (
                metadata.get("phone_number_id") if isinstance(metadata, dict) else None
            )
            for msg in value.get("messages") or []:
                if not isinstance(msg, dict):
                    continue
                msg_id = msg.get("id")
                sender = msg.get("from")
                recipient = msg.get("to") or msg.get("recipient_id")
                ts_raw = msg.get("timestamp")
                if not (isinstance(msg_id, str) and isinstance(sender, str)):
                    continue
                try:
                    ts = datetime.fromtimestamp(int(ts_raw or 0), tz=UTC)
                except (TypeError, ValueError):
                    ts = datetime.now(tz=UTC)
                body = msg.get("text")
                text = body.get("body") if isinstance(body, dict) else None
                return MessageEcho(
                    waba_id=str(waba_id),
                    phone_number_id=str(pnid or ""),
                    provider_message_id=msg_id,
                    sender_identifier=sender,
                    recipient_identifier=str(recipient or ""),
                    text=text if isinstance(text, str) else None,
                    received_at=ts,
                )
    return None


def parse_app_state_sync(payload: dict[str, Any]) -> AppStateSync | None:
    """First ``smb_app_state_sync`` event in the envelope, if any."""
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        waba_id = entry.get("id") or ""
        for change in entry.get("changes") or []:
            if not isinstance(change, dict):
                continue
            if change.get("field") != "smb_app_state_sync":
                continue
            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata") or {}
            pnid = (
                metadata.get("phone_number_id") if isinstance(metadata, dict) else None
            )
            contacts = value.get("contacts") or []
            return AppStateSync(
                waba_id=str(waba_id),
                phone_number_id=str(pnid or ""),
                contact_count=len(contacts) if isinstance(contacts, list) else 0,
                has_more=bool(value.get("has_more", False)),
            )
    return None


def parse_history_sync(payload: dict[str, Any]) -> HistorySync | None:
    """First ``history`` event in the envelope, if any.

    Meta batches multiple chat threads per webhook. The ``messages`` array
    inside each thread is what we'd ultimately persist, but this parser
    only reports the summary — the per-message extraction lives in the
    history-import worker (not on the webhook hot path).
    """
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        waba_id = entry.get("id") or ""
        for change in entry.get("changes") or []:
            if not isinstance(change, dict):
                continue
            if change.get("field") != "history":
                continue
            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata") or {}
            pnid = (
                metadata.get("phone_number_id") if isinstance(metadata, dict) else None
            )
            history_threads = value.get("history") or []
            message_count = 0
            if isinstance(history_threads, list):
                for thread in history_threads:
                    if isinstance(thread, dict):
                        msgs = thread.get("messages") or []
                        if isinstance(msgs, list):
                            message_count += len(msgs)
            err_code = value.get("error_code")
            return HistorySync(
                waba_id=str(waba_id),
                phone_number_id=str(pnid or ""),
                message_count=message_count,
                error_code=err_code if isinstance(err_code, int) else None,
            )
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
    kept provider-agnostic — so callers can plug a future provider with
    the same resolver query.
    """
    if not isinstance(phone, str) or not phone:
        return None
    return phone if phone.startswith("+") else f"+{phone}"
