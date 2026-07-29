"""HMAC SHA-256 verification of TikTok webhook deliveries.

TikTok signs every webhook with a header of the form::

    TikTok-Signature: t=1701234567,s=<hex_hmac>

where ``t`` is a unix timestamp, the HMAC key is the developer app's
**client secret** (global to the app, NOT per tenant), and the signed
message is::

    f"{t}.{raw_body}"

The body must be the bytes **exactly as they arrived**. Any re-serialisation
(``json.loads`` → ``json.dumps``) breaks the comparison even when the JSON is
semantically identical — key order and whitespace are part of what was
signed.

This module is the security-critical surface. The route layer in ``apps/api``
must:

1. Read ``request.body()`` BEFORE touching ``request.json()`` so Starlette
   does not consume the stream.
2. Pass the bytes verbatim to :func:`verify_tiktok_signature`.
3. Translate :class:`TikTokInvalidSignatureError` to ``401 Unauthorized``
   without echoing the body to logs.

Unlike Meta's ``X-Hub-Signature-256``, the timestamp is *inside the signed
material*, so replay protection here is real rather than best-effort: an
attacker cannot change ``t`` without invalidating ``s``.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from nexus_channels.tiktok_bm.exceptions import TikTokInvalidSignatureError

# TikTok's own documentation describes a 5-second freshness expectation, but
# the decision to reject a stale-but-valid payload is explicitly left to the
# receiving application. Five seconds is unusable in practice — ordinary
# queueing or a cold worker would drop legitimate customer messages, and a
# dropped inbound is invisible to the customer, who just sees an agent that
# never answered. 300s is the conventional replay window and still makes
# capture-and-replay useless.
DEFAULT_TOLERANCE_SECONDS = 300


def _parse_header(header_value: str) -> tuple[int, str]:
    """Split ``t=<ts>,s=<sig>`` into its parts.

    Tolerates whitespace and unknown extra fields (TikTok has added fields
    to signature headers before), but requires both ``t`` and ``s``.
    """
    fields: dict[str, str] = {}
    for chunk in header_value.split(","):
        key, sep, value = chunk.partition("=")
        if sep:
            fields[key.strip()] = value.strip()

    raw_ts = fields.get("t")
    signature = fields.get("s")
    if raw_ts is None or signature is None:
        raise TikTokInvalidSignatureError("malformed TikTok-Signature header")
    try:
        timestamp = int(raw_ts)
    except ValueError as exc:
        raise TikTokInvalidSignatureError("TikTok-Signature timestamp is not an integer") from exc
    if not signature:
        raise TikTokInvalidSignatureError("TikTok-Signature carries an empty signature")
    return timestamp, signature


def verify_tiktok_signature(
    client_secret: str,
    body: bytes,
    header_value: str | None,
    *,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: float | None = None,
) -> None:
    """Constant-time verify of a ``TikTok-Signature`` header.

    Raises :class:`TikTokInvalidSignatureError` on every failure mode
    (missing header, malformed header, stale timestamp, digest mismatch) so
    the caller only has to ``try / except``.

    Args:
        client_secret: The developer app's secret, from
            :attr:`nexus_api.config.Settings.tiktok_app_secret`.
        body: Raw bytes of the request body, verbatim.
        header_value: Contents of the ``TikTok-Signature`` header. ``None`` is
            accepted and rejected uniformly so callers needn't null-check.
        tolerance_seconds: Replay window. Set to ``0`` to disable the
            freshness check entirely (tests replaying recorded fixtures).
        now: Injectable clock for deterministic tests.
    """
    if not header_value:
        raise TikTokInvalidSignatureError("missing TikTok-Signature header")

    timestamp, received = _parse_header(header_value)

    # Freshness first: it is the cheap check, and rejecting a replay before
    # the HMAC keeps the constant-time comparison off the hot path for
    # obviously-bad traffic.
    if tolerance_seconds > 0:
        current = time.time() if now is None else now
        if abs(current - timestamp) > tolerance_seconds:
            raise TikTokInvalidSignatureError(
                f"TikTok-Signature timestamp outside {tolerance_seconds}s tolerance"
            )

    expected = _digest(client_secret, timestamp, body)
    if not hmac.compare_digest(expected, received):
        raise TikTokInvalidSignatureError("signature mismatch")


def sign_tiktok_request(client_secret: str, body: bytes, *, timestamp: int | None = None) -> str:
    """Produce the header value TikTok would send for ``body``.

    Used by tests and the local smoke harness. Real signing happens at
    TikTok — Nexus only ever verifies.
    """
    ts = int(time.time()) if timestamp is None else timestamp
    return f"t={ts},s={_digest(client_secret, ts, body)}"


def _digest(client_secret: str, timestamp: int, body: bytes) -> str:
    signed_payload = str(timestamp).encode("utf-8") + b"." + body
    return hmac.new(
        client_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
