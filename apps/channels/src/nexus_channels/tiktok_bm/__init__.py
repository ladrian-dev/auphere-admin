"""TikTok Business Messaging channel — direct integration as a TikTok developer app.

Single Auphere developer app on ``business-api.tiktok.com``; every tenant
authorises *that* app over their own Business Account, the same
Tech-Provider shape the Meta channel uses. ``channels.provider`` is
``"tiktok"`` for every TikTok channel.

Public surface:

- :class:`TikTokChannelAdapter` — implements
  :class:`nexus_channels.base.ChannelAdapter`.
- :class:`TikTokClient` — raw API wrapper with envelope-aware error handling
  and retries. Reused by the adapter, the authorisation orchestrator and the
  token-refresh cron.
- ``parse_inbound`` / ``extract_business_id`` / ``extract_conversation_id`` —
  webhook payload parsers.
- ``verify_tiktok_signature`` — ``TikTok-Signature`` HMAC verifier.

Two constraints from the provider shape everything downstream, and are
repeated here because they are easy to forget at a call site:

1. **Access tokens live ~24 hours.** Without the refresh cron every TikTok
   channel goes silent within a day.
2. **The business can never speak first.** Outbound sends require a
   ``conversation_id`` the user opened, inside a 48-hour window.

The credentials wrapper (``credentials.TikTokCredentials``) is imported
lazily from its submodule to keep Postgres deps out of the adapter's
outbound path.
"""

from __future__ import annotations

from nexus_channels.tiktok_bm.adapter import TikTokChannelAdapter
from nexus_channels.tiktok_bm.exceptions import (
    TikTokAPIError,
    TikTokAuthorizationError,
    TikTokInvalidSignatureError,
    TikTokMalformedPayloadError,
    TikTokNoBusinessAccountError,
    TikTokRateLimitedError,
    TikTokRegionNotSupportedError,
    TikTokTokenExchangeError,
    TikTokTokenInvalidatedError,
    TikTokTokenRefreshError,
    TikTokTransientError,
    TikTokWebhookSetupError,
)
from nexus_channels.tiktok_bm.signature import (
    DEFAULT_TOLERANCE_SECONDS,
    sign_tiktok_request,
    verify_tiktok_signature,
)
from nexus_channels.tiktok_bm.tiktok_client import (
    TIKTOK_API_BASE_URL,
    TIKTOK_API_VERSION,
    TikTokClient,
)
from nexus_channels.tiktok_bm.webhook_adapter import (
    ConversationEvent,
    extract_business_id,
    extract_conversation_id,
    is_known_event,
    is_message_event,
    iter_inbound_messages,
    parse_conversation_event,
    parse_inbound,
)

# TikTok's service window: 48 hours from the customer's last interaction,
# twice WhatsApp's 24. Lives here rather than in the adapter because the
# guardrail that enforces it runs in the API layer, well away from any
# send call.
TIKTOK_SERVICE_WINDOW_HOURS = 48

__all__ = [
    "DEFAULT_TOLERANCE_SECONDS",
    "TIKTOK_API_BASE_URL",
    "TIKTOK_API_VERSION",
    "TIKTOK_SERVICE_WINDOW_HOURS",
    "ConversationEvent",
    "TikTokAPIError",
    "TikTokAuthorizationError",
    "TikTokChannelAdapter",
    "TikTokClient",
    "TikTokInvalidSignatureError",
    "TikTokMalformedPayloadError",
    "TikTokNoBusinessAccountError",
    "TikTokRateLimitedError",
    "TikTokRegionNotSupportedError",
    "TikTokTokenExchangeError",
    "TikTokTokenInvalidatedError",
    "TikTokTokenRefreshError",
    "TikTokTransientError",
    "TikTokWebhookSetupError",
    "extract_business_id",
    "extract_conversation_id",
    "is_known_event",
    "is_message_event",
    "iter_inbound_messages",
    "parse_conversation_event",
    "parse_inbound",
    "sign_tiktok_request",
    "verify_tiktok_signature",
]
