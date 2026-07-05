"""Widget session JWT mint + verification (ADR-028).

The token is the association mechanism between a partner's client and
our tenant: it is minted ONLY by ``POST /v1/widget-sessions`` (secret
API key auth, tenant resolved through the ``partner_tenants`` mapping)
and verified by every ``/v1/embed/*`` request. The resource side reads
``tenant_id`` exclusively from these signed claims — never from browser
input — which plugs straight into ``SET LOCAL app.tenant_id`` + RLS.

HS256 with a dedicated secret: this API is both the only minter and the
only verifier, so asymmetric keys would add rotation surface for zero
benefit. ``aud`` is pinned to the embed app origin so an accidentally
leaked token can't be replayed against a future JWT surface with a
different audience.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from nexus_api.config import get_settings


class WidgetTokenError(Exception):
    """Verification failed — expired, bad signature, wrong audience,
    malformed claims. Always maps to 401; the message is safe to log
    but must not be echoed to the browser verbatim."""


@dataclass(frozen=True)
class WidgetClaims:
    tenant_id: uuid.UUID
    partner_id: uuid.UUID
    key_id: uuid.UUID
    scope: tuple[str, ...]
    allowed_origins: tuple[str, ...]
    jti: str


def mint_widget_token(
    *,
    tenant_id: uuid.UUID,
    partner_id: uuid.UUID,
    key_id: uuid.UUID,
    scope: list[str],
    allowed_origins: list[str],
) -> tuple[str, str, int]:
    """Returns ``(token, jti, expires_in_seconds)``."""
    settings = get_settings()
    now = datetime.now(UTC)
    jti = uuid.uuid4().hex
    token = jwt.encode(
        {
            "tenant_id": str(tenant_id),
            "partner_id": str(partner_id),
            "key_id": str(key_id),
            "scope": scope,
            # Shipped in the claims so the iframe can enforce the
            # postMessage origin allow-list without an extra roundtrip.
            # The authoritative checks stay server-side.
            "allowed_origins": allowed_origins,
            "aud": settings.embed_app_origin,
            "iat": now,
            "exp": now + timedelta(seconds=settings.embed_token_ttl_seconds),
            "jti": jti,
        },
        settings.embed_jwt_secret,
        algorithm="HS256",
    )
    return token, jti, settings.embed_token_ttl_seconds


def verify_widget_token(token: str) -> WidgetClaims:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.embed_jwt_secret,
            algorithms=["HS256"],  # explicit allow-list — never trust the header
            audience=settings.embed_app_origin,
            options={"require": ["exp", "iat", "aud", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise WidgetTokenError(str(exc)) from exc
    try:
        return WidgetClaims(
            tenant_id=uuid.UUID(payload["tenant_id"]),
            partner_id=uuid.UUID(payload["partner_id"]),
            key_id=uuid.UUID(payload["key_id"]),
            scope=tuple(payload.get("scope", ())),
            allowed_origins=tuple(payload.get("allowed_origins", ())),
            jti=payload["jti"],
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise WidgetTokenError(f"malformed claims: {exc}") from exc
