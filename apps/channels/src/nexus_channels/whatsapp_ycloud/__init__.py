"""WhatsApp via YCloud BSP — Phase 1 channel adapter.

Architecture:

- :mod:`signature`: HMAC verifier matching YCloud's `t={ts},s={sig}` scheme
  over `{ts}.{raw_body}`. Different from generic HMAC; lives here so
  :mod:`nexus_api.core.security` stays provider-agnostic.
- :mod:`webhook_adapter`: parses YCloud's `whatsapp.inbound_message.received`
  envelope into :class:`nexus_channels.base.InboundMessage`.
- :mod:`ycloud_client`: thin async httpx client wrapping
  ``POST /v2/whatsapp/messages/sendDirectly`` and the embedded-signup support
  endpoints (``bindWaba``, ``registerPhoneNumber``).
- :mod:`adapter`: the :class:`ChannelAdapter` implementation.
- :mod:`templates`: YAML-on-disk catalog of approved Meta templates per
  tenant. The adapter renders params at send time.
"""

from nexus_channels.whatsapp_ycloud.adapter import WhatsAppYCloudAdapter
from nexus_channels.whatsapp_ycloud.signature import (
    YCloudSignatureError,
    sign_ycloud_request,
    verify_ycloud_signature,
)
from nexus_channels.whatsapp_ycloud.ycloud_client import (
    YCloudAPIError,
    YCloudClient,
)

__all__ = [
    "WhatsAppYCloudAdapter",
    "YCloudAPIError",
    "YCloudClient",
    "YCloudSignatureError",
    "sign_ycloud_request",
    "verify_ycloud_signature",
]
