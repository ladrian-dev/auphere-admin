"""Parse Instagram (``object=instagram``) and Page (``object=page``) webhooks.

Both objects share the Messenger Platform envelope::

    {"object": "instagram" | "page",
     "entry": [{"id": "<IG_ID | PAGE_ID>", "time": ...,
                "messaging": [ {sender, recipient, timestamp, message | postback
                                | reaction | read | referral} ],
                "changes":   [ {"field": "comments" | "mentions" | ..., "value": {...}} ]}]}

``entry.id`` is the business's account or Page — the identifier the tenant
is resolved from. ``sender.id`` is the person (IGSID / PSID), assigned by
Meta and never taken from anything the model produced.

Pure functions, no I/O. The route decides what to enqueue.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from nexus_channels.base import (
    InboundMessage,
    InboundMessageKind,
    InteractiveReply,
    MediaReference,
    ReactionPayload,
)

PROVIDER_INSTAGRAM = "meta_instagram"
PROVIDER_MESSENGER = "meta_messenger"
OBJECT_TO_PROVIDER: dict[str, str] = {
    "instagram": PROVIDER_INSTAGRAM,
    "page": PROVIDER_MESSENGER,
}
#: Prefix of ``context_message_id`` / ``provider_message_id`` for a comment
#: turn. The outbound side reads it back to send a private reply.
COMMENT_PREFIX = "comment:"
#: Prefix of ``MediaReference.provider_media_id`` for an attachment that
#: arrives as a CDN URL (both channels) instead of a media id (WhatsApp).
URL_MEDIA_PREFIX = "url:"

_ATTACHMENT_KINDS: dict[str, InboundMessageKind] = {
    "image": InboundMessageKind.IMAGE,
    "video": InboundMessageKind.VIDEO,
    "audio": InboundMessageKind.AUDIO,
    "file": InboundMessageKind.DOCUMENT,
    "sticker": InboundMessageKind.STICKER,
    "animated_image": InboundMessageKind.IMAGE,
}

EventKind = Literal["message", "comment", "echo", "read", "deleted", "other"]


@dataclass(frozen=True, slots=True)
class SocialEvent:
    """One normalised event of a batch.

    ``inbound`` is set for ``message`` and ``comment``: what becomes a turn.
    The other kinds are logged and acked.
    """

    kind: EventKind
    provider: str
    account_id: str
    inbound: InboundMessage | None = None
    detail: str | None = None


def provider_for(payload: dict[str, Any]) -> str | None:
    obj = payload.get("object")
    return OBJECT_TO_PROVIDER.get(obj) if isinstance(obj, str) else None


def entry_account_ids(payload: dict[str, Any]) -> list[str]:
    """The business accounts / Pages a batch is about, in order, deduplicated."""
    seen: list[str] = []
    for entry in payload.get("entry") or []:
        if isinstance(entry, dict):
            eid = entry.get("id")
            if eid is not None and str(eid) not in seen:
                seen.append(str(eid))
    return seen


def iter_events(payload: dict[str, Any]) -> list[SocialEvent]:
    provider = provider_for(payload)
    if provider is None:
        return []
    events: list[SocialEvent] = []
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict) or entry.get("id") is None:
            continue
        account_id = str(entry["id"])
        for item in entry.get("messaging") or []:
            if isinstance(item, dict):
                events.append(_messaging_event(item, provider=provider, account_id=account_id))
        for change in entry.get("changes") or []:
            if isinstance(change, dict):
                events.append(_change_event(change, provider=provider, account_id=account_id))
        # ``standby`` (another app owns the thread) is never ours to answer.
    return events


# ── messaging[] ─────────────────────────────────────────────────────────────


def _ts(value: Any) -> datetime:
    if isinstance(value, (int, float)) and value > 0:
        # Meta sends milliseconds on messaging events.
        return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, tz=UTC)
    return datetime.now(UTC)


def _messaging_event(item: dict[str, Any], *, provider: str, account_id: str) -> SocialEvent:
    sender = str((item.get("sender") or {}).get("id") or "")
    received = _ts(item.get("timestamp"))

    message = item.get("message")
    if isinstance(message, dict):
        if message.get("is_echo"):
            return SocialEvent("echo", provider, account_id, detail=message.get("mid"))
        if message.get("is_deleted"):
            return SocialEvent("deleted", provider, account_id, detail=message.get("mid"))
        if not sender or sender == account_id or not message.get("mid"):
            return SocialEvent("other", provider, account_id, detail="message_without_sender")
        return SocialEvent(
            "message",
            provider,
            account_id,
            inbound=_inbound_from_message(
                message, provider=provider, account_id=account_id, sender=sender, received=received
            ),
        )

    postback = item.get("postback")
    if isinstance(postback, dict) and sender and sender != account_id:
        payload_id = str(postback.get("payload") or postback.get("title") or "postback")
        mid = str(postback.get("mid") or f"postback:{sender}:{item.get('timestamp')}")
        return SocialEvent(
            "message",
            provider,
            account_id,
            inbound=InboundMessage(
                kind=InboundMessageKind.INTERACTIVE,
                provider=provider,
                provider_message_id=mid[:255],
                provider_identifier=account_id,
                sender_identifier=sender,
                interactive=InteractiveReply(
                    kind="button", payload_id=payload_id[:255], title=postback.get("title")
                ),
                raw_event_type="postback",
                received_at=received,
            ),
        )

    reaction = item.get("reaction")
    if isinstance(reaction, dict) and sender and sender != account_id and reaction.get("mid"):
        emoji = "" if reaction.get("action") == "unreact" else str(reaction.get("emoji") or "")
        target = str(reaction["mid"])
        return SocialEvent(
            "message",
            provider,
            account_id,
            inbound=InboundMessage(
                kind=InboundMessageKind.REACTION,
                provider=provider,
                provider_message_id=f"reaction:{target}:{sender}:{item.get('timestamp')}"[:255],
                provider_identifier=account_id,
                sender_identifier=sender,
                reaction=ReactionPayload(target_message_id=target, emoji=emoji),
                raw_event_type="reaction",
                received_at=received,
            ),
        )

    if isinstance(item.get("read"), dict):
        return SocialEvent("read", provider, account_id)
    if isinstance(item.get("referral"), dict):
        return SocialEvent("other", provider, account_id, detail="referral")
    return SocialEvent("other", provider, account_id, detail=_first_key(item))


def _inbound_from_message(
    message: dict[str, Any],
    *,
    provider: str,
    account_id: str,
    sender: str,
    received: datetime,
) -> InboundMessage:
    mid = str(message["mid"])[:255]
    text = message.get("text") if isinstance(message.get("text"), str) else None
    reply_to = _dict(message.get("reply_to"))
    context = reply_to.get("mid") if isinstance(reply_to.get("mid"), str) else None

    quick = message.get("quick_reply")
    if isinstance(quick, dict) and quick.get("payload"):
        return InboundMessage(
            kind=InboundMessageKind.INTERACTIVE,
            provider=provider,
            provider_message_id=mid,
            provider_identifier=account_id,
            sender_identifier=sender,
            text=text,
            interactive=InteractiveReply(
                kind="button", payload_id=str(quick["payload"])[:255], title=text
            ),
            context_message_id=context,
            raw_event_type="quick_reply",
            received_at=received,
        )

    attachments = [a for a in message.get("attachments") or [] if isinstance(a, dict)]
    for att in attachments:
        kind = _ATTACHMENT_KINDS.get(str(att.get("type")))
        url = (
            (att.get("payload") or {}).get("url") if isinstance(att.get("payload"), dict) else None
        )
        if kind is not None and isinstance(url, str) and url:
            return InboundMessage(
                kind=kind,
                provider=provider,
                provider_message_id=mid,
                provider_identifier=account_id,
                sender_identifier=sender,
                text=text,
                media=MediaReference(
                    provider_media_id=f"{URL_MEDIA_PREFIX}{url}"[:2000], caption=text
                ),
                context_message_id=context,
                raw_event_type=str(att.get("type")),
                received_at=received,
            )

    if text:
        return InboundMessage(
            kind=InboundMessageKind.TEXT,
            provider=provider,
            provider_message_id=mid,
            provider_identifier=account_id,
            sender_identifier=sender,
            text=text,
            context_message_id=context,
            raw_event_type="text",
            received_at=received,
        )

    # Shares, reels, story mentions, templates: no text and nothing the
    # pipeline can read. The agent sees ``[unsupported:<type>]`` and can say so.
    att_type = str(attachments[0].get("type")) if attachments else "unknown"
    return InboundMessage(
        kind=InboundMessageKind.UNSUPPORTED,
        provider=provider,
        provider_message_id=mid,
        provider_identifier=account_id,
        sender_identifier=sender,
        context_message_id=context,
        raw_event_type=att_type,
        received_at=received,
    )


# ── changes[] ───────────────────────────────────────────────────────────────


def _change_event(change: dict[str, Any], *, provider: str, account_id: str) -> SocialEvent:
    field = change.get("field")
    value = _dict(change.get("value"))
    if field == "comments" and provider == PROVIDER_INSTAGRAM:
        return _comment_event(value, provider=provider, account_id=account_id)
    return SocialEvent("other", provider, account_id, detail=str(field))


def _comment_event(value: dict[str, Any], *, provider: str, account_id: str) -> SocialEvent:
    comment_id = value.get("id")
    author = _dict(value.get("from"))
    author_id = str(author.get("id") or "")
    text = value.get("text") if isinstance(value.get("text"), str) else None
    if not comment_id or not author_id or not text:
        return SocialEvent("other", provider, account_id, detail="comment_incomplete")
    # Req. 4.4: the business's own comments (its replies included) never
    # reach the agent.
    if author_id == account_id:
        return SocialEvent("echo", provider, account_id, detail=f"{COMMENT_PREFIX}{comment_id}")
    ref = f"{COMMENT_PREFIX}{comment_id}"
    media = _dict(value.get("media"))
    return SocialEvent(
        "comment",
        provider,
        account_id,
        inbound=InboundMessage(
            kind=InboundMessageKind.TEXT,
            provider=provider,
            provider_message_id=ref[:255],
            provider_identifier=account_id,
            sender_identifier=author_id,
            sender_name=str(author.get("username")) if author.get("username") else None,
            text=text,
            context_message_id=ref[:160],
            raw_event_type=f"comment:{media.get('media_product_type') or 'FEED'}",
            received_at=datetime.now(UTC),
        ),
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_key(item: dict[str, Any]) -> str:
    for key in item:
        if key not in {"sender", "recipient", "timestamp"}:
            return str(key)
    return "unknown"
