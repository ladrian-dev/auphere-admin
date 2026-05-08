import hashlib
import hmac

import pytest

from nexus_api.core.errors import HMACVerificationFailed
from nexus_api.core.security import compute_hmac_sha256, verify_hmac


def _signature(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_compute_hmac_matches_stdlib():
    body = b'{"event":"x"}'
    assert compute_hmac_sha256("k", body) == _signature("k", body)


def test_verify_hmac_accepts_matching_signature():
    body = b"payload"
    sig = _signature("secret", body)
    verify_hmac("secret", body, sig)


def test_verify_hmac_accepts_prefixed_signature():
    body = b"payload"
    sig = "sha256=" + _signature("secret", body)
    verify_hmac("secret", body, sig)


def test_verify_hmac_rejects_wrong_secret():
    with pytest.raises(HMACVerificationFailed):
        verify_hmac("wrong", b"payload", _signature("secret", b"payload"))


def test_verify_hmac_rejects_wrong_body():
    with pytest.raises(HMACVerificationFailed):
        verify_hmac("secret", b"different", _signature("secret", b"payload"))


def test_verify_hmac_rejects_missing_signature():
    with pytest.raises(HMACVerificationFailed):
        verify_hmac("secret", b"payload", "")


def test_verify_hmac_is_constant_time():
    # Sanity: verify_hmac uses hmac.compare_digest which is constant-time.
    # We don't measure timing here; we just confirm the wrong sig still raises
    # for two near-identical strings (same length, single bit diff).
    body = b"payload"
    correct = _signature("secret", body)
    wrong = correct[:-1] + ("0" if correct[-1] != "0" else "1")
    with pytest.raises(HMACVerificationFailed):
        verify_hmac("secret", body, wrong)
