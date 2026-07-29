"""HMAC-signed ``state`` for the TikTok authorisation redirect.

TikTok's authorisation flow is a plain browser redirect: we send the business
owner to TikTok with a ``state`` parameter, and TikTok hands that value back
to our callback alongside the ``auth_code``. The callback has no session and
no other way to know *which tenant* is connecting, so ``state`` has to carry
that itself — and therefore has to be unforgeable.

Without a signed state, anyone who can reach the callback URL could post an
``auth_code`` of their own with ``state=<victim tenant id>`` and graft their
TikTok account onto someone else's tenant. That is a cross-tenant write, so
this module is on the isolation boundary, not merely a convenience.

Properties:

- **Tenant-bound** — the payload contains ``tenant_id``; a state signed for
  tenant A cannot authorise tenant B.
- **Short-lived** — 30 minutes by default. An OAuth round-trip takes
  seconds; anything longer is a stale tab or a replay.
- **Tamper-evident** — HMAC-SHA256 over canonical JSON, verified with
  ``hmac.compare_digest``.
- **Nonced** — two authorisations of the same tenant produce different
  states, so one cannot be mistaken for the other in logs.

Format is ``base64url(payload).base64url(signature)``, matching the
convention already used by
:mod:`nexus_api.services.connectors.consent_token`.
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

DEFAULT_TTL = timedelta(minutes=30)


class OAuthStateInvalid(ValueError):
    """The state is malformed, tampered with, or signed with another secret."""


class OAuthStateExpired(ValueError):
    """The state's expiration has passed."""


@dataclass(frozen=True)
class OAuthStatePayload:
    tenant_id: uuid.UUID
    nonce: str
    expires_at: datetime


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def sign_oauth_state(
    *,
    tenant_id: uuid.UUID,
    secret: str,
    ttl: timedelta = DEFAULT_TTL,
    now: datetime | None = None,
) -> tuple[str, OAuthStatePayload]:
    """Mint a signed state. Returns ``(state_string, payload)``."""
    if not secret:
        raise ValueError("oauth state secret must be non-empty")
    issued = now if now is not None else datetime.now(UTC)
    payload = OAuthStatePayload(
        tenant_id=tenant_id,
        nonce=secrets.token_urlsafe(16),
        expires_at=issued + ttl,
    )
    raw = json.dumps(
        {
            "t": str(payload.tenant_id),
            "n": payload.nonce,
            "e": int(payload.expires_at.timestamp()),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    return f"{_b64url_encode(raw)}.{_b64url_encode(signature)}", payload


def verify_oauth_state(
    *,
    state: str,
    secret: str,
    now: datetime | None = None,
) -> OAuthStatePayload:
    """Verify a state and return its payload. Raises on any failure mode."""
    if not secret:
        raise ValueError("oauth state secret must be non-empty")
    if not state or "." not in state:
        raise OAuthStateInvalid("malformed state (missing separator)")
    raw_b64, sig_b64 = state.split(".", 1)
    try:
        raw = _b64url_decode(raw_b64)
        signature = _b64url_decode(sig_b64)
    except (ValueError, binascii.Error) as exc:
        raise OAuthStateInvalid("base64 decode failed") from exc

    expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    # Compared before parsing: an attacker must not be able to probe payload
    # handling with unsigned input.
    if not hmac.compare_digest(expected, signature):
        raise OAuthStateInvalid("HMAC mismatch")

    try:
        parsed = json.loads(raw.decode("utf-8"))
        tenant_id = uuid.UUID(parsed["t"])
        nonce = str(parsed["n"])
        expires_at = datetime.fromtimestamp(int(parsed["e"]), tz=UTC)
    except (KeyError, ValueError, TypeError) as exc:
        raise OAuthStateInvalid(f"payload parse failed: {exc}") from exc

    current = now if now is not None else datetime.now(UTC)
    if current >= expires_at:
        raise OAuthStateExpired(
            f"state expired at {expires_at.isoformat()}; now is {current.isoformat()}"
        )
    return OAuthStatePayload(tenant_id=tenant_id, nonce=nonce, expires_at=expires_at)


__all__ = [
    "DEFAULT_TTL",
    "OAuthStateExpired",
    "OAuthStateInvalid",
    "OAuthStatePayload",
    "sign_oauth_state",
    "verify_oauth_state",
]
