"""Instagram and Messenger :class:`ChannelAdapter`.

One class, two providers (``meta_instagram`` / ``meta_messenger``): both
speak the Messenger Platform Send API on ``graph.facebook.com``. What differs
is the sender id (the professional account id or the Page id), the token
(system-user token or Page token, resolved per channel by the loader) and
the limits (1000 bytes vs 2000 characters per text message).

What Meta does not allow, and how it surfaces
---------------------------------------------
- **No business-initiated messages, no templates.** ``send_template`` raises
  :class:`ChannelCapabilityError`. The dispatcher refuses agent sends outside
  the 24 h window before reaching the adapter.
- **A person after 24 h.** ``human_agent=True`` sends with
  ``messaging_type=MESSAGE_TAG, tag=HUMAN_AGENT`` (7 days). The dispatcher
  only sets it on a message a team member wrote; the agent never can.
- **A private reply** (``context_message_id="comment:<id>"``) goes to
  ``recipient.comment_id``: one message per comment, within 7 days. If the
  channel configures a public reply, it is posted under the comment after
  the private one succeeds.
- **Interactive** degrades to quick replies (13 max, 20-char titles) with the
  body as text; what cannot be expressed goes out as text.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import structlog

from nexus_channels.base import ChannelCapabilityError, ChannelType, SendResult, SendStatus
from nexus_channels.meta_social.graph import MetaSocialClient
from nexus_channels.meta_social.text import INSTAGRAM_MAX_BYTES, MESSENGER_MAX_CHARS, split_message
from nexus_channels.meta_social.webhook_adapter import (
    COMMENT_PREFIX,
    PROVIDER_INSTAGRAM,
    PROVIDER_MESSENGER,
    URL_MEDIA_PREFIX,
)

log = structlog.get_logger(__name__)

QUICK_REPLY_MAX = 13
QUICK_REPLY_TITLE_MAX = 20
MEDIA_MAX_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SendContext:
    """What a send needs from the channel row, resolved per channel."""

    account_id: str
    token: str
    public_comment_reply: str | None = None


class SendContextLoader(Protocol):
    async def __call__(self, *, tenant_id: uuid.UUID, channel_id: uuid.UUID) -> SendContext: ...


class MetaSocialChannelAdapter:
    channel_type: ChannelType
    provider: str

    def __init__(
        self,
        client: MetaSocialClient,
        *,
        provider: str,
        context_loader: SendContextLoader,
    ) -> None:
        if provider not in {PROVIDER_INSTAGRAM, PROVIDER_MESSENGER}:
            raise ValueError(f"unknown meta_social provider: {provider}")
        self._client = client
        self.provider = provider
        self.channel_type = "instagram" if provider == PROVIDER_INSTAGRAM else "messenger"
        self._load = context_loader

    @property
    def is_instagram(self) -> bool:
        return self.provider == PROVIDER_INSTAGRAM

    def _chunks(self, text: str) -> list[str]:
        if self.is_instagram:
            return split_message(text, max_bytes=INSTAGRAM_MAX_BYTES)
        return split_message(text, max_chars=MESSENGER_MAX_CHARS)

    # ── outbound ────────────────────────────────────────────────────────

    async def send_text(
        self,
        *,
        from_phone: str,
        recipient: str,
        text: str,
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
        context_message_id: str | None = None,
        human_agent: bool = False,
    ) -> SendResult:
        ctx = await self._load(tenant_id=tenant_id, channel_id=channel_id)
        if context_message_id and context_message_id.startswith(COMMENT_PREFIX):
            return await self._private_reply(
                ctx,
                comment_id=context_message_id[len(COMMENT_PREFIX) :],
                text=text,
                channel_id=channel_id,
            )
        chunks = self._chunks(text) or [text]
        result: SendResult | None = None
        for chunk in chunks:
            result = await self._send(
                ctx,
                recipient={"id": recipient},
                message={"text": chunk},
                human_agent=human_agent,
                reply_to=context_message_id if result is None else None,
            )
        assert result is not None
        return result

    async def send_interactive(
        self,
        *,
        from_phone: str,
        recipient: str,
        interactive: dict[str, Any],
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
        context_message_id: str | None = None,
        human_agent: bool = False,
    ) -> SendResult:
        body, options = _quick_replies_from_interactive(interactive)
        if not options:
            return await self.send_text(
                from_phone=from_phone,
                recipient=recipient,
                text=body,
                tenant_id=tenant_id,
                channel_id=channel_id,
                context_message_id=context_message_id,
                human_agent=human_agent,
            )
        ctx = await self._load(tenant_id=tenant_id, channel_id=channel_id)
        chunks = self._chunks(body) or ["…"]
        # Long bodies go first as plain text; the quick replies ride on the
        # last chunk, which is the one the person answers.
        for chunk in chunks[:-1]:
            await self._send(
                ctx, recipient={"id": recipient}, message={"text": chunk}, human_agent=human_agent
            )
        return await self._send(
            ctx,
            recipient={"id": recipient},
            message={"text": chunks[-1], "quick_replies": options},
            human_agent=human_agent,
        )

    async def send_template(self, **_: Any) -> SendResult:
        raise ChannelCapabilityError(
            "Instagram and Messenger have no message templates for this use case: "
            "the person has to write first."
        )

    async def send_image(
        self, *, recipient: str, link: str, caption: str | None = None, **kw: Any
    ) -> SendResult:
        return await self._send_media(
            "image", recipient=recipient, link=link, caption=caption, **kw
        )

    async def send_video(
        self, *, recipient: str, link: str, caption: str | None = None, **kw: Any
    ) -> SendResult:
        return await self._send_media(
            "video", recipient=recipient, link=link, caption=caption, **kw
        )

    async def send_audio(self, *, recipient: str, link: str, **kw: Any) -> SendResult:
        return await self._send_media("audio", recipient=recipient, link=link, caption=None, **kw)

    async def send_document(
        self,
        *,
        recipient: str,
        link: str,
        filename: str | None = None,
        caption: str | None = None,
        **kw: Any,
    ) -> SendResult:
        return await self._send_media("file", recipient=recipient, link=link, caption=caption, **kw)

    async def send_reaction(
        self,
        *,
        from_phone: str,
        recipient: str,
        target_message_id: str,
        emoji: str,
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
    ) -> SendResult:
        if not self.is_instagram:
            raise ChannelCapabilityError("Messenger reactions are not sent by the business.")
        ctx = await self._load(tenant_id=tenant_id, channel_id=channel_id)
        body: dict[str, Any] = {
            "recipient": {"id": recipient},
            "sender_action": "unreact" if not emoji else "react",
            "payload": {"message_id": target_message_id, "reaction": "love"},
        }
        raw = await self._client.send(sender_id=ctx.account_id, access_token=ctx.token, body=body)
        return _to_result(raw, fallback_id=f"reaction:{target_message_id}")

    async def mark_as_read(self, **_: Any) -> None:
        """Read receipts need the person's id, not the message's; the webhook
        never asks for them on these channels."""
        return None

    # ── inbound helpers ─────────────────────────────────────────────────

    async def fetch_media_bytes(
        self,
        *,
        media_id: str,
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID | None = None,
    ) -> tuple[bytes, str | None, str | None]:
        if not media_id.startswith(URL_MEDIA_PREFIX):
            raise ValueError("meta_social media ids are CDN URLs")
        content, mime = await self._client.download_attachment(
            media_id[len(URL_MEDIA_PREFIX) :], max_bytes=MEDIA_MAX_BYTES
        )
        return content, mime, None

    async def fetch_profile(
        self, *, recipient: str, tenant_id: uuid.UUID, channel_id: uuid.UUID
    ) -> str | None:
        """The person's display name (Business Asset User Profile Access).
        ``None`` on any failure: the inbox shows a generic name instead."""
        try:
            ctx = await self._load(tenant_id=tenant_id, channel_id=channel_id)
            if self.is_instagram:
                data = await self._client.user_profile(
                    user_id=recipient, access_token=ctx.token, fields="name,username"
                )
                name = data.get("name") or data.get("username")
            else:
                data = await self._client.user_profile(
                    user_id=recipient, access_token=ctx.token, fields="first_name,last_name"
                )
                name = " ".join(p for p in (data.get("first_name"), data.get("last_name")) if p)
        except Exception as exc:
            log.info(
                "meta_social.profile.unavailable", provider=self.provider, error=type(exc).__name__
            )
            return None
        return str(name)[:255] if name else None

    # ── internals ───────────────────────────────────────────────────────

    async def _send(
        self,
        ctx: SendContext,
        *,
        recipient: dict[str, str],
        message: dict[str, Any],
        human_agent: bool = False,
        reply_to: str | None = None,
    ) -> SendResult:
        if reply_to and self.is_instagram and not reply_to.startswith(COMMENT_PREFIX):
            message = {**message, "reply_to": {"mid": reply_to}}
        body: dict[str, Any] = {"recipient": recipient, "message": message}
        if human_agent:
            body["messaging_type"] = "MESSAGE_TAG"
            body["tag"] = "HUMAN_AGENT"
        else:
            body["messaging_type"] = "RESPONSE"
        raw = await self._client.send(sender_id=ctx.account_id, access_token=ctx.token, body=body)
        return _to_result(raw)

    async def _send_media(
        self,
        kind: str,
        *,
        recipient: str,
        link: str,
        caption: str | None,
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
        human_agent: bool = False,
        **_: Any,
    ) -> SendResult:
        ctx = await self._load(tenant_id=tenant_id, channel_id=channel_id)
        result = await self._send(
            ctx,
            recipient={"id": recipient},
            message={"attachment": {"type": kind, "payload": {"url": link, "is_reusable": False}}},
            human_agent=human_agent,
        )
        # A caption is its own message: neither API carries text with an
        # attachment.
        for chunk in self._chunks(caption or ""):
            await self._send(
                ctx, recipient={"id": recipient}, message={"text": chunk}, human_agent=human_agent
            )
        return result

    async def _private_reply(
        self, ctx: SendContext, *, comment_id: str, text: str, channel_id: uuid.UUID
    ) -> SendResult:
        if not self.is_instagram:
            raise ChannelCapabilityError("Private replies are only wired for Instagram comments.")
        # One message per comment: what does not fit is cut, not split.
        chunk = (self._chunks(text) or [text])[0]
        raw = await self._client.send(
            sender_id=ctx.account_id,
            access_token=ctx.token,
            body={"recipient": {"comment_id": comment_id}, "message": {"text": chunk}},
        )
        result = _to_result(raw)
        if ctx.public_comment_reply:
            try:
                await self._client.reply_comment(
                    comment_id=comment_id, access_token=ctx.token, message=ctx.public_comment_reply
                )
            except Exception as exc:
                # The private reply already reached the person; a missing
                # public line under the post is not worth failing the send.
                log.warning(
                    "meta_social.public_reply.failed",
                    channel_id=str(channel_id),
                    error=type(exc).__name__,
                )
        return result


def _quick_replies_from_interactive(block: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    """WhatsApp-shaped ``interactive`` block → (body text, quick replies).

    The dispatcher builds the block once (``_to_meta_interactive``); buttons
    and list rows become quick replies, anything else (product cards, CTA
    URLs) becomes text with the body.
    """
    body = str(((block.get("body") or {}).get("text")) or "")
    action = block.get("action") or {}
    options: list[tuple[str, str]] = []
    for button in action.get("buttons") or []:
        reply = button.get("reply") or {}
        if reply.get("id") and reply.get("title"):
            options.append((str(reply["id"]), str(reply["title"])))
    for section in action.get("sections") or []:
        for row in section.get("rows") or []:
            if row.get("id") and row.get("title"):
                options.append((str(row["id"]), str(row["title"])))
    if block.get("type") == "cta_url":
        params = action.get("parameters") or {}
        url = params.get("url")
        label = params.get("display_text")
        if url:
            body = f"{body}\n\n{label + ': ' if label else ''}{url}".strip()
    quick = [
        {
            "content_type": "text",
            "title": title[:QUICK_REPLY_TITLE_MAX].strip(),
            "payload": pid[:1000],
        }
        for pid, title in options[:QUICK_REPLY_MAX]
    ]
    return body, quick


def _to_result(raw: dict[str, Any], *, fallback_id: str = "") -> SendResult:
    mid = raw.get("message_id") or fallback_id
    return SendResult(provider_message_id=str(mid), status=SendStatus.SENT, raw=raw)
