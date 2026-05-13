"""S3-compatible media storage adapter.

Implementation notes:

- The boto3 client is sync. We wrap every call in
  ``asyncio.to_thread`` so the FastAPI event loop never blocks on the
  network. boto3 itself reuses connections via its session, so the
  thread-pool cost is amortised after the first call.
- ``StoredMedia`` is the canonical handle returned by ``put_inbound``;
  it carries the S3 key, the bucket, the content-type and the size so
  the caller can persist directly into ``messages.media_*`` columns.
- Object keys: ``inbound/{tenant_slug}/{yyyy}/{mm}/{dd}/{wamid}.{ext}``.
  The slug-not-id prefix makes lifecycle policies and bucket
  inspection human-readable; the tenant slug is stable for the lifetime
  of the tenant and IDs are easier to recover from the path. The
  ``yyyy/mm/dd`` shard keeps any given prefix below S3's 3500 PUT/s
  limit even for high-volume tenants.
"""

from __future__ import annotations

import abc
import asyncio
import hashlib
import logging
import mimetypes
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from nexus_api.config import get_settings

log = logging.getLogger(__name__)


class MediaStorageError(RuntimeError):
    """Raised when an upload, presign or fetch fails."""


@dataclass(frozen=True)
class StoredMedia:
    """Handle returned by ``put_inbound``. Carries everything the caller
    needs to persist into ``messages.media_*``."""

    bucket: str
    key: str
    content_type: str
    size_bytes: int
    sha256: str


class MediaStorage(abc.ABC):
    """Storage interface. Two impls: S3 (prod) and in-memory (tests)."""

    @abc.abstractmethod
    async def put_inbound(
        self,
        *,
        tenant_slug: str,
        wamid: str,
        content: bytes,
        content_type: str | None,
        suggested_extension: str | None = None,
        sha256: str | None = None,
    ) -> StoredMedia:
        """Store an inbound media object. Returns the canonical handle."""

    @abc.abstractmethod
    async def put_outbound(
        self,
        *,
        tenant_slug: str,
        content: bytes,
        content_type: str,
        filename: str | None = None,
    ) -> StoredMedia:
        """Store an outbound media object ahead of generating a presigned URL."""

    @abc.abstractmethod
    async def presign_get(self, key: str, *, ttl_seconds: int | None = None) -> str:
        """Return a short-TTL HTTPS URL Meta/YCloud can fetch."""

    @abc.abstractmethod
    async def get_object(self, key: str) -> tuple[bytes, str]:
        """Read an object's bytes + content-type. Used by the multimodal pipeline."""


# ── helpers ─────────────────────────────────────────────────────────────────


def _extension_for(content_type: str | None, suggested: str | None) -> str:
    if suggested:
        # Strip any leading "."; normalise common aliases.
        ext = suggested.lstrip(".").lower()
        if ext:
            return ext
    if content_type:
        guess = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
        if guess:
            return guess.lstrip(".")
        # WhatsApp commonly serves audio as audio/ogg; codecs=opus — split
        # the parameter and try again.
        if content_type.startswith("audio/ogg"):
            return "ogg"
        if content_type.startswith("audio/mp4") or content_type == "audio/aac":
            return "m4a"
    return "bin"


def _key_for_inbound(*, tenant_slug: str, wamid: str, extension: str) -> str:
    now = datetime.now(UTC)
    safe_wamid = wamid.replace("/", "_").replace(" ", "_")[:200]
    return (
        f"inbound/{tenant_slug}/{now.year:04d}/{now.month:02d}/{now.day:02d}/"
        f"{safe_wamid}.{extension}"
    )


