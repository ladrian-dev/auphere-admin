"""WhatsApp/YCloud :class:`ChannelAdapter` implementation.

Outbound calls require the **business phone** (the WABA's E.164 number) as
``from_phone``. The caller (outbound dispatcher) loads the channel row and
passes it in. Channel rows are per-tenant; the adapter instance is global —
the API key is shared at the BSP layer (Auphere is the YCloud customer; each
tenant is a WABA migrated to that BSP). Per-tenant API keys are a
Phase 4+ white-label concern.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar, cast

import structlog

from nexus_channels.base import (
    ChannelType,
    InboundMessage,
    SendResult,
    SendStatus,
)
from nexus_channels.whatsapp_ycloud import webhook_adapter as wa
from nexus_channels.whatsapp_ycloud.ycloud_client import YCloudAPIError, YCloudClient

log = structlog.get_logger(__name__)


class WhatsAppYCloudAdapter:
    """Adapter glueing :mod:`webhook_adapter` (inbound) and
    :class:`YCloudClient` (outbound) into the
    :class:`nexus_channels.base.ChannelAdapter` Protocol.

    One instance per worker process. Outbound calls take ``from_phone``
    explicitly because adapter has no DB visibility.
    """

    channel_type: ClassVar[ChannelType] = "whatsapp"
    provider: ClassVar[str] = "ycloud"

    def __init__(self, client: YCloudClient) -> None:
        self._client = client

    # ── inbound side ─────────────────────────────────────────────────────────

    def parse_inbound(self, raw_event: dict[str, Any]) -> InboundMessage | None:
        return wa.parse_inbound(raw_event)

    def provider_identifier_from_payload(self, raw_event: dict[str, Any]) -> str | None:
        return wa.extract_business_phone(raw_event)

    # ── outbound side ────────────────────────────────────────────────────────

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
        try:
            raw = await self._client.send_text(
                from_phone=from_phone,
                to=recipient,
                body=text,
                context_message_id=context_message_id,
            )
        except YCloudAPIError as exc:
            log.warning(
                "ycloud.send_text.failed",
                tenant_id=str(tenant_id),
                channel_id=str(channel_id),
                status=exc.status_code,
                detail=exc.message,
            )
            raise
        return _to_result(raw)

    async def send_template(
        self,
        *,
        from_phone: str,
        recipient: str,
        template_name: str,
        language: str,
        body_params: list[str] | dict[str, str],
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
        header_params: list[str] | None = None,
        button_params: list[dict[str, Any]] | None = None,
        context_message_id: str | None = None,
    ) -> SendResult:
        try:
            raw = await self._client.send_template(
                from_phone=from_phone,
                to=recipient,
                template_name=template_name,
                language=language,
                body_params=body_params,
                header_params=header_params,
                button_params=button_params,
                context_message_id=context_message_id,
            )
        except YCloudAPIError as exc:
            log.warning(
                "ycloud.send_template.failed",
                tenant_id=str(tenant_id),
                channel_id=str(channel_id),
                template=template_name,
                status=exc.status_code,
                detail=exc.message,
            )
            raise
        return _to_result(raw)

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
        try:
            raw = await self._client.send_interactive(
                from_phone=from_phone,
                to=recipient,
                interactive=interactive,
                context_message_id=context_message_id,
            )
        except YCloudAPIError as exc:
            log.warning(
                "ycloud.send_interactive.failed",
                tenant_id=str(tenant_id),
                channel_id=str(channel_id),
                status=exc.status_code,
                detail=exc.message,
            )
            raise
        return _to_result(raw)

    # ── media outbound ────────────────────────────────────────────────────────
    #
    # Each method takes a ``link`` (public URL — typically a presigned S3
    # URL valid for the few seconds it takes Meta to fetch) and forwards
    # to the YCloud client. Errors propagate as ``YCloudAPIError`` so the
    # outbound dispatcher can classify retry-vs-fail.

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
        try:
            raw = await self._client.send_image(
                from_phone=from_phone,
                to=recipient,
                link=link,
                caption=caption,
                context_message_id=context_message_id,
            )
        except YCloudAPIError as exc:
            log.warning(
                "ycloud.send_image.failed",
                tenant_id=str(tenant_id),
                channel_id=str(channel_id),
                status=exc.status_code,
                detail=exc.message,
            )
            raise
        return _to_result(raw)

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
        try:
            raw = await self._client.send_audio(
                from_phone=from_phone,
                to=recipient,
                link=link,
                context_message_id=context_message_id,
            )
        except YCloudAPIError as exc:
            log.warning(
                "ycloud.send_audio.failed",
                tenant_id=str(tenant_id),
                channel_id=str(channel_id),
                status=exc.status_code,
                detail=exc.message,
            )
            raise
        return _to_result(raw)

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
        try:
            raw = await self._client.send_video(
                from_phone=from_phone,
                to=recipient,
                link=link,
                caption=caption,
                context_message_id=context_message_id,
            )
        except YCloudAPIError as exc:
            log.warning(
                "ycloud.send_video.failed",
                tenant_id=str(tenant_id),
                channel_id=str(channel_id),
                status=exc.status_code,
                detail=exc.message,
            )
            raise
        return _to_result(raw)

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
        try:
            raw = await self._client.send_document(
                from_phone=from_phone,
                to=recipient,
                link=link,
                filename=filename,
                caption=caption,
                context_message_id=context_message_id,
            )
        except YCloudAPIError as exc:
            log.warning(
                "ycloud.send_document.failed",
                tenant_id=str(tenant_id),
                channel_id=str(channel_id),
                status=exc.status_code,
                detail=exc.message,
            )
            raise
        return _to_result(raw)

    async def send_location(
        self,
        *,
        from_phone: str,
        recipient: str,
        latitude: float,
        longitude: float,
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
        name: str | None = None,
        address: str | None = None,
        context_message_id: str | None = None,
    ) -> SendResult:
        try:
            raw = await self._client.send_location(
                from_phone=from_phone,
                to=recipient,
                latitude=latitude,
                longitude=longitude,
                name=name,
                address=address,
                context_message_id=context_message_id,
            )
        except YCloudAPIError as exc:
            log.warning(
                "ycloud.send_location.failed",
                tenant_id=str(tenant_id),
                channel_id=str(channel_id),
                status=exc.status_code,
                detail=exc.message,
            )
            raise
        return _to_result(raw)

    async def send_contacts(
        self,
        *,
        from_phone: str,
        recipient: str,
        contacts: list[dict[str, Any]],
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
        context_message_id: str | None = None,
    ) -> SendResult:
        try:
            raw = await self._client.send_contacts(
                from_phone=from_phone,
                to=recipient,
                contacts=contacts,
                context_message_id=context_message_id,
            )
        except YCloudAPIError as exc:
            log.warning(
                "ycloud.send_contacts.failed",
                tenant_id=str(tenant_id),
                channel_id=str(channel_id),
                status=exc.status_code,
                detail=exc.message,
            )
            raise
        return _to_result(raw)

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
        try:
            raw = await self._client.send_reaction(
                from_phone=from_phone,
                to=recipient,
                target_message_id=target_message_id,
                emoji=emoji,
            )
        except YCloudAPIError as exc:
            log.warning(
                "ycloud.send_reaction.failed",
                tenant_id=str(tenant_id),
                channel_id=str(channel_id),
                status=exc.status_code,
                detail=exc.message,
            )
            raise
        return _to_result(raw)

    async def mark_as_read(
        self,
        *,
        from_phone: str,
        wamid: str,
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
    ) -> None:
        """Best-effort. We don't propagate failures because failing to put
        the two blue checks is never reason to fail the inbound turn."""
        try:
            await self._client.mark_as_read(from_phone=from_phone, wamid=wamid)
        except YCloudAPIError as exc:
            log.info(
                "ycloud.mark_as_read.failed",
                tenant_id=str(tenant_id),
                channel_id=str(channel_id),
                status=exc.status_code,
                detail=exc.message,
            )

    # ── media inbound helpers ─────────────────────────────────────────────────

    async def fetch_media_bytes(self, *, media_id: str) -> tuple[bytes, str | None, str | None]:
        """Two-step media fetch: resolve URL then download bytes.

        Returns ``(content, mime_type, sha256)``. ``mime_type`` from
        ``get_media_url`` is the Meta-side canonical type; the
        content-type from the actual download may differ if YCloud
        proxies through a CDN — we prefer Meta's.
        """
        metadata = await self._client.get_media_url(media_id)
        url = metadata.get("url")
        if not isinstance(url, str) or not url:
            from nexus_channels.whatsapp_ycloud.ycloud_client import YCloudAPIError

            raise YCloudAPIError(404, f"media id {media_id!r} has no resolvable URL")
        content, response_ct = await self._client.download_media(url)
        mime = metadata.get("mime_type") or metadata.get("mimeType") or response_ct
        sha = metadata.get("sha256") or metadata.get("sha_256")
        return (
            content,
            mime if isinstance(mime, str) else None,
            sha if isinstance(sha, str) else None,
        )


def _to_result(raw: dict[str, Any]) -> SendResult:
    """Map YCloud's send response into a :class:`SendResult`.

    YCloud returns ``{"id": "...", "status": "queued|sent|...",
    "whatsappMessage": {"wamid": "..."}}`` — exact fields vary by version. We
    prefer ``wamid`` as the durable id; fall back to the YCloud envelope id.
    """
    whatsapp_block = raw.get("whatsappMessage") or {}
    wamid = whatsapp_block.get("wamid") if isinstance(whatsapp_block, dict) else None
    msg_id_raw = wamid or raw.get("wamid") or raw.get("id") or ""
    if not isinstance(msg_id_raw, str):
        msg_id_raw = str(msg_id_raw)
    status_raw = raw.get("status")
    status: SendStatus
    if isinstance(status_raw, str):
        try:
            status = SendStatus(status_raw)
        except ValueError:
            status = SendStatus.SENT  # YCloud's "accepted" / "submitted" → sent
    else:
        status = SendStatus.SENT
    return SendResult(
        provider_message_id=msg_id_raw,
        status=status,
        cost_usd_estimate=cast(float | None, raw.get("totalPrice")),
        raw=raw,
    )
