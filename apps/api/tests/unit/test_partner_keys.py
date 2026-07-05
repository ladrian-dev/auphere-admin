"""Unit tests for partner API key generation/verification (ADR-028)."""

from __future__ import annotations

from nexus_api.core.partner_keys import (
    GeneratedKey,
    checksum_ok,
    generate_api_key,
    hash_key,
)


def test_generated_key_shape() -> None:
    key = generate_api_key("live")
    assert key.plaintext.startswith("ak_live_")
    # ak_live_ (8) + 27 secret + 6 checksum
    assert len(key.plaintext) == 8 + 27 + 6
    assert key.prefix_snippet == key.plaintext[:12]
    assert key.key_hash == hash_key(key.plaintext)
    assert len(key.key_hash) == 64  # sha256 hex


def test_test_type_key_prefix() -> None:
    assert generate_api_key("test").plaintext.startswith("ak_test_")


def test_checksum_roundtrip() -> None:
    key = generate_api_key()
    assert checksum_ok(key.plaintext)


def test_checksum_rejects_tampering() -> None:
    key = generate_api_key()
    # Flip one char in the secret body — checksum must catch it.
    body = key.plaintext
    pos = 10
    flipped = body[:pos] + ("A" if body[pos] != "A" else "B") + body[pos + 1 :]
    assert not checksum_ok(flipped)


def test_checksum_rejects_garbage() -> None:
    assert not checksum_ok("")
    assert not checksum_ok("ak_")
    assert not checksum_ok("not-a-key")
    assert not checksum_ok("sk_live_" + "x" * 33)


def test_keys_are_unique() -> None:
    keys = {generate_api_key().plaintext for _ in range(50)}
    assert len(keys) == 50


def test_hash_is_deterministic() -> None:
    key: GeneratedKey = generate_api_key()
    assert hash_key(key.plaintext) == hash_key(key.plaintext)
