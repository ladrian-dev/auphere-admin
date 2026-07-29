"""Exceptions raised by the TikTok Business Messaging adapter.

Mirrors the shape of :mod:`nexus_channels.whatsapp_meta.exceptions` so the
outbound dispatcher can classify failures the same way for both channels
(coarse match on ``TikTokAPIError``, fine match on
:class:`TikTokTokenInvalidatedError` to trigger re-authorisation).

One TikTok-specific wrinkle drives the whole design here: **the API answers
HTTP 200 even when the call failed.** Success is ``code == 0`` in the JSON
envelope; anything else is an error carrying ``code``, ``message`` and
``request_id``. So ``status_code`` on these exceptions is frequently 200 and
must never be used alone to decide success — that's why ``code`` is a
first-class field and the classification in ``tiktok_client`` keys off it.
"""

from __future__ import annotations


class TikTokError(Exception):
    """Base for every exception raised by this module."""


# ── HTTP / API ──────────────────────────────────────────────────────────────


class TikTokAPIError(TikTokError):
    """The API rejected the call.

    ``status_code`` is the HTTP status (often 200 — see module docstring) and
    ``code`` is TikTok's own error code from the response envelope, which is
    the field that actually carries the semantics.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: int | None = None,
        request_id: str | None = None,
        body: str | None = None,
    ) -> None:
        super().__init__(f"TikTok API error {status_code}/{code}: {message}")
        self.message = message
        self.status_code = status_code
        self.code = code
        self.request_id = request_id
        self.body = body


class TikTokRateLimitedError(TikTokAPIError):
    """HTTP 429 or a throttling code. Business Messaging is capped around
    10 QPS, which a reminder fan-out can brush against."""


class TikTokTransientError(TikTokAPIError):
    """HTTP 5xx, timeouts, gateway errors. Safe to retry."""


# ── Tokens ──────────────────────────────────────────────────────────────────


class TikTokTokenInvalidatedError(TikTokAPIError):
    """The access token is no longer usable and refreshing won't help.

    TikTok access tokens live ~24h and are rotated by the refresh cron. This
    is the *other* failure: the business revoked the authorisation, or the
    one-year refresh token finally expired. The dispatcher flips
    ``tenant_credentials.needs_reauth`` so the panel can prompt the owner to
    re-authorise, exactly like the Meta path does on OAuthException 190.
    """


class TikTokTokenExchangeError(TikTokError):
    """``auth_code`` could not be exchanged for an access token.

    Separate hierarchy from :class:`TikTokTokenInvalidatedError` — exchange
    failures happen during onboarding, when there is no credential row yet,
    so they must not flag an existing tenant as needing re-auth.
    """


class TikTokTokenRefreshError(TikTokError):
    """The refresh token could not be redeemed for a new access token.

    Raised by the refresh cron. Unlike the exchange error this DOES imply
    an existing credential row, and the caller is expected to flag
    ``needs_reauth`` — a channel with a dead token goes silent within a day.
    """


# ── Webhooks ────────────────────────────────────────────────────────────────


class TikTokWebhookError(TikTokError):
    """Base for webhook processing issues. The route translates these to
    HTTP responses; never let them bubble unhandled."""


class TikTokInvalidSignatureError(TikTokWebhookError):
    """``TikTok-Signature`` did not verify, or its timestamp was outside the
    accepted tolerance.

    Almost always means: (a) wrong App Secret, (b) the framework re-serialised
    the body before we hashed it, (c) a replay or spoofing attempt. The route
    returns 401 *without* echoing the body to logs.
    """


class TikTokMalformedPayloadError(TikTokWebhookError):
    """Payload did not match the documented schema. We log, return 200 (so
    TikTok doesn't redrive) and discard."""


# ── Authorisation ───────────────────────────────────────────────────────────


class TikTokAuthorizationError(TikTokError):
    """Base for authorisation-flow orchestration failures."""


class TikTokNoBusinessAccountError(TikTokAuthorizationError):
    """The authorisation succeeded but exposed no usable Business Account.

    Usual cause: the owner authorised with a personal TikTok account.
    Business Messaging is Business-Account-only, so there is nothing to
    connect and the flow must stop with a message the owner can act on.
    """


class TikTokRegionNotSupportedError(TikTokAuthorizationError):
    """The Business Account is registered in a region where TikTok does not
    offer Business Messaging (EEA, Switzerland, UK).

    Detected during authorisation so the owner gets a clear explanation
    instead of a channel that connects and then silently never receives a
    single webhook.
    """


class TikTokWebhookSetupError(TikTokAuthorizationError):
    """Creating the Business Messaging webhook configuration failed.

    Until this succeeds the Business Account does not emit events to our
    endpoint — the tenant looks "connected" but is deaf.
    """
