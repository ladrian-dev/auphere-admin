"""ChannelAdapter Protocol + canonical inbound/outbound shapes.

The runtime never speaks the wire format of any provider. It speaks
``InboundMessage`` (normalised event) and ``SendResult`` (acknowledgement).
Each adapter under ``nexus_channels.<channel>`` implements this Protocol.

Tenant resolution lives in the webhook layer (FastAPI route), not the adapter
itself, because it needs Redis cache + Postgres SECURITY DEFINER. The adapter
exposes :meth:`provider_identifier_from_payload` so the webhook can extract
the stable identifier from the raw payload before resolving.

This module is the spec from ``architecture/channel-adapters.md`` materialised
in code. Do NOT add channel-specific shapes here — push them into the adapter
package.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

ChannelType = Literal["whatsapp", "instagram", "telegram", "email", "web", "tiktok"]


class InboundMessageKind(str, enum.Enum):
    """Normalised inbound shape.

    Migration 0019 promoted media types from ``UNSUPPORTED`` to first-class
    kinds (the platform now downloads them to S3 and the multimodal pipeline
    processes them). ``UNSUPPORTED`` is reserved for genuinely unknown
    event types we can't or shouldn't translate.
    """

    TEXT = "text"
    INTERACTIVE = "interactive"
    AUDIO = "audio"
    IMAGE = "image"
    DOCUMENT = "document"
    VIDEO = "video"
    STICKER = "sticker"
    LOCATION = "location"
    CONTACTS = "contacts"
    REACTION = "reaction"
    UNSUPPORTED = "unsupported"


class InteractiveReply(BaseModel):
    """User's reply to a button or list interactive message."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["button", "list"]
    payload_id: str
    title: str | None = None
    description: str | None = None


class MediaReference(BaseModel):
    """Reference to a media object on the upstream provider.

    The webhook receives this from Cloud API as ``{id, mime_type, sha256,
    caption?, filename?}``. The platform later resolves ``id`` to a
    download URL (``MetaClient.get_media_url``) and persists the bytes
    to S3.
    """

    model_config = ConfigDict(extra="forbid")

    provider_media_id: str = Field(min_length=1, max_length=255)
    mime_type: str | None = None
    sha256: str | None = None
    caption: str | None = None
    filename: str | None = None
    voice: bool = False  # only meaningful for audio: distinguishes voice notes


class LocationPayload(BaseModel):
    """Inbound location pin."""

    model_config = ConfigDict(extra="forbid")

    latitude: float
    longitude: float
    name: str | None = None
    address: str | None = None


class ReactionPayload(BaseModel):
    """Inbound reaction event. ``emoji`` may be empty when the user *removed*
    a previously-set reaction (Cloud API behaviour)."""

    model_config = ConfigDict(extra="forbid")

    target_message_id: str
    emoji: str = ""


class InboundMessage(BaseModel):
    """Canonical inbound shape passed from the webhook adapter to the worker.

    Note that ``tenant_id`` and ``channel_id`` are NOT populated by the
    adapter itself — the webhook layer resolves them from
    ``provider_identifier`` and stamps them on the event before XADD. The
    adapter only knows wire-level fields.
    """

    model_config = ConfigDict(extra="forbid")

    kind: InboundMessageKind
    provider: str = Field(min_length=1, max_length=40)
    provider_message_id: str = Field(min_length=1, max_length=255)
    provider_identifier: str = Field(
        min_length=1,
        max_length=128,
        description=(
            "Stable identifier of the *receiver* (the business). For WhatsApp "
            "this is the business phone number in E.164 format; for TikTok it "
            "is the Business Account ``business_id``. The webhook uses this to "
            "resolve (provider, identifier) -> tenant_id."
        ),
    )
    # 128, not 40: E.164 phone numbers fit in 16 chars but TikTok's ``open_id``
    # / ``business_id`` are opaque provider strings with no documented bound.
    # The DB columns behind these (``channels.provider_identifier``,
    # ``customers.identifier``) are already String(255), so the Pydantic bound
    # was the only thing that would have rejected a legitimate TikTok event.
    sender_identifier: str = Field(min_length=1, max_length=128)
    sender_name: str | None = None
    text: str | None = None
    interactive: InteractiveReply | None = None
    media: MediaReference | None = None
    location: LocationPayload | None = None
    reaction: ReactionPayload | None = None
    # Quoted reply: when the customer cites a previous message, ``context_
    # message_id`` is the wamid being cited. The pipeline can use it to
    # ground the answer on the original turn.
    context_message_id: str | None = None
    raw_event_type: str | None = None
    received_at: datetime


class ChannelCapabilityError(RuntimeError):
    """The adapter's transport cannot express what the caller asked for.

    Distinct from a transport failure: retrying will never help, and it is
    not the provider rejecting the payload — the capability simply does not
    exist on this channel (e.g. templates on TikTok). The outbound
    dispatcher treats it as terminal and does not burn retry attempts.
    """


class SendStatus(str, enum.Enum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class SendResult(BaseModel):
    """Adapter ack for an outbound send."""

    model_config = ConfigDict(extra="forbid")

    provider_message_id: str
    status: SendStatus
    cost_usd_estimate: float | None = None
    raw: dict[str, Any] | None = None


@runtime_checkable
class ChannelAdapter(Protocol):
    """Implementations live under ``nexus_channels.<channel>``.

    Providers: ``whatsapp_meta``, ``tiktok_bm``. The Protocol is async because
    every real transport involves I/O (HTTP, websocket, etc.).

    Not every provider supports every method. TikTok has no template
    (HSM) equivalent and no business-initiated messaging at all, so its
    adapter raises :class:`ChannelCapabilityError` from ``send_template``
    rather than pretending to succeed. Callers that fan out across channels
    MUST handle that.
    """

    channel_type: ChannelType
    provider: str

    def parse_inbound(self, raw_event: dict[str, Any]) -> InboundMessage | None:
        """Normalise a raw provider payload to ``InboundMessage``.

        Returns ``None`` for events the adapter cannot or should not turn
        into an inbound message (acks, status callbacks, non-message events).
        Returning ``None`` MUST NOT be used to silently drop unknown message
        types — those become :attr:`InboundMessageKind.UNSUPPORTED` so the
        agent sees them and can degrade gracefully.
        """
        ...

    def provider_identifier_from_payload(self, raw_event: dict[str, Any]) -> str | None:
        """Extract the receiver identifier (e.g. business phone E.164) from
        a raw payload, without normalising the rest. The webhook layer needs
        this to resolve the tenant before doing the rest of the work.
        """
        ...

    async def send_text(
        self,
        *,
        recipient: str,
        text: str,
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
    ) -> SendResult: ...

    async def send_template(
        self,
        *,
        recipient: str,
        template_name: str,
        language: str,
        params: dict[str, Any],
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
    ) -> SendResult: ...

    async def send_interactive(
        self,
        *,
        recipient: str,
        payload: dict[str, Any],
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
    ) -> SendResult: ...
