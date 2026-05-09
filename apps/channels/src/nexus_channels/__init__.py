"""Nexus channel adapters.

Each channel implements the :class:`ChannelAdapter` protocol from
:mod:`nexus_channels.base`. Phase 1 ships only ``whatsapp_ycloud``; future
channels (Instagram DM, Telegram, email, web chat) plug in without touching
the worker runtime.

The adapter pattern keeps the runtime agnostic to the medium — it sees only
``InboundMessage`` and ``SendResult`` shapes.
"""

from nexus_channels.base import (
    ChannelAdapter,
    InboundMessage,
    InboundMessageKind,
    InteractiveReply,
    SendResult,
    SendStatus,
)

__all__ = [
    "ChannelAdapter",
    "InboundMessage",
    "InboundMessageKind",
    "InteractiveReply",
    "SendResult",
    "SendStatus",
]
