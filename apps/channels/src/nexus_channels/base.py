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

ChannelType = Literal["whatsapp", "instagram", "telegram", "email", "web"]


class InboundMessageKind(str, enum.Enum):
    """Normalised inbound shape. Phase 1 covers text + interactive replies.

    Media (image/audio/video/document) is captured as ``UNSUPPORTED`` for now
    — the adapter still parses ``from``/``to`` so the webhook can ack and the
    pipeline can answer "puedo manejar texto pero no medios todavía". Phase 2
    promotes media to first-class kinds when the use case shows up.
    """

    TEXT = "text"
    INTERACTIVE = "interactive"
    UNSUPPORTED = "unsupported"


class InteractiveReply(BaseModel):
    """User's reply to a button or list interactive message."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["button", "list"]
    payload_id: str
    title: str | None = None
    description: str | None = None


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
        max_length=40,
        description=(
            "Stable identifier of the *receiver* (the business). For WhatsApp "
            "this is the business phone number in E.164 format. The webhook "
            "uses this to resolve (provider, identifier) -> tenant_id."
        ),
    )
    sender_identifier: str = Field(min_length=1, max_length=40)
    sender_name: str | None = None
    text: str | None = None
    interactive: InteractiveReply | None = None
    raw_event_type: str | None = None
    received_at: datetime


class SendStatus(str, enum.Enum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
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

    Phase 1: ``whatsapp_ycloud``. The Protocol is async because every real
    transport involves I/O (HTTP, websocket, etc.).
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
