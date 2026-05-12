"""Unit tests for the consent token signer.

Covers the security-critical paths: tamper detection, expiry, wrong secret,
malformed input, tenant binding.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from nexus_api.services.connectors.consent_token import (
    ConsentTokenExpired,
    ConsentTokenInvalid,
    sign_consent_token,
    verify_consent_token,
)

SECRET = "test-secret-min-32-chars-padding-extra"


def test_sign_verify_roundtrip() -> None:
    t = uuid.uuid4()
    c = uuid.uuid4()
    token, payload = sign_consent_token(tenant_id=t, connector_id=c, secret=SECRET)
    out = verify_consent_token(token=token, secret=SECRET)
    assert out.tenant_id == t
    assert out.connector_id == c
    assert out.nonce == payload.nonce


def test_tamper_rejected() -> None:
    t = uuid.uuid4()
    c = uuid.uuid4()
    token, _ = sign_consent_token(tenant_id=t, connector_id=c, secret=SECRET)
    with pytest.raises(ConsentTokenInvalid):
        verify_consent_token(token=token + "x", secret=SECRET)


def test_wrong_secret_rejected() -> None:
    t = uuid.uuid4()
    c = uuid.uuid4()
    token, _ = sign_consent_token(tenant_id=t, connector_id=c, secret=SECRET)
    with pytest.raises(ConsentTokenInvalid):
        verify_consent_token(token=token, secret="other-secret-32-chars-min-len")


def test_expired_rejected() -> None:
    t = uuid.uuid4()
    c = uuid.uuid4()
    token, _ = sign_consent_token(
        tenant_id=t,
        connector_id=c,
        secret=SECRET,
        ttl=timedelta(seconds=-1),
    )
    with pytest.raises(ConsentTokenExpired):
        verify_consent_token(token=token, secret=SECRET)


@pytest.mark.parametrize(
    "bad",
    ["", "no-separator", ".", "aaa.bbb!!!", "...", "bad-base64.bad-base64"],
)
def test_malformed_rejected(bad: str) -> None:
    with pytest.raises(ConsentTokenInvalid):
        verify_consent_token(token=bad, secret=SECRET)


def test_payload_field_typo_rejected() -> None:
    """A token whose payload doesn't decode as proper JSON or whose UUIDs are
    bad must raise ConsentTokenInvalid — never silently pass."""
    # Forge a token with the right signature but a junk payload field.
    import base64
    import hashlib
    import hmac
    import json

    raw = json.dumps({"t": "not-a-uuid", "c": "x", "n": "n", "e": 9999999999}).encode()
    sig = hmac.new(SECRET.encode(), raw, hashlib.sha256).digest()
    token = (
        base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
        + "."
        + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    )
    with pytest.raises(ConsentTokenInvalid):
        verify_consent_token(token=token, secret=SECRET)


def test_empty_secret_raises() -> None:
    t = uuid.uuid4()
    with pytest.raises(ValueError):
        sign_consent_token(tenant_id=t, connector_id=t, secret="")
    with pytest.raises(ValueError):
        verify_consent_token(token="aaa.bbb", secret="")


def test_default_ttl_is_seven_days() -> None:
    t = uuid.uuid4()
    before = datetime.now(UTC)
    _, payload = sign_consent_token(tenant_id=t, connector_id=t, secret=SECRET)
    delta = payload.expires_at - before
    assert timedelta(days=6, hours=23) <= delta <= timedelta(days=7, seconds=1)
