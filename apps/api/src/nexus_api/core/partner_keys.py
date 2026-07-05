"""Partner API key generation and verification primitives (ADR-028).

Key format: ``ak_<type>_<27 chars base62><6 chars base62 CRC32>``

- ``ak_`` prefix + type makes keys self-identifying for secret scanners
  (GitHub secret scanning partner program, trufflehog rules).
- 27 base62 chars ≈ 160 bits of entropy from ``secrets``.
- The trailing 6 base62 chars encode a CRC32 checksum of everything
  before them, so an auth middleware can reject typos and garbage
  offline — before spending a DB roundtrip.

Storage is a plain SHA-256 hex digest. The key is high-entropy, so a
slow password hash (bcrypt/argon2) would add per-request latency
without any security benefit — there is no low-entropy secret to
brute-force. This is the industry standard for API tokens (GitHub,
Stripe).
"""

from __future__ import annotations

import hashlib
import secrets
import zlib
from dataclasses import dataclass

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_SECRET_LEN = 27  # ceil(160 bits / log2(62))
_CHECKSUM_LEN = 6  # 62^6 > 2^32 — fits any CRC32 value
_PREFIX_SNIPPET_LEN = 12  # 'ak_live_4f9c' — display/identification only


@dataclass(frozen=True)
class GeneratedKey:
    """The plaintext is returned exactly once, at generation time."""

    plaintext: str
    key_hash: str
    prefix_snippet: str


def _base62(value: int, length: int) -> str:
    chars: list[str] = []
    for _ in range(length):
        value, rem = divmod(value, 62)
        chars.append(_ALPHABET[rem])
    return "".join(reversed(chars))


def _checksum(body: str) -> str:
    return _base62(zlib.crc32(body.encode("ascii")), _CHECKSUM_LEN)


def generate_api_key(key_type: str = "live") -> GeneratedKey:
    secret = "".join(secrets.choice(_ALPHABET) for _ in range(_SECRET_LEN))
    body = f"ak_{key_type}_{secret}"
    plaintext = body + _checksum(body)
    return GeneratedKey(
        plaintext=plaintext,
        key_hash=hash_key(plaintext),
        prefix_snippet=plaintext[:_PREFIX_SNIPPET_LEN],
    )


def checksum_ok(plaintext: str) -> bool:
    """Cheap offline validity check — run BEFORE any DB lookup."""
    if not plaintext.startswith("ak_") or len(plaintext) <= _CHECKSUM_LEN:
        return False
    body, checksum = plaintext[:-_CHECKSUM_LEN], plaintext[-_CHECKSUM_LEN:]
    return _checksum(body) == checksum


def hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("ascii")).hexdigest()
