"""Nexus channel adapters.

Each channel implements the :class:`ChannelAdapter` protocol from
:mod:`nexus_channels.base`. Providers: ``whatsapp_meta`` (Cloud API direct)
and ``tiktok_bm`` (TikTok Business Messaging API); future channels
(Instagram DM, Telegram, email, web chat) plug in without touching the
worker runtime.

The adapter pattern keeps the runtime agnostic to the medium — it sees only
``InboundMessage`` and ``SendResult`` shapes.
"""

from nexus_channels.base import (
    ChannelAdapter,
    ChannelCapabilityError,
    InboundMessage,
    InboundMessageKind,
    InteractiveReply,
    LocationPayload,
    MediaReference,
    ReactionPayload,
    SendResult,
    SendStatus,
)

__all__ = [
    "ChannelAdapter",
    "ChannelCapabilityError",
    "InboundMessage",
    "InboundMessageKind",
    "InteractiveReply",
    "LocationPayload",
    "MediaReference",
    "ReactionPayload",
    "SendResult",
    "SendStatus",
]
