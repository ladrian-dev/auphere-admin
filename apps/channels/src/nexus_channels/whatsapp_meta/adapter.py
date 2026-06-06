"""WhatsApp Cloud API :class:`ChannelAdapter` — direct Meta integration.

Replaces :class:`nexus_channels.whatsapp_ycloud.adapter.WhatsAppYCloudAdapter`
for tenants migrated to the Auphere-owned Meta App. Same Protocol — same
runtime path — different transport.

The adapter is stateless past construction. Per-tenant data (BISUAT,
``phone_number_id``) is looked up via a ``CredentialsLoader`` callback
supplied by the caller. This keeps the channels package free of DB deps
and lets tests inject in-memory tokens.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar, Protocol, cast

import structlog

from nexus_channels.base import (
    ChannelType,
    InboundMessage,
    SendResult,
    SendStatus,
)
from nexus_channels.whatsapp_meta import webhook_adapter as wa
from nexus_channels.whatsapp_meta.exceptions import MetaAPIError
from nexus_channels.whatsapp_meta.meta_client import MetaClient

log = structlog.get_logger(__name__)


class CredentialsLoader(Protocol):
    """Callback the caller wires up to resolve per-tenant Meta credentials.

    Returning a tuple instead of a dict because the adapter only ever needs
    the two fields and a flat tuple is the cheapest shape to type. In
    production this dispatches to
    :class:`nexus_channels.whatsapp_meta.credentials.MetaCredentialsRepository`
    after the request opens a tenant-scoped session.
    """

    async def __call__(self, *, tenant_id: uuid.UUID) -> tuple[str, str]:
        """Return ``(phone_number_id, bisuat)`` for the active tenant."""
        ...


class MetaChannelAdapter:
    """Implements :class:`nexus_channels.base.ChannelAdapter`.

    Inbound: delegates to :mod:`webhook_adapter` (the route already does
    signature verification before reaching us).

    Outbound: each ``send_*`` method resolves the tenant's
    ``(phone_number_id, bisuat)`` via the configured ``CredentialsLoader``,
    then calls into :class:`MetaClient`. Errors propagate as
    :class:`MetaAPIError` subclasses — the outbound dispatcher classifies
    retry-vs-fail.
    """

    channel_type: ClassVar[ChannelType] = "whatsapp"
    provider: ClassVar[str] = "meta"

    def __init__(
        self,
        client: MetaClient,
        *,
        credentials_loader: CredentialsLoader,
    ) -> None:
        self._client = client
        self._load_credentials = credentials_loader

    # ── inbound ────────────────────────────────────────────────────────────

    def parse_inbound(self, raw_event: dict[str, Any]) -> InboundMessage | None:
        return wa.parse_inbound(raw_event)

    def provider_identifier_from_payload(self, raw_event: dict[str, Any]) -> str | None:
        return wa.extract_business_phone(raw_event)

    # ── outbound: text / template / interactive ────────────────────────────

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
        pnid, token = await self._load_credentials(tenant_id=tenant_id)
        try:
            raw = await self._client.send_text(
                phone_number_id=pnid,
                access_token=token,
                to=recipient,
                body=text,
                context_message_id=context_message_id,
            )
        except MetaAPIError as exc:
            log.warning(
                "meta.send_text.failed",
                tenant_id=str(tenant_id),
                channel_id=str(channel_id),
                status=exc.status_code,
                code=exc.code,
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
        params: dict[str, Any],
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
        context_message_id: str | None = None,
    ) -> SendResult:
        """Adapter signature matches the Protocol: a single ``params`` dict.

        ``params`` accepts three optional keys for backward-compat with the
        YCloud-era callers:

        * ``"body"`` — ``list[str]`` (positional) or ``dict[str, str]`` (named).
        * ``"header"`` — ``list[str]`` of header text parameters.
        * ``"buttons"`` — ``list[dict]`` of button component overrides.

        If a caller already builds a Cloud API ``components`` payload
        manually, pass ``params={"components": [...]}`` and the rest is
        forwarded verbatim.
        """
        pnid, token = await self._load_credentials(tenant_id=tenant_id)
        components = _build_template_components(params)
        try:
            raw = await self._client.send_template(
                phone_number_id=pnid,
                access_token=token,
                to=recipient,
                template_name=template_name,
                language=language,
                components=components,
                context_message_id=context_message_id,
            )
        except MetaAPIError as exc:
            log.warning(
                "meta.send_template.failed",
                tenant_id=str(tenant_id),
                channel_id=str(channel_id),
                template=template_name,
                status=exc.status_code,
                code=exc.code,
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
        # Keyword is ``interactive`` (not ``payload``) to match the de-facto
        # runtime contract: the outbound dispatcher and the YCloud adapter
        # both speak ``interactive=``. The base.py Protocol still says
        # ``payload`` — that Protocol predates the dispatcher and is stale;
        # neither WhatsApp adapter conforms to it (both add ``from_phone``).
        pnid, token = await self._load_credentials(tenant_id=tenant_id)
        try:
            raw = await self._client.send_interactive(
                phone_number_id=pnid,
                access_token=token,
                to=recipient,
                interactive=interactive,
                context_message_id=context_message_id,
            )
        except MetaAPIError as exc:
            log.warning(
                "meta.send_interactive.failed",
                tenant_id=str(tenant_id),
                channel_id=str(channel_id),
                status=exc.status_code,
                code=exc.code,
                detail=exc.message,
            )
            raise
        return _to_result(raw)

    # ── outbound: media ────────────────────────────────────────────────────

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
        return await self._send_media(
            media_type="image",
            from_phone=from_phone,
            recipient=recipient,
            link=link,
            caption=caption,
            filename=None,
            tenant_id=tenant_id,
            channel_id=channel_id,
            context_message_id=context_message_id,
        )

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
        return await self._send_media(
            media_type="audio",
            from_phone=from_phone,
            recipient=recipient,
            link=link,
            caption=None,
            filename=None,
            tenant_id=tenant_id,
            channel_id=channel_id,
            context_message_id=context_message_id,
        )

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
        return await self._send_media(
            media_type="video",
            from_phone=from_phone,
            recipient=recipient,
            link=link,
            caption=caption,
            filename=None,
            tenant_id=tenant_id,
            channel_id=channel_id,
            context_message_id=context_message_id,
        )

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
        return await self._send_media(
            media_type="document",
            from_phone=from_phone,
            recipient=recipient,
            link=link,
            caption=caption,
            filename=filename,
            tenant_id=tenant_id,
            channel_id=channel_id,
            context_message_id=context_message_id,
        )

    async def _send_media(
        self,
        *,
        media_type: str,
        from_phone: str,
        recipient: str,
        link: str,
        caption: str | None,
        filename: str | None,
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
        context_message_id: str | None,
    ) -> SendResult:
        pnid, token = await self._load_credentials(tenant_id=tenant_id)
        try:
            raw = await self._client.send_media(
                phone_number_id=pnid,
                access_token=token,
                to=recipient,
                media_type=media_type,
                link=link,
                caption=caption,
                filename=filename,
                context_message_id=context_message_id,
            )
        except MetaAPIError as exc:
            log.warning(
                f"meta.send_{media_type}.failed",
                tenant_id=str(tenant_id),
                channel_id=str(channel_id),
                status=exc.status_code,
                code=exc.code,
                detail=exc.message,
            )
            raise
        return _to_result(raw)

    # ── outbound: reaction / mark-as-read ──────────────────────────────────

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
        pnid, token = await self._load_credentials(tenant_id=tenant_id)
        try:
            raw = await self._client.send_reaction(
                phone_number_id=pnid,
                access_token=token,
                to=recipient,
                target_message_id=target_message_id,
                emoji=emoji,
            )
        except MetaAPIError as exc:
            log.warning(
                "meta.send_reaction.failed",
                tenant_id=str(tenant_id),
                channel_id=str(channel_id),
                status=exc.status_code,
                code=exc.code,
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
        """Best-effort. Failing to put the two blue checks never blocks an
        inbound turn — same contract as the YCloud adapter."""
        try:
            pnid, token = await self._load_credentials(tenant_id=tenant_id)
            await self._client.mark_as_read(
                phone_number_id=pnid,
                access_token=token,
                message_id=wamid,
            )
        except MetaAPIError as exc:
            log.info(
                "meta.mark_as_read.failed",
                tenant_id=str(tenant_id),
                channel_id=str(channel_id),
                status=exc.status_code,
                code=exc.code,
            )

    # ── media inbound helpers ──────────────────────────────────────────────

    async def fetch_media_bytes(
        self,
        *,
        media_id: str,
        tenant_id: uuid.UUID,
    ) -> tuple[bytes, str | None, str | None]:
        """Two-step media fetch: resolve URL, then download bytes.

        Returns ``(content, mime_type, sha256)``. Used by the inbound media
        pipeline before persisting to S3.
        """
        _, token = await self._load_credentials(tenant_id=tenant_id)
        metadata = await self._client.get_media_url(media_id=media_id, access_token=token)
        url = metadata.get("url")
        if not isinstance(url, str) or not url:
            raise MetaAPIError(
                f"media id {media_id!r} has no resolvable URL",
                status_code=404,
            )
        content, response_ct = await self._client.download_media(url=url, access_token=token)
        mime = metadata.get("mime_type") or response_ct
        sha = metadata.get("sha256")
        return (
            content,
            mime if isinstance(mime, str) else None,
            sha if isinstance(sha, str) else None,
        )


# ── helpers ────────────────────────────────────────────────────────────────


def _to_result(raw: dict[str, Any]) -> SendResult:
    """Map Meta's ``/messages`` response into a :class:`SendResult`.

    Cloud API returns ``{"messaging_product": "whatsapp", "contacts":[...],
    "messages":[{"id":"wamid.HBgL...", "message_status": "..."}]}`` — extract
    the wamid as the durable id; status defaults to ``SENT`` because
    /messages itself only confirms acceptance (real delivery comes via the
    status callback webhook).
    """
    messages = raw.get("messages") or []
    if isinstance(messages, list) and messages and isinstance(messages[0], dict):
        wamid = str(messages[0].get("id") or "")
        status_raw = messages[0].get("message_status")
    else:
        wamid = ""
        status_raw = None
    if isinstance(status_raw, str):
        try:
            status = SendStatus(status_raw)
        except ValueError:
            status = SendStatus.SENT
    else:
        status = SendStatus.SENT
    return SendResult(
        provider_message_id=wamid,
        status=status,
        cost_usd_estimate=cast(float | None, raw.get("pricing", {}).get("total")) if isinstance(raw.get("pricing"), dict) else None,
        raw=raw,
    )


def _build_template_components(params: dict[str, Any]) -> list[dict[str, Any]]:
    """Build Cloud API ``components`` from the YCloud-era ``params`` shape.

    Supported keys (all optional):

    - ``components`` — escape hatch: passed through verbatim.
    - ``header`` — ``list[str]`` of text parameters for the HEADER component.
    - ``body`` — ``list[str]`` positional or ``dict[str, str]`` named.
    - ``buttons`` — ``list[dict]`` of pre-built button components.

    Empty/missing keys produce no component.
    """
    if "components" in params and isinstance(params["components"], list):
        return cast(list[dict[str, Any]], params["components"])

    components: list[dict[str, Any]] = []

    header = params.get("header")
    if isinstance(header, list) and header:
        components.append(
            {
                "type": "header",
                "parameters": [{"type": "text", "text": str(v)} for v in header],
            }
        )

    body = params.get("body")
    body_parameters: list[dict[str, Any]] | None = None
    if isinstance(body, dict):
        body_parameters = [
            {"type": "text", "parameter_name": k, "text": str(v)} for k, v in body.items()
        ]
    elif isinstance(body, list):
        body_parameters = [{"type": "text", "text": str(v)} for v in body]
    if body_parameters:
        components.append({"type": "body", "parameters": body_parameters})

    buttons = params.get("buttons")
    if isinstance(buttons, list):
        for idx, btn in enumerate(buttons):
            if not isinstance(btn, dict):
                continue
            components.append(
                {
                    "type": "button",
                    "sub_type": btn.get("sub_type", "quick_reply"),
                    "index": str(idx),
                    "parameters": btn.get("parameters", []),
                }
            )

    return components
