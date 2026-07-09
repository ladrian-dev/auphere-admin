"""Web chat widget session JWT mint + verification.

Sister of ``core/embed_jwt.py`` for the PUBLIC web chat widget. The token
is the association mechanism between an anonymous browser session and a
tenant: it is minted ONLY by ``POST /v1/widget/session`` (after the
``public_key`` → tenant lookup + origin allow-list check) and verified by
every ``POST/GET /v1/widget/messages`` request. Handlers read ``tenant_id``
exclusively from these signed claims — never from browser input — which
plugs straight into ``SET LOCAL app.tenant_id`` + RLS.

HS256 with the SAME secret as the embed surface (``embed_jwt_secret``):
this API is the only minter and verifier, so a symmetric key is correct
and a second secret would add rotation surface for zero benefit. The
audience is a DISTINCT constant from the embed app origin so an embed
token can't be replayed on the widget surface (and vice-versa).

The ``session_id`` claim is the anonymous customer identity (a uuid the
loader stores in ``localStorage``); it becomes ``Customer.identifier`` in
the pipeline, giving the visitor cart/history continuity across page
loads. The ``origin`` claim binds the token to the site it was minted for.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from nexus_api.config import get_settings

# Distinct audience from ``embed_app_origin`` — a leaked embed/broadcast
# token must not authenticate against the chat widget surface.
_WIDGET_AUDIENCE = "auphere:web-widget"
_WIDGET_SCOPE = "widget:chat"


class WidgetSessionTokenError(Exception):
    """Verification failed — expired, bad signature, wrong audience,
    malformed claims. Always maps to 401; safe to log but never echoed to
    the browser verbatim."""


@dataclass(frozen=True)
class WidgetSessionClaims:
    tenant_id: uuid.UUID
    session_id: str
    origin: str
    scope: str
    jti: str


def mint_widget_session_token(
    *,
    tenant_id: uuid.UUID,
    session_id: str,
    origin: str,
) -> tuple[str, str, int]:
    """Returns ``(token, jti, expires_in_seconds)``."""
    settings = get_settings()
    now = datetime.now(UTC)
    jti = uuid.uuid4().hex
    token = jwt.encode(
        {
            "tenant_id": str(tenant_id),
            "session_id": session_id,
            # Binds the token to the site it was minted for; re-checked
            # against the request ``Origin`` header on every call.
            "origin": origin,
            "scope": _WIDGET_SCOPE,
            "aud": _WIDGET_AUDIENCE,
            "iat": now,
            "exp": now + timedelta(seconds=settings.embed_token_ttl_seconds),
            "jti": jti,
        },
        settings.embed_jwt_secret,
        algorithm="HS256",
    )
    return token, jti, settings.embed_token_ttl_seconds


def verify_widget_session_token(token: str) -> WidgetSessionClaims:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.embed_jwt_secret,
            algorithms=["HS256"],  # explicit allow-list — never trust the header
            audience=_WIDGET_AUDIENCE,
            options={"require": ["exp", "iat", "aud", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise WidgetSessionTokenError(str(exc)) from exc
    try:
        return WidgetSessionClaims(
            tenant_id=uuid.UUID(payload["tenant_id"]),
            session_id=str(payload["session_id"]),
            origin=str(payload["origin"]),
            scope=str(payload.get("scope", "")),
            jti=payload["jti"],
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise WidgetSessionTokenError(f"malformed claims: {exc}") from exc
