"""Media storage adapter — S3-compatible (AWS, Cloudflare R2, MinIO).

Two operations the platform performs:

- ``put_inbound`` — store an inbound media object the moment the webhook
  downloads it from Meta. Keyed by tenant + wamid + extension.
- ``presign_outbound`` — given an in-bucket key (typically an asset the
  operator uploaded ahead of time, or an inbound piece we want to forward),
  return a short-TTL HTTPS URL the Cloud API can fetch.

The adapter is intentionally lightweight: boto3 is the only third-party
dependency, and ``aioboto3`` is preferred but optional — we offload the
synchronous calls to a worker thread when only boto3 is available so the
async event loop stays unblocked.

When ``Settings.media_s3_enabled`` is False, :class:`InMemoryMediaStorage`
is used. It is **only** for tests and local dev; uploading anything large
will leak memory.
"""

from __future__ import annotations

from nexus_api.services.media_storage.storage import (
    InMemoryMediaStorage,
    MediaStorage,
    MediaStorageError,
    S3MediaStorage,
    StoredMedia,
    get_media_storage,
)

__all__ = [
    "InMemoryMediaStorage",
    "MediaStorage",
    "MediaStorageError",
    "S3MediaStorage",
    "StoredMedia",
    "get_media_storage",
]
