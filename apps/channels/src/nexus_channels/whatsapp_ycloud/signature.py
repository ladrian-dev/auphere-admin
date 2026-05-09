"""YCloud webhook signature verification.

YCloud signs each webhook with a header of the form::

    YCloud-Signature: t=<unix_ts>,s=<hex_hmac_sha256>

The signed payload is ``{t}.{raw_body}`` (Stripe-style). The HMAC uses the
account's webhook signing secret (``whsec_...``).

This is **different** from the generic ``verify_hmac`` in
:mod:`nexus_api.core.security` — keep both. The generic one stays for any
future webhook with a simpler scheme; YCloud-specific logic lives here so
the provider quirks don't leak into the security module.
"""

from __future__ import annotations

import hashlib
import hmac
import time


class YCloudSignatureError(Exception):
    """Raised when a YCloud webhook signature fails verification."""


def _parse_signature_header(header: str) -> tuple[str, str]:
    """Parse ``t=...,s=...`` into ``(timestamp, signature)``.

    Tolerates extra whitespace and unexpected ordering.
    """
    parts: dict[str, str] = {}
    for chunk in header.split(","):
        chunk = chunk.strip()
        if "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        parts[key.strip()] = value.strip()
    if "t" not in parts or "s" not in parts:
        raise YCloudSignatureError("malformed YCloud-Signature header (missing t/s components)")
    return parts["t"], parts["s"]


def sign_ycloud_request(
    secret: str,
    body: bytes,
    *,
    timestamp: int | None = None,
) -> str:
    """Produce a header value YCloud would send for ``body``. Used by tests
    and by the local smoke fixture; the real signing happens at YCloud."""
    ts = str(timestamp if timestamp is not None else int(time.time()))
    payload = f"{ts}.".encode() + body
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"t={ts},s={sig}"


def verify_ycloud_signature(
    secret: str,
    body: bytes,
    header_value: str,
    *,
    tolerance_seconds: int = 300,
    now: int | None = None,
) -> None:
    """Constant-time verify. Raises :class:`YCloudSignatureError` on mismatch.

    ``tolerance_seconds`` rejects signatures whose timestamp is too far from
    "now" (replay protection). Default 5 min — generous enough for clock
    skew, tight enough that captured webhook calls expire fast.
    """
    if not header_value:
        raise YCloudSignatureError("missing signature header")
    timestamp, received = _parse_signature_header(header_value)
    try:
        ts_int = int(timestamp)
    except ValueError as exc:
        raise YCloudSignatureError(f"non-numeric timestamp: {timestamp!r}") from exc
    current = now if now is not None else int(time.time())
    if abs(current - ts_int) > tolerance_seconds:
        raise YCloudSignatureError(
            f"timestamp drift exceeds tolerance: |{current - ts_int}| > {tolerance_seconds}"
        )
    payload = f"{timestamp}.".encode() + body
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise YCloudSignatureError("signature mismatch")
