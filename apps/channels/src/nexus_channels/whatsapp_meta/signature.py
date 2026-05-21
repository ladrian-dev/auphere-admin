"""HMAC SHA-256 verification of Meta webhooks + ``appsecret_proof`` helper.

Meta signs every webhook delivery with::

    X-Hub-Signature-256: sha256=<hex_hmac>

where the HMAC key is the Meta App Secret (global to the app, NOT per
tenant) and the message is the **raw request body** — bytes exactly as
they arrived. Any re-serialisation (``json.loads`` → ``json.dumps``) breaks
the comparison even if the JSON is semantically equal.

This module is the security-critical surface. The route layer in
``apps/api`` must:

1. Read ``request.body()`` BEFORE accessing ``request.json()`` so
   Starlette does not consume the stream.
2. Pass the bytes verbatim to :func:`verify_meta_signature`.
3. Translate :class:`MetaSignatureError` to ``401 Unauthorized``.

``appsecret_proof`` is the companion mechanism for the *outbound* side:
when ``Require App Secret Proof`` is enabled on the Meta App (Auphere has
it ON since 2026-05-21), every authenticated Graph API call must carry
``appsecret_proof = HMAC_SHA256(bisuat, app_secret)`` as a query param or
body field. :class:`MetaClient` injects it automatically.
"""

from __future__ import annotations

import hashlib
import hmac
import time

_PREFIX = "sha256="


class MetaSignatureError(Exception):
    """Raised when a Meta webhook signature does not verify."""


def verify_meta_signature(
    secret: str,
    body: bytes,
    header_value: str | None,
) -> None:
    """Constant-time verify of an ``X-Hub-Signature-256`` header.

    Raises :class:`MetaSignatureError` on every failure mode (missing
    header, wrong prefix, length mismatch, digest mismatch) so the caller
    only has to ``try / except``.

    Args:
        secret: The Meta App Secret (string from
            :attr:`nexus_api.config.Settings.meta_app_secret`).
        body: Raw bytes of the request body. Do NOT pass
            ``json.dumps(json.loads(body))`` — the bytes must be the exact
            payload Meta signed.
        header_value: Contents of the ``X-Hub-Signature-256`` header. ``None``
            is accepted and rejected uniformly so the caller doesn't have to
            null-check upstream.
    """
    if not header_value:
        raise MetaSignatureError("missing X-Hub-Signature-256 header")
    if not header_value.startswith(_PREFIX):
        raise MetaSignatureError(
            f"unexpected signature prefix: {header_value[: len(_PREFIX)]!r}"
        )
    received = header_value[len(_PREFIX) :]
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise MetaSignatureError("signature mismatch")


def sign_meta_request(secret: str, body: bytes) -> str:
    """Produce the header value Meta would send for ``body``.

    Used by tests (fixture webhooks) and by the local smoke harness. Real
    signing happens at Meta — Nexus only ever verifies.
    """
    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"{_PREFIX}{sig}"


def appsecret_proof(access_token: str, app_secret: str) -> str:
    """Compute ``appsecret_proof`` for a BISUAT (or any user token).

    Meta requires this on every authenticated Graph API call when the app
    has *Require App Secret Proof* enabled. The value is an HMAC-SHA256 of
    the access token using the App Secret as the key, hex-digested.

    The proof is rotation-stable: it changes only when the app secret
    rotates or the token rotates. Computing it on every request is cheap
    (~1µs); callers may cache per token if they ever measure this in the
    hot path.
    """
    return hmac.new(
        app_secret.encode("utf-8"),
        access_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def is_replay_acceptable(meta_timestamp: int | None, *, tolerance_seconds: int = 300) -> bool:
    """Bonus replay-window check for payloads that carry a timestamp.

    Meta's ``X-Hub-Signature-256`` itself does not include a timestamp
    (unlike YCloud's ``t=...,s=...``), so replay protection is *best-effort*
    using the timestamp Meta embeds inside the payload (``entry[].time``
    or per-message ``timestamp``). The webhook route may use this when the
    payload contains one; if not, ``meta_timestamp=None`` short-circuits to
    ``True`` (no extra protection beyond the signature).
    """
    if meta_timestamp is None:
        return True
    return abs(int(time.time()) - meta_timestamp) <= tolerance_seconds
