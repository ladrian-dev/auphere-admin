"""WhatsApp Cloud API channel — direct integration with Meta as Tech Provider.

Replaces ``whatsapp_ycloud`` for tenants migrated to the Auphere-owned Meta
App (BM Facelad SpA, App ID 957213733862330). The two packages coexist
during the migration: ``channels.provider`` discriminates ``"ycloud"`` from
``"meta"`` at the webhook layer, so a single tenant can sit on one provider
at a time and switch on Embedded Signup completion.

Public surface:

- :class:`MetaChannelAdapter` — implements
  :class:`nexus_channels.base.ChannelAdapter`.
- :class:`MetaClient` — raw Graph API wrapper with ``appsecret_proof`` and
  retries. Reused by the adapter, the signup orchestrator, and any future
  background job that needs to talk to Meta on a tenant's behalf.
- ``parse_inbound`` / ``extract_business_phone`` — webhook payload parsers.
- ``verify_meta_signature`` — ``X-Hub-Signature-256`` HMAC verifier.

The signup helpers (``embedded_signup``, ``post_signup``) and the
credentials wrapper (``credentials.MetaCredentials``) are imported lazily
from their submodules to avoid pulling Postgres deps into the channel
adapter's outbound path.
"""

from __future__ import annotations

from nexus_channels.whatsapp_meta.adapter import MetaChannelAdapter
from nexus_channels.whatsapp_meta.exceptions import (
    MetaAPIError,
    MetaRateLimitedError,
    MetaTransientError,
    TokenInvalidatedError,
)
from nexus_channels.whatsapp_meta.meta_client import (
    META_GRAPH_BASE_URL,
    META_GRAPH_VERSION,
    MetaClient,
)
from nexus_channels.whatsapp_meta.signature import (
    MetaSignatureError,
    appsecret_proof,
    sign_meta_request,
    verify_meta_signature,
)
from nexus_channels.whatsapp_meta.signup import (
    EmbeddedSignupOrchestrator,
    SignupIngressPayload,
    SignupResult,
)
from nexus_channels.whatsapp_meta.webhook_adapter import (
    INBOUND_OBJECT,
    AppStateSync,
    HistorySync,
    MessageEcho,
    StatusUpdate,
    TemplateStatusUpdate,
    extract_business_phone,
    extract_phone_number_id,
    extract_waba_id,
    iter_inbound_messages,
    parse_app_state_sync,
    parse_history_sync,
    parse_inbound,
    parse_message_echo,
    parse_status_callback,
    parse_template_status,
)

__all__ = [
    "INBOUND_OBJECT",
    "META_GRAPH_BASE_URL",
    "META_GRAPH_VERSION",
    "AppStateSync",
    "EmbeddedSignupOrchestrator",
    "HistorySync",
    "MessageEcho",
    "MetaAPIError",
    "MetaChannelAdapter",
    "MetaClient",
    "MetaRateLimitedError",
    "MetaSignatureError",
    "MetaTransientError",
    "SignupIngressPayload",
    "SignupResult",
    "StatusUpdate",
    "TemplateStatusUpdate",
    "TokenInvalidatedError",
    "appsecret_proof",
    "extract_business_phone",
    "extract_phone_number_id",
    "extract_waba_id",
    "iter_inbound_messages",
    "parse_app_state_sync",
    "parse_history_sync",
    "parse_inbound",
    "parse_message_echo",
    "parse_status_callback",
    "parse_template_status",
    "sign_meta_request",
    "verify_meta_signature",
]
