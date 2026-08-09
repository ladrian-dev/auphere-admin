"""Inbound media fetch — runner-side (WP-11 / D10, plataforma v2 Fase 1).

Closes V7: the webhook used to download media bytes from Meta INSIDE the
request handler, so a burst of voice notes saturated the API's pool and
uvicorn while Meta waited for its 200. Now the webhook publishes only the
``media_provider_id`` and the runner resolves bytes → S3 here, before
``classify``.

The fetcher is process-injected (``set_media_fetcher`` from bootstrap) so
the dispatcher stays constructor-free and tests can substitute a fake. A
fetch failure is non-fatal by contract: the turn continues without the
media and the agent asks the customer to resend — same degradation the
webhook-side download had.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import structlog
from nexus_api.config import get_settings
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Tenant
from nexus_api.services.media_storage import MediaStorageError, get_media_storage
from sqlalchemy import select

log = structlog.get_logger(__name__)


@dataclass
class FetchedMedia:
    s3_key: str
    mime: str | None
    size_bytes: int
    sha256: str | None


# adapter.fetch_media_bytes-compatible: (media_id, tenant_id, channel_id) →
# (content, mime, sha256)
MediaBytesFetcher = Callable[..., Awaitable[tuple[bytes, str | None, str | None]]]

_media_bytes_fetcher: MediaBytesFetcher | None = None


def set_media_fetcher(fetcher: MediaBytesFetcher | None) -> None:
    """Wire the provider-bytes fetcher (bootstrap passes the Meta adapter's
    ``fetch_media_bytes``; tests pass a fake)."""
    global _media_bytes_fetcher
    _media_bytes_fetcher = fetcher


async def _tenant_slug_for(tenant_id: uuid.UUID) -> str:
    sm = get_sessionmaker()
    async with sm() as session:
        slug = await session.scalar(select(Tenant.slug).where(Tenant.id == tenant_id))
    return slug or str(tenant_id)


async def fetch_inbound_media(
    *,
    tenant_id: uuid.UUID,
    channel_id: uuid.UUID,
    provider_message_id: str,
    media_provider_id: str,
    hint_mime: str | None = None,
    hint_sha: str | None = None,
) -> FetchedMedia | None:
    """Resolve a provider media id to an S3 object. Returns None when no
    fetcher is wired (dev without Meta creds) or on any failure — the
    caller degrades to a text-only turn, never dies."""
    if _media_bytes_fetcher is None:
        log.warning("media_fetch.no_fetcher_wired", tenant_id=str(tenant_id))
        return None
    settings = get_settings()
    try:
        # ``channel_id`` scopes the token: a media id belongs to the WABA
        # that received it.
        content, mime, sha = await _media_bytes_fetcher(
            media_id=media_provider_id, tenant_id=tenant_id, channel_id=channel_id
        )
        if not mime and hint_mime:
            mime = hint_mime
        if not sha and hint_sha:
            sha = hint_sha
        size = len(content)
        if size > settings.media_max_size_mb * 1024 * 1024:
            raise MediaStorageError(
                f"inbound media too large: {size} bytes > {settings.media_max_size_mb}MB limit"
            )
        storage = get_media_storage()
        stored = await storage.put_inbound(
            tenant_slug=await _tenant_slug_for(tenant_id),
            wamid=provider_message_id,
            content=content,
            content_type=mime,
            sha256=sha,
        )
        return FetchedMedia(
            s3_key=stored.key,
            mime=stored.content_type,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
        )
    except Exception as exc:
        log.warning(
            "media_fetch.failed",
            tenant_id=str(tenant_id),
            media_id=media_provider_id,
            error=str(exc),
        )
        return None