def _key_for_outbound(*, tenant_slug: str, filename: str | None, extension: str) -> str:
    now = datetime.now(UTC)
    base = uuid.uuid4().hex[:16]
    if filename:
        # Best-effort preserve the operator's filename for documents.
        clean = "".join(c for c in filename if c.isalnum() or c in "._-")
        if clean:
            return (
                f"outbound/{tenant_slug}/{now.year:04d}/{now.month:02d}/{now.day:02d}/"
                f"{base}_{clean[:120]}"
            )
    return (
        f"outbound/{tenant_slug}/{now.year:04d}/{now.month:02d}/{now.day:02d}/"
        f"{base}.{extension}"
    )


# ── S3 impl ─────────────────────────────────────────────────────────────────


class S3MediaStorage(MediaStorage):
    """Real S3-compatible storage. Built on synchronous boto3 wrapped via
    ``asyncio.to_thread`` so the event loop doesn't block on PUT/GET."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint_url: str | None,
        access_key_id: str,
        secret_access_key: str,
        presign_ttl_seconds: int,
        sse_enabled: bool,
    ) -> None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover — runtime guard
            msg = "boto3 is required for S3MediaStorage; add `boto3>=1.34` to deps"
            raise RuntimeError(msg) from exc
        self._bucket = bucket
        self._presign_ttl = presign_ttl_seconds
        self._sse_enabled = sse_enabled
        # virtual-host style breaks against MinIO and Cloudflare R2 — fall
        # back to path style when an endpoint_url is configured.
        s3_config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if endpoint_url else "virtual"},
        )
        self._client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key_id or None,
            aws_secret_access_key=secret_access_key or None,
            config=s3_config,
        )

    async def put_inbound(
        self,
        *,
        tenant_slug: str,
        wamid: str,
        content: bytes,
        content_type: str | None,
        suggested_extension: str | None = None,
        sha256: str | None = None,
    ) -> StoredMedia:
        ext = _extension_for(content_type, suggested_extension)
        key = _key_for_inbound(tenant_slug=tenant_slug, wamid=wamid, extension=ext)
        normalised_ct = content_type or mimetypes.guess_type(f"file.{ext}")[0] or "application/octet-stream"
        digest = sha256 or hashlib.sha256(content).hexdigest()
        await self._put(key=key, body=content, content_type=normalised_ct)
        return StoredMedia(
            bucket=self._bucket,
            key=key,
            content_type=normalised_ct,
            size_bytes=len(content),
            sha256=digest,
        )

    async def put_outbound(
        self,
        *,
        tenant_slug: str,
        content: bytes,
        content_type: str,
        filename: str | None = None,
    ) -> StoredMedia:
        ext = _extension_for(content_type, suggested=None)
        key = _key_for_outbound(tenant_slug=tenant_slug, filename=filename, extension=ext)
        digest = hashlib.sha256(content).hexdigest()
        await self._put(key=key, body=content, content_type=content_type)
        return StoredMedia(
            bucket=self._bucket,
            key=key,
            content_type=content_type,
            size_bytes=len(content),
            sha256=digest,
        )

    async def presign_get(self, key: str, *, ttl_seconds: int | None = None) -> str:
        ttl = ttl_seconds or self._presign_ttl
        return await asyncio.to_thread(self._presign_blocking, key, ttl)

    async def get_object(self, key: str) -> tuple[bytes, str]:
        return await asyncio.to_thread(self._get_blocking, key)

    # ── blocking helpers ─────────────────────────────────────────────────────

    def _put_blocking(self, *, key: str, body: bytes, content_type: str) -> None:
        params: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": body,
            "ContentType": content_type,
        }
        if self._sse_enabled:
            params["ServerSideEncryption"] = "AES256"
        self._client.put_object(**params)

    async def _put(self, *, key: str, body: bytes, content_type: str) -> None:
        try:
            await asyncio.to_thread(
                self._put_blocking, key=key, body=body, content_type=content_type
            )
        except Exception as exc:  # noqa: BLE001 — translate to typed error
            raise MediaStorageError(f"s3 PUT failed for {key}: {exc}") from exc

    def _presign_blocking(self, key: str, ttl: int) -> str:
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=ttl,
            )
        except Exception as exc:  # noqa: BLE001
            raise MediaStorageError(f"s3 presign failed for {key}: {exc}") from exc

    def _get_blocking(self, key: str) -> tuple[bytes, str]:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            body = response["Body"].read()
            ct = response.get("ContentType") or "application/octet-stream"
            return body, ct
        except Exception as exc:  # noqa: BLE001
            raise MediaStorageError(f"s3 GET failed for {key}: {exc}") from exc


# ── in-memory impl (tests + dev without S3) ─────────────────────────────────


class InMemoryMediaStorage(MediaStorage):
    """Process-local map. Useful for unit tests + ``docker-compose`` dev
    when no S3 is wired. Returns a fake ``data:`` URL on presign so the
    media outbound path can still be exercised end-to-end."""

    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, str]] = {}

    async def put_inbound(
        self,
        *,
        tenant_slug: str,
        wamid: str,
        content: bytes,
        content_type: str | None,
        suggested_extension: str | None = None,
        sha256: str | None = None,
    ) -> StoredMedia:
        ext = _extension_for(content_type, suggested_extension)
        key = _key_for_inbound(tenant_slug=tenant_slug, wamid=wamid, extension=ext)
        ct = content_type or "application/octet-stream"
        digest = sha256 or hashlib.sha256(content).hexdigest()
        self._objects[key] = (content, ct)
        return StoredMedia(
            bucket="memory",
            key=key,
            content_type=ct,
            size_bytes=len(content),
            sha256=digest,
        )

    async def put_outbound(
        self,
        *,
        tenant_slug: str,
        content: bytes,
        content_type: str,
        filename: str | None = None,
    ) -> StoredMedia:
        ext = _extension_for(content_type, suggested=None)
        key = _key_for_outbound(tenant_slug=tenant_slug, filename=filename, extension=ext)
        digest = hashlib.sha256(content).hexdigest()
        self._objects[key] = (content, content_type)
        return StoredMedia(
            bucket="memory",
            key=key,
            content_type=content_type,
            size_bytes=len(content),
            sha256=digest,
        )

    async def presign_get(self, key: str, *, ttl_seconds: int | None = None) -> str:
        if key not in self._objects:
            raise MediaStorageError(f"in-memory storage: unknown key {key!r}")
        return f"memory://{key}"

    async def get_object(self, key: str) -> tuple[bytes, str]:
        if key not in self._objects:
            raise MediaStorageError(f"in-memory storage: unknown key {key!r}")
        return self._objects[key]


# ── singleton accessor ──────────────────────────────────────────────────────


_singleton: MediaStorage | None = None


def get_media_storage() -> MediaStorage:
    """Return the process-wide storage adapter.

    Picks S3MediaStorage when settings are populated; falls back to
    InMemoryMediaStorage otherwise. The singleton lives for the whole
    process — boto3 reuses its connection pool which is what makes the
    PUT path cheap.
    """
    global _singleton
    if _singleton is not None:
        return _singleton
    settings = get_settings()
    if settings.media_s3_enabled:
        _singleton = S3MediaStorage(
            bucket=settings.media_s3_bucket,
            region=settings.media_s3_region,
            endpoint_url=settings.media_s3_endpoint_url,
            access_key_id=settings.media_s3_access_key_id,
            secret_access_key=settings.media_s3_secret_access_key,
            presign_ttl_seconds=settings.media_s3_presign_ttl_seconds,
            sse_enabled=settings.media_s3_sse_enabled,
        )
    else:
        log.warning(
            "media_storage.using_in_memory",
            extra={"reason": "S3 settings incomplete; only safe in tests/dev"},
        )
        _singleton = InMemoryMediaStorage()
    return _singleton


def set_media_storage(storage: MediaStorage | None) -> None:
    """Test hook to inject a fake storage instance (or reset to default)."""
    global _singleton
    _singleton = storage
