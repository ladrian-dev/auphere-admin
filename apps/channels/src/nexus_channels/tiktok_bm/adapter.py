"""TikTok Business Messaging :class:`ChannelAdapter`.

Same Protocol, same runtime path, a much narrower transport than WhatsApp.
The adapter is stateless past construction; per-tenant data (access token,
``business_id``) is resolved through a ``CredentialsLoader`` callback so the
channels package stays free of DB dependencies and tests can inject
in-memory tokens.

What TikTok cannot do, and how that surfaces
--------------------------------------------
This is the first channel in Nexus that is *less* capable than WhatsApp, so
the gaps are explicit rather than silent:

- **No templates / no business-initiated messages.** There is no HSM
  equivalent and no way to open a conversation. ``send_template`` raises
  :class:`ChannelCapabilityError`; the broadcast path is blocked upstream so
  it never gets this far in normal operation.
- **No interactive components.** ``send_interactive`` degrades to the
  payload's body text instead of failing — a customer reading the options as
  prose is a far better outcome than silence.
- **No reactions, no audio/video/document sends.** All raise
  :class:`ChannelCapabilityError`.
- **Images go by id, not URL.** The dispatcher hands us a presigned S3 link;
  we fetch it and upload the bytes to TikTok, because TikTok's send call only
  accepts an ``image_id`` it issued itself.

Addressing
----------
The dispatcher passes ``from_phone`` (the channel's ``provider_identifier``)
and ``recipient`` (the customer identifier). For TikTok those are the
``business_id`` and the sender's ``open_id`` — the keyword name is a WhatsApp
holdover kept for dispatcher compatibility, not a claim about the value.

The value that actually routes an outbound send is neither of those: it is
the ``conversation_id``, which the inbound parser stores on the message's
``context_message_id``. The dispatcher forwards that field verbatim, so it
arrives here as ``context_message_id``.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar, Protocol

import httpx
import structlog

from nexus_channels.base import (
    ChannelCapabilityError,
    ChannelType,
    InboundMessage,
    SendResult,
    SendStatus,
)
from nexus_channels.tiktok_bm import webhook_adapter as tt
from nexus_channels.tiktok_bm.exceptions import TikTokAPIError
from nexus_channels.tiktok_bm.tiktok_client import TikTokClient

log = structlog.get_logger(__name__)


class CredentialsLoader(Protocol):
    """Callback the caller wires up to resolve per-tenant TikTok credentials.

    Returns ``(business_id, access_token)``. In production this dispatches to
    :class:`nexus_channels.tiktok_bm.credentials.TikTokCredentialsRepository`
    after the request opens a tenant-scoped session.
    """

    async def __call__(self, *, tenant_id: uuid.UUID) -> tuple[str, str]: ...


class TikTokChannelAdapter:
    """Implements the :class:`nexus_channels.base.ChannelAdapter` contract.

    Inbound: delegates to :mod:`webhook_adapter` (the route verifies the
    signature before reaching us).

    Outbound: each ``send_*`` resolves the tenant's ``(business_id,
    access_token)``, then calls :class:`TikTokClient`. Errors propagate as
    :class:`TikTokAPIError` subclasses so the outbound dispatcher can
    classify retry-vs-fail.
    """

    channel_type: ClassVar[ChannelType] = "tiktok"
    provider: ClassVar[str] = "tiktok"

    def __init__(
        self,
        client: TikTokClient,
        *,
        credentials_loader: CredentialsLoader,
        media_timeout: float = 20.0,
    ) -> None:
        self._client = client
        self._load_credentials = credentials_loader
        self._media_timeout = media_timeout

    # ── inbound ────────────────────────────────────────────────────────────

    def parse_inbound(self, raw_event: dict[str, Any]) -> InboundMessage | None:
        return tt.parse_inbound(raw_event)

    def provider_identifier_from_payload(self, raw_event: dict[str, Any]) -> str | None:
        return tt.extract_business_id(raw_event)

    # ── outbound: text ─────────────────────────────────────────────────────

    async def send_text(
        self,
        *,
        from_phone: str,
        recipient: str,
        text: str,
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
        context_message_id: str | None = None,
    ) -> SendResult:
        business_id, token = await self._load_credentials(tenant_id=tenant_id)
        conversation_id = self._require_conversation(
            context_message_id,
            tenant_id=tenant_id,
            channel_id=channel_id,
        )
        try:
            raw = await self._client.send_text(
                access_token=token,
                business_id=business_id,
                conversation_id=conversation_id,
                text=text,
            )
        except TikTokAPIError as exc:
            self._log_failure("send_text", exc, tenant_id=tenant_id, channel_id=channel_id)
            raise
        return _to_result(raw)

    # ── outbound: image ────────────────────────────────────────────────────

    async def send_image(
        self,
        *,
        from_phone: str,
        recipient: str,
        link: str,
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
        caption: str | None = None,
        context_message_id: str | None = None,
    ) -> SendResult:
        """Fetch the presigned S3 object, upload it to TikTok, then send.

        Three network hops for one image is unavoidable: TikTok will not
        accept a foreign URL, so the bytes have to pass through us.
        """
        business_id, token = await self._load_credentials(tenant_id=tenant_id)
        conversation_id = self._require_conversation(
            context_message_id,
            tenant_id=tenant_id,
            channel_id=channel_id,
        )

        content, mime_type = await self._fetch_link(link)
        try:
            upload = await self._client.upload_image(
                access_token=token,
                business_id=business_id,
                content=content,
                mime_type=mime_type or "image/jpeg",
            )
            image_id = upload.get("image_id") or upload.get("imageId")
            if not isinstance(image_id, str) or not image_id:
                raise TikTokAPIError("image upload returned no image_id", status_code=200)
            raw = await self._client.send_image(
                access_token=token,
                business_id=business_id,
                conversation_id=conversation_id,
                image_id=image_id,
            )
        except TikTokAPIError as exc:
            self._log_failure("send_image", exc, tenant_id=tenant_id, channel_id=channel_id)
            raise

        result = _to_result(raw)
        # TikTok has no caption field on image messages. Sending the caption
        # as a follow-up text keeps the information rather than dropping it;
        # a failure here must not undo the image that already landed.
        if caption:
            try:
                await self._client.send_text(
                    access_token=token,
                    business_id=business_id,
                    conversation_id=conversation_id,
                    text=caption,
                )
            except TikTokAPIError as exc:
                log.warning(
                    "tiktok.send_image.caption_failed",
                    tenant_id=str(tenant_id),
                    channel_id=str(channel_id),
                    code=exc.code,
                    detail=exc.message,
                )
        return result

    # ── outbound: degraded ─────────────────────────────────────────────────

    async def send_interactive(
        self,
        *,
        from_phone: str,
        recipient: str,
        interactive: dict[str, Any],
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
        context_message_id: str | None = None,
    ) -> SendResult:
        """Flatten to text. ``ucm-schema``'s ``degrade()`` normally prevents
        interactive payloads from reaching a TikTok channel at all; this is
        the backstop for any caller that bypasses the formatter."""
        body = _flatten_interactive(interactive)
        if not body:
            raise ChannelCapabilityError(
                "TikTok cannot render interactive components and the payload "
                "carried no text to fall back to"
            )
        log.info(
            "tiktok.send_interactive.degraded_to_text",
            tenant_id=str(tenant_id),
            channel_id=str(channel_id),
        )
        return await self.send_text(
            from_phone=from_phone,
            recipient=recipient,
            text=body,
            tenant_id=tenant_id,
            channel_id=channel_id,
            context_message_id=context_message_id,
        )

    # ── outbound: unsupported ──────────────────────────────────────────────

    async def send_template(
        self,
        *,
        from_phone: str,
        recipient: str,
        template_name: str,
        language: str,
        params: dict[str, Any],
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
        context_message_id: str | None = None,
    ) -> SendResult:
        raise ChannelCapabilityError(
            "TikTok Business Messaging has no template equivalent and forbids "
            "business-initiated messages; a template send can never succeed "
            f"on this channel (attempted: {template_name!r})"
        )

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
        raise ChannelCapabilityError("TikTok Business Messaging does not support reactions")

    async def send_audio(
        self,
        *,
        from_phone: str,
        recipient: str,
        link: str,
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
        context_message_id: str | None = None,
    ) -> SendResult:
        raise ChannelCapabilityError("TikTok Business Messaging does not support audio messages")

    async def send_video(
        self,
        *,
        from_phone: str,
        recipient: str,
        link: str,
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
        caption: str | None = None,
        context_message_id: str | None = None,
    ) -> SendResult:
        raise ChannelCapabilityError("TikTok Business Messaging does not support video sends")

    async def send_document(
        self,
        *,
        from_phone: str,
        recipient: str,
        link: str,
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
        filename: str | None = None,
        caption: str | None = None,
        context_message_id: str | None = None,
    ) -> SendResult:
        raise ChannelCapabilityError("TikTok Business Messaging does not support document sends")

    async def mark_as_read(
        self,
        *,
        from_phone: str,
        wamid: str,
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
    ) -> None:
        """No-op. TikTok exposes no read-receipt write; the runtime calls
        this unconditionally after an inbound turn, so silently doing
        nothing is the correct behaviour rather than an error."""
        return None

    # ── media inbound ──────────────────────────────────────────────────────

    async def fetch_media_bytes(
        self,
        *,
        media_id: str,
        tenant_id: uuid.UUID,
    ) -> tuple[bytes, str | None, str | None]:
        """Download an inbound image. Returns ``(content, mime_type, sha256)``.

        ``sha256`` is always ``None`` — TikTok does not publish a checksum,
        and inventing one would defeat the dedupe it is meant to serve.
        Signature matches the Meta adapter so the inbound media pipeline
        stays provider-agnostic.
        """
        business_id, token = await self._load_credentials(tenant_id=tenant_id)
        content, mime = await self._client.download_image(
            access_token=token,
            business_id=business_id,
            image_id=media_id,
        )
        return content, mime, None

    # ── helpers ────────────────────────────────────────────────────────────

    def _require_conversation(
        self,
        conversation_id: str | None,
        *,
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
    ) -> str:
        if conversation_id:
            return conversation_id
        log.warning(
            "tiktok.send.missing_conversation_id",
            tenant_id=str(tenant_id),
            channel_id=str(channel_id),
        )
        raise ChannelCapabilityError(
            "TikTok sends require a conversation_id opened by the user; the "
            "outbound row carried none (business-initiated messaging is not "
            "possible on this channel)"
        )

    async def _fetch_link(self, link: str) -> tuple[bytes, str | None]:
        async with httpx.AsyncClient(timeout=self._media_timeout) as client:
            resp = await client.get(link)
            resp.raise_for_status()
            return resp.content, resp.headers.get("content-type")

    def _log_failure(
        self,
        op: str,
        exc: TikTokAPIError,
        *,
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
    ) -> None:
        log.warning(
            f"tiktok.{op}.failed",
            tenant_id=str(tenant_id),
            channel_id=str(channel_id),
            status=exc.status_code,
            code=exc.code,
            request_id=exc.request_id,
            detail=exc.message,
        )


# ── module helpers ──────────────────────────────────────────────────────────


def _to_result(raw: dict[str, Any]) -> SendResult:
    """Map a Business Messaging send response into a :class:`SendResult`.

    Status defaults to ``SENT``: the send call only confirms acceptance, and
    TikTok reports real delivery through separate webhook events.
    """
    message_id = raw.get("message_id") or raw.get("messageId") or ""
    return SendResult(
        provider_message_id=str(message_id),
        status=SendStatus.SENT,
        # TikTok does not bill per message, so there is nothing to estimate.
        cost_usd_estimate=None,
        raw=raw,
    )


def _flatten_interactive(interactive: dict[str, Any]) -> str:
    """Best-effort prose rendering of an interactive payload.

    Deliberately simple: it exists so a mis-routed payload still says
    something useful, not to be a second rendering engine. The real
    degradation lives in ``ucm-schema``.
    """
    parts: list[str] = []

    body = interactive.get("body")
    if isinstance(body, dict):
        text = body.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    elif isinstance(body, str) and body:
        parts.append(body)

    for key in ("text", "caption"):
        value = interactive.get(key)
        if isinstance(value, str) and value and value not in parts:
            parts.append(value)

    options = _collect_option_titles(interactive)
    if options:
        parts.append("\n".join(f"- {title}" for title in options))

    return "\n\n".join(parts).strip()


def _collect_option_titles(interactive: dict[str, Any]) -> list[str]:
    """Pull button / list-row titles out of the common payload shapes."""
    titles: list[str] = []
    action = interactive.get("action")
    if not isinstance(action, dict):
        return titles

    for button in action.get("buttons") or []:
        if not isinstance(button, dict):
            continue
        reply = button.get("reply")
        source = reply if isinstance(reply, dict) else button
        title = source.get("title")
        if isinstance(title, str) and title:
            titles.append(title)

    for section in action.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for row in section.get("rows") or []:
            if not isinstance(row, dict):
                continue
            title = row.get("title")
            if isinstance(title, str) and title:
                titles.append(title)

    return titles
