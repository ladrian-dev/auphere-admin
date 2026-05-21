"""Exceptions raised by the Meta WhatsApp adapter.

Hierarchy designed so callers can match coarsely (``MetaAPIError``) or finely
(``TokenInvalidatedError`` triggers tenant re-onboarding,
``MetaRateLimitedError`` triggers backoff in the outbound dispatcher).

Codes that map to specific subclasses, per Graph API docs:

- ``OAuthException`` code 190 (or 102, 463) → :class:`TokenInvalidatedError`.
- ``code = 4`` (Application request limit reached), ``code = 80004``
  (Throttled — too many calls), HTTP 429 → :class:`MetaRateLimitedError`.
- HTTP 5xx and timeouts → :class:`MetaTransientError`.
- Everything else 4xx → :class:`MetaAPIError`.
"""

from __future__ import annotations


class MetaError(Exception):
    """Base for every exception raised by this module."""


# ── HTTP / API ──────────────────────────────────────────────────────────────


class MetaAPIError(MetaError):
    """Non-2xx response from the Graph API.

    ``code`` and ``subcode`` follow Meta's conventions; see
    https://developers.facebook.com/docs/graph-api/guides/error-handling/.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: int | None = None,
        subcode: int | None = None,
        fbtrace_id: str | None = None,
        body: str | None = None,
    ) -> None:
        super().__init__(f"Meta API error {status_code}: {message}")
        self.message = message
        self.status_code = status_code
        self.code = code
        self.subcode = subcode
        self.fbtrace_id = fbtrace_id
        self.body = body


class MetaRateLimitedError(MetaAPIError):
    """HTTP 429 or Graph API code 4/80004. The dispatcher should backoff."""


class MetaTransientError(MetaAPIError):
    """HTTP 5xx, timeouts, gateway errors. Safe to retry."""


# ── Tokens ──────────────────────────────────────────────────────────────────


class TokenInvalidatedError(MetaAPIError):
    """OAuthException 190 (or 102, 463) — the BISUAT is no longer usable.

    Inherits from :class:`MetaAPIError` so the same ``status_code`` / ``code``
    / ``subcode`` / ``fbtrace_id`` / ``body`` payload the API layer captures
    on every Meta error is also available here without a special case.

    The adapter raises this so the API layer can flip
    ``tenant_credentials.needs_reauth = true`` and dispatch the
    ``alert_needs_reauth_v1`` template to the tenant owner. The next
    inbound from that WABA stays at 200 OK; outbound returns
    ``SendStatus.FAILED`` until re-onboarding completes.
    """


class TokenExchangeError(MetaError):
    """OAuth ``code`` could not be exchanged for a BISUAT.

    Distinct hierarchy from :class:`TokenInvalidatedError` — exchange
    failures happen during onboarding (no BISUAT yet), so they should not
    trigger ``needs_reauth`` on an existing tenant.
    """


# ── Webhooks ────────────────────────────────────────────────────────────────


class WebhookError(MetaError):
    """Base for webhook processing issues. The route translates these to
    HTTP responses; never let them bubble unhandled."""


class InvalidSignatureError(WebhookError):
    """``X-Hub-Signature-256`` did not verify.

    Almost always means: (a) wrong App Secret, (b) framework re-serialised
    the body, (c) spoofing attempt. The route returns 401 *without* echoing
    the body to logs.
    """


class MalformedPayloadError(WebhookError):
    """Payload did not match the documented Cloud API schema. We log,
    return 200 (so Meta doesn't redrive) and discard."""


# ── Signup ──────────────────────────────────────────────────────────────────


class SignupError(MetaError):
    """Base for Embedded Signup orchestration failures."""


class RegisterPhoneError(SignupError):
    """``POST /{phone_number_id}/register`` failed.

    Common cause: PIN already set from a prior registration. The signup
    flow retries with a stored PIN before surfacing.
    """


class SubscribeWebhookError(SignupError):
    """``POST /{waba_id}/subscribed_apps`` failed.

    Until this succeeds the WABA does not emit webhooks to our endpoint —
    the tenant is technically "onboarded" but silent. The signup orchestrator
    must roll back tenant_credentials when this happens.
    """
