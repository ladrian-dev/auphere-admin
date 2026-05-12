"""HMAC-signed consent tokens for the autonomous-consent flow.

Used by:
1. ``initiate_consent`` to embed a server-verifiable token in the magic-link
   URL that the tenant owner clicks (sent via WhatsApp template
   ``connector_consent_request_v1``).
2. ``oauth_callback`` to verify the redirect from the upstream provider was
   triggered by our own initiation, not by a forged URL.

Properties:

- **Tenant-bound** — token payload contains ``tenant_id`` and ``connector_id``.
  A token signed for tenant A cannot authorize tenant B (even if both are
  connecting the same connector simultaneously).
- **Time-bound** — 7-day TTL by default; configurable per call.
- **Single-use** — ``consume_consent_token`` rotates the
  ``tenant_connectors.consent_token`` column atomically; a second call with
  the same token raises ``ConsentTokenAlreadyConsumed``.
- **Tamper-evident** — HMAC-SHA256 over a canonical JSON payload + secret
  from Doppler (``NEXUS_CONNECTOR_CONSENT_SECRET``). Verification uses
  ``hmac.compare_digest``.

The token format is ``base64url(payload).base64url(signature)`` — opaque to
the receiver, no need to share secret with the upstream provider.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

DEFAULT_TTL = timedelta(days=7)


class ConsentTokenInvalid(ValueError):
    """The token is malformed, tampered with, or signed with a different secret."""


class ConsentTokenExpired(ValueError):
    """The token's expiration has passed."""


class ConsentTokenAlreadyConsumed(RuntimeError):
    """The token was already consumed in a previous call."""


@dataclass(frozen=True)
class ConsentTokenPayload:
    tenant_id: uuid.UUID
    connector_id: uuid.UUID
    nonce: str
    expires_at: datetime


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding)


def sign_consent_token(
    *,
    tenant_id: uuid.UUID,
    connector_id: uuid.UUID,
    secret: str,
    ttl: timedelta = DEFAULT_TTL,
    now: datetime | None = None,
) -> tuple[str, ConsentTokenPayload]:
    """Mint a signed consent token. Returns (token_string, payload)."""
    if not secret:
        msg = "consent token secret must be non-empty"
        raise ValueError(msg)
    issued = now if now is not None else datetime.now(UTC)
    expires_at = issued + ttl
    payload = ConsentTokenPayload(
        tenant_id=tenant_id,
        connector_id=connector_id,
        nonce=secrets.token_urlsafe(16),
        expires_at=expires_at,
    )
    raw = json.dumps(
        {
            "t": str(payload.tenant_id),
            "c": str(payload.connector_id),
            "n": payload.nonce,
            "e": int(payload.expires_at.timestamp()),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    token = f"{_b64url_encode(raw)}.{_b64url_encode(signature)}"
    return token, payload


def verify_consent_token(
    *,
    token: str,
    secret: str,
    now: datetime | None = None,
) -> ConsentTokenPayload:
    """Verify a token and return its payload. Raises on any failure mode."""
    if not secret:
        msg = "consent token secret must be non-empty"
        raise ValueError(msg)
    if not token or "." not in token:
        raise ConsentTokenInvalid("malformed token (missing separator)")
    raw_b64, sig_b64 = token.split(".", 1)
    try:
        raw = _b64url_decode(raw_b64)
        signature = _b64url_decode(sig_b64)
    except (ValueError, binascii.Error) as exc:
        raise ConsentTokenInvalid("base64 decode failed") from exc
    expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, signature):
        raise ConsentTokenInvalid("HMAC mismatch")
    try:
        parsed = json.loads(raw.decode("utf-8"))
        tenant_id = uuid.UUID(parsed["t"])
        connector_id = uuid.UUID(parsed["c"])
        nonce = str(parsed["n"])
        expires_at = datetime.fromtimestamp(int(parsed["e"]), tz=UTC)
    except (KeyError, ValueError, TypeError) as exc:
        raise ConsentTokenInvalid(f"payload parse failed: {exc}") from exc
    current = now if now is not None else datetime.now(UTC)
    if current >= expires_at:
        raise ConsentTokenExpired(
            f"token expired at {expires_at.isoformat()}; now is {current.isoformat()}"
        )
    return ConsentTokenPayload(
        tenant_id=tenant_id,
        connector_id=connector_id,
        nonce=nonce,
        expires_at=expires_at,
    )


__all__ = [
    "DEFAULT_TTL",
    "ConsentTokenAlreadyConsumed",
    "ConsentTokenExpired",
    "ConsentTokenInvalid",
    "ConsentTokenPayload",
    "sign_consent_token",
    "verify_consent_token",
]
