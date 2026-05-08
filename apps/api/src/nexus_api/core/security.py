"""HMAC verification for inbound webhooks + bearer auth for admin endpoints."""

from __future__ import annotations

import hashlib
import hmac

from fastapi import Header, HTTPException, status

from nexus_api.config import get_settings
from nexus_api.core.errors import HMACVerificationFailed


def compute_hmac_sha256(secret: str, body: bytes) -> str:
    """Hex-encoded HMAC-SHA256 of `body` with `secret`."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_hmac(secret: str, body: bytes, signature: str) -> None:
    """Constant-time HMAC verify. Raises `HMACVerificationFailed` on mismatch.

    `signature` may be hex-encoded with or without a leading prefix like
    `sha256=`. We normalise both sides before comparison.
    """
    if signature is None:
        raise HMACVerificationFailed("Missing signature header")
    sig = signature.split("=", 1)[1] if "=" in signature else signature
    expected = compute_hmac_sha256(secret, body)
    if not hmac.compare_digest(expected, sig):
        raise HMACVerificationFailed("HMAC mismatch")


def require_admin_token(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> str:
    """FastAPI dependency. Validates `Authorization: Bearer <NEXUS_ADMIN_TOKEN>`.

    Returns the token (so handlers can reuse it as the actor in audit logs);
    Better Auth replaces this in block G with a real session.
    """
    settings = get_settings()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token, settings.admin_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token",
        )
    return token
