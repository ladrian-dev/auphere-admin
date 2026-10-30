"""Instagram (Unified Login) and Messenger channels — spec 049.

Both ride the Messenger Platform on ``graph.facebook.com`` with the business
integration system-user token a Facebook Login for Business configuration
issues, the same mechanism the WhatsApp Embedded Signup uses:

- :class:`MetaSocialChannelAdapter` — outbound for ``meta_instagram`` and
  ``meta_messenger``.
- :mod:`webhook_adapter` — parsers for ``object=instagram`` / ``object=page``.
- :class:`MetaSocialConnector` (``connect`` submodule, imported lazily: it
  pulls the API's models) — connect, check, disconnect.
"""

from __future__ import annotations

from nexus_channels.meta_social.adapter import (
    MetaSocialChannelAdapter,
    SendContext,
    SocialProfile,
)
from nexus_channels.meta_social.exceptions import (
    MetaSocialConnectError,
    MetaSocialWindowClosed,
    is_messages_disabled,
    is_permission_error,
    is_recipient_unavailable,
    is_window_error,
)
from nexus_channels.meta_social.graph import (
    INSTAGRAM_FIELDS,
    MESSENGER_FIELDS,
    META_SOCIAL_GRAPH_VERSION,
    MetaSocialClient,
)
from nexus_channels.meta_social.text import split_message
from nexus_channels.meta_social.webhook_adapter import (
    COMMENT_PREFIX,
    PROVIDER_INSTAGRAM,
    PROVIDER_MESSENGER,
    URL_MEDIA_PREFIX,
    SocialEvent,
    entry_account_ids,
    iter_events,
    provider_for,
)

META_SOCIAL_PROVIDERS = frozenset({PROVIDER_INSTAGRAM, PROVIDER_MESSENGER})

__all__ = [
    "COMMENT_PREFIX",
    "INSTAGRAM_FIELDS",
    "MESSENGER_FIELDS",
    "META_SOCIAL_GRAPH_VERSION",
    "META_SOCIAL_PROVIDERS",
    "PROVIDER_INSTAGRAM",
    "PROVIDER_MESSENGER",
    "URL_MEDIA_PREFIX",
    "MetaSocialChannelAdapter",
    "MetaSocialClient",
    "MetaSocialConnectError",
    "MetaSocialWindowClosed",
    "SendContext",
    "SocialEvent",
    "SocialProfile",
    "entry_account_ids",
    "is_messages_disabled",
    "is_permission_error",
    "is_recipient_unavailable",
    "is_window_error",
    "iter_events",
    "provider_for",
    "split_message",
]
