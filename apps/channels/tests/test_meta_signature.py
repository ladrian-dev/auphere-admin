"""Tests for the Meta X-Hub-Signature-256 verifier and appsecret_proof."""

from __future__ import annotations

import pytest

from nexus_channels.whatsapp_meta.signature import (
    MetaSignatureError,
    appsecret_proof,
    sign_meta_request,
    verify_meta_signature,
)


def test_round_trip_signs_and_verifies() -> None:
    secret = "app_secret_demo"
    body = b'{"object":"whatsapp_business_account","entry":[]}'
    header = sign_meta_request(secret, body)
    verify_meta_signature(secret, body, header)  # no raise


def test_rejects_wrong_secret() -> None:
    body = b'{"object":"whatsapp_business_account"}'
    header = sign_meta_request("right", body)
    with pytest.raises(MetaSignatureError, match="signature mismatch"):
        verify_meta_signature("wrong", body, header)


def test_rejects_tampered_body() -> None:
    body = b'{"object":"whatsapp_business_account"}'
    header = sign_meta_request("k", body)
    with pytest.raises(MetaSignatureError, match="signature mismatch"):
        verify_meta_signature("k", b'{"object":"x"}', header)


def test_rejects_missing_header() -> None:
    with pytest.raises(MetaSignatureError, match="missing"):
        verify_meta_signature("k", b"{}", None)
    with pytest.raises(MetaSignatureError, match="missing"):
        verify_meta_signature("k", b"{}", "")


def test_rejects_wrong_prefix() -> None:
    with pytest.raises(MetaSignatureError, match="prefix"):
        verify_meta_signature("k", b"{}", "sha1=deadbeef")


def test_rejects_extra_chars() -> None:
    secret = "s"
    body = b"{}"
    sig = sign_meta_request(secret, body)
    with pytest.raises(MetaSignatureError):
        verify_meta_signature(secret, body, sig + "00")


def test_appsecret_proof_is_deterministic_and_hex() -> None:
    proof = appsecret_proof("token-abc", "app-secret-xyz")
    assert len(proof) == 64
    assert set(proof) <= set("0123456789abcdef")
    # Same inputs → same output (no randomness).
    assert appsecret_proof("token-abc", "app-secret-xyz") == proof


def test_appsecret_proof_changes_when_either_input_changes() -> None:
    base = appsecret_proof("t1", "s1")
    assert appsecret_proof("t2", "s1") != base
    assert appsecret_proof("t1", "s2") != base
