"""Unit tests for widget session JWT mint/verify (ADR-028)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest

from nexus_api.config import get_settings
from nexus_api.core.embed_jwt import (
    WidgetTokenError,
    mint_widget_token,
    verify_widget_token,
)

TENANT = uuid.uuid4()
PARTNER = uuid.uuid4()
KEY = uuid.uuid4()


def _mint(**overrides):
    kwargs = dict(
        tenant_id=TENANT,
        partner_id=PARTNER,
        key_id=KEY,
        scope=["widget:send"],
        allowed_origins=["https://partner.example"],
    )
    kwargs.update(overrides)
    return mint_widget_token(**kwargs)


def test_mint_and_verify_roundtrip() -> None:
    token, jti, expires_in = _mint()
    claims = verify_widget_token(token)
    assert claims.tenant_id == TENANT
    assert claims.partner_id == PARTNER
    assert claims.key_id == KEY
    assert claims.scope == ("widget:send",)
    assert claims.allowed_origins == ("https://partner.example",)
    assert claims.jti == jti
    assert expires_in == get_settings().embed_token_ttl_seconds


def test_rejects_wrong_signature() -> None:
    token, _, _ = _mint()
    header, payload, _sig = token.split(".")
    forged = f"{header}.{payload}.AAAA"
    with pytest.raises(WidgetTokenError):
        verify_widget_token(forged)


def test_rejects_token_signed_with_other_secret() -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    evil = pyjwt.encode(
        {
            "tenant_id": str(TENANT),
            "partner_id": str(PARTNER),
            "key_id": str(KEY),
            "scope": ["widget:send"],
            "allowed_origins": [],
            "aud": settings.embed_app_origin,
            "iat": now,
            "exp": now + timedelta(minutes=15),
            "jti": uuid.uuid4().hex,
        },
        "some-other-secret",
        algorithm="HS256",
    )
    with pytest.raises(WidgetTokenError):
        verify_widget_token(evil)


def test_rejects_expired_token() -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    expired = pyjwt.encode(
        {
            "tenant_id": str(TENANT),
            "partner_id": str(PARTNER),
            "key_id": str(KEY),
            "scope": [],
            "allowed_origins": [],
            "aud": settings.embed_app_origin,
            "iat": now - timedelta(hours=1),
            "exp": now - timedelta(minutes=1),
            "jti": uuid.uuid4().hex,
        },
        settings.embed_jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(WidgetTokenError):
        verify_widget_token(expired)


def test_rejects_wrong_audience() -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    wrong_aud = pyjwt.encode(
        {
            "tenant_id": str(TENANT),
            "partner_id": str(PARTNER),
            "key_id": str(KEY),
            "scope": [],
            "allowed_origins": [],
            "aud": "https://evil.example",
            "iat": now,
            "exp": now + timedelta(minutes=15),
            "jti": uuid.uuid4().hex,
        },
        settings.embed_jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(WidgetTokenError):
        verify_widget_token(wrong_aud)


def test_rejects_alg_none() -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    unsigned = pyjwt.encode(
        {
            "tenant_id": str(TENANT),
            "partner_id": str(PARTNER),
            "key_id": str(KEY),
            "aud": settings.embed_app_origin,
            "iat": now,
            "exp": now + timedelta(minutes=15),
            "jti": uuid.uuid4().hex,
        },
        key=None,
        algorithm="none",
    )
    with pytest.raises(WidgetTokenError):
        verify_widget_token(unsigned)


def test_rejects_missing_jti() -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    no_jti = pyjwt.encode(
        {
            "tenant_id": str(TENANT),
            "partner_id": str(PARTNER),
            "key_id": str(KEY),
            "scope": [],
            "allowed_origins": [],
            "aud": settings.embed_app_origin,
            "iat": now,
            "exp": now + timedelta(minutes=15),
        },
        settings.embed_jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(WidgetTokenError):
        verify_widget_token(no_jti)


def test_rejects_malformed_tenant_id() -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    bad = pyjwt.encode(
        {
            "tenant_id": "not-a-uuid",
            "partner_id": str(PARTNER),
            "key_id": str(KEY),
            "scope": [],
            "allowed_origins": [],
            "aud": settings.embed_app_origin,
            "iat": now,
            "exp": now + timedelta(minutes=15),
            "jti": uuid.uuid4().hex,
        },
        settings.embed_jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(WidgetTokenError):
        verify_widget_token(bad)
