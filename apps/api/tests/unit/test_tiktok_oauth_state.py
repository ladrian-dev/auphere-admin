"""The signed OAuth ``state`` that carries a tenant through TikTok's redirect.

This sits on the isolation boundary. TikTok's callback arrives with no admin
token and no session, so ``state`` is the *only* thing naming the tenant being
connected. If it could be forged, anyone able to reach the callback could
attach their own TikTok account to someone else's tenant.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from nexus_api.services.tiktok_oauth_state import (
    OAuthStateExpired,
    OAuthStateInvalid,
    sign_oauth_state,
    verify_oauth_state,
)

SECRET = "state-secret-at-least-32-characters-long"
NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()


def test_roundtrips_the_tenant_it_was_signed_for() -> None:
    state, payload = sign_oauth_state(tenant_id=TENANT_A, secret=SECRET, now=NOW)
    verified = verify_oauth_state(state=state, secret=SECRET, now=NOW)

    assert verified.tenant_id == TENANT_A
    assert verified.nonce == payload.nonce


def test_a_state_signed_with_another_secret_is_rejected() -> None:
    state, _ = sign_oauth_state(tenant_id=TENANT_A, secret="a-completely-different-secret", now=NOW)

    with pytest.raises(OAuthStateInvalid, match="HMAC mismatch"):
        verify_oauth_state(state=state, secret=SECRET, now=NOW)


def test_swapping_the_tenant_id_invalidates_the_signature() -> None:
    """The attack this module exists to stop: repoint a valid state at
    another tenant and connect your account to theirs."""
    state, _ = sign_oauth_state(tenant_id=TENANT_A, secret=SECRET, now=NOW)
    raw_b64, sig_b64 = state.split(".", 1)

    payload = json.loads(base64.urlsafe_b64decode(raw_b64 + "=" * (-len(raw_b64) % 4)))
    payload["t"] = str(TENANT_B)
    tampered_raw = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).rstrip(b"=")
    tampered = f"{tampered_raw.decode()}.{sig_b64}"

    with pytest.raises(OAuthStateInvalid):
        verify_oauth_state(state=tampered, secret=SECRET, now=NOW)


def test_an_expired_state_is_rejected() -> None:
    state, _ = sign_oauth_state(
        tenant_id=TENANT_A, secret=SECRET, ttl=timedelta(minutes=30), now=NOW
    )

    with pytest.raises(OAuthStateExpired):
        verify_oauth_state(state=state, secret=SECRET, now=NOW + timedelta(minutes=31))


def test_a_state_stays_valid_for_a_normal_round_trip() -> None:
    state, _ = sign_oauth_state(tenant_id=TENANT_A, secret=SECRET, now=NOW)

    verify_oauth_state(state=state, secret=SECRET, now=NOW + timedelta(minutes=2))


def test_two_states_for_the_same_tenant_differ() -> None:
    """Nonced, so one authorisation can't be mistaken for another in logs."""
    first, _ = sign_oauth_state(tenant_id=TENANT_A, secret=SECRET, now=NOW)
    second, _ = sign_oauth_state(tenant_id=TENANT_A, secret=SECRET, now=NOW)

    assert first != second


@pytest.mark.parametrize("state", ["", "nodot", "a.b", "!!!.???"])
def test_malformed_states_are_rejected(state: str) -> None:
    with pytest.raises(OAuthStateInvalid):
        verify_oauth_state(state=state, secret=SECRET, now=NOW)


def test_an_empty_secret_is_a_programming_error_not_a_soft_failure() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        sign_oauth_state(tenant_id=TENANT_A, secret="", now=NOW)
    with pytest.raises(ValueError, match="non-empty"):
        verify_oauth_state(state="a.b", secret="", now=NOW)
