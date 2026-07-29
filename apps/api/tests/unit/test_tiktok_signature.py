"""Signature verification for TikTok webhooks.

This is the security boundary of the channel: everything downstream trusts
that a payload reaching the parser really came from TikTok. The cases below
are the failure modes that actually happen in production — a rotated app
secret, a framework that re-serialised the body, and a replayed capture.
"""

from __future__ import annotations

import json

import pytest
from nexus_channels.tiktok_bm.exceptions import TikTokInvalidSignatureError
from nexus_channels.tiktok_bm.signature import (
    sign_tiktok_request,
    verify_tiktok_signature,
)

SECRET = "tiktok-app-secret"
NOW = 1_800_000_000
BODY = b'{"event":"message_received","business_id":"7123"}'


def test_accepts_a_signature_it_just_produced() -> None:
    header = sign_tiktok_request(SECRET, BODY, timestamp=NOW)
    verify_tiktok_signature(SECRET, BODY, header, now=NOW)


def test_rejects_a_signature_made_with_a_different_secret() -> None:
    header = sign_tiktok_request("some-other-secret", BODY, timestamp=NOW)
    with pytest.raises(TikTokInvalidSignatureError, match="signature mismatch"):
        verify_tiktok_signature(SECRET, BODY, header, now=NOW)


def test_rejects_a_body_that_was_reserialised() -> None:
    """The classic footgun: json.loads -> json.dumps produces semantically
    identical JSON with different bytes, and the HMAC no longer matches."""
    header = sign_tiktok_request(SECRET, BODY, timestamp=NOW)
    reserialised = json.dumps(json.loads(BODY)).encode("utf-8")

    assert reserialised != BODY
    with pytest.raises(TikTokInvalidSignatureError):
        verify_tiktok_signature(SECRET, reserialised, header, now=NOW)


def test_rejects_a_replay_outside_the_tolerance_window() -> None:
    header = sign_tiktok_request(SECRET, BODY, timestamp=NOW)
    with pytest.raises(TikTokInvalidSignatureError, match="tolerance"):
        verify_tiktok_signature(SECRET, BODY, header, now=NOW + 3600)


def test_accepts_a_delivery_that_is_merely_late() -> None:
    """A minute of lag is ordinary queueing, not an attack — rejecting it
    would silently drop real customer messages."""
    header = sign_tiktok_request(SECRET, BODY, timestamp=NOW)
    verify_tiktok_signature(SECRET, BODY, header, now=NOW + 60)


def test_tolerance_zero_disables_the_freshness_check() -> None:
    header = sign_tiktok_request(SECRET, BODY, timestamp=NOW)
    verify_tiktok_signature(SECRET, BODY, header, tolerance_seconds=0, now=NOW + 10**6)


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "deadbeef",
        "t=notanumber,s=deadbeef",
        "s=deadbeef",
        "t=1800000000",
        "t=1800000000,s=",
    ],
)
def test_rejects_missing_or_malformed_headers(header: str | None) -> None:
    with pytest.raises(TikTokInvalidSignatureError):
        verify_tiktok_signature(SECRET, BODY, header, now=NOW)


def test_tolerates_unknown_extra_fields_in_the_header() -> None:
    """TikTok has added fields to signature headers before; an unknown key
    must not break verification of the ones we do understand."""
    base = sign_tiktok_request(SECRET, BODY, timestamp=NOW)
    verify_tiktok_signature(SECRET, BODY, f"{base},v=2", now=NOW)
