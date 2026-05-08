"""Custom SQLAlchemy types used across models."""

from __future__ import annotations

from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import LargeBinary, TypeDecorator

from nexus_api.config import get_settings


class FernetEncrypted(TypeDecorator[bytes]):
    """Stores bytes encrypted at rest with Fernet.

    The plaintext column type is `bytes`. The DB column type is `BYTEA`. The Fernet
    key comes from `settings.fernet_key`. Rotation: read with both keys and re-write
    with the new one (out of scope for block B; documented as a phase 2 task).
    """

    impl = LargeBinary
    cache_ok = True

    @property
    def python_type(self) -> type[bytes]:
        return bytes

    def _fernet(self) -> Fernet:
        return Fernet(get_settings().fernet_key.encode())

    def process_bind_param(self, value: Any, dialect: Any) -> bytes | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.encode("utf-8")
        if not isinstance(value, bytes):
            raise TypeError(f"FernetEncrypted requires bytes or str, got {type(value)!r}")
        return self._fernet().encrypt(value)

    def process_result_value(self, value: Any, dialect: Any) -> bytes | None:
        if value is None:
            return None
        if isinstance(value, memoryview):
            value = bytes(value)
        try:
            return self._fernet().decrypt(value)
        except InvalidToken as exc:
            raise ValueError("FernetEncrypted: failed to decrypt — wrong key?") from exc
