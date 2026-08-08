"""WP-11 (D10): the runner resolves inbound media, and failure never kills
the turn.

Contract pinned here:
- ``fetch_inbound_media`` resolves provider bytes → S3 via the injected
  fetcher and the media storage, honouring the size cap;
- no fetcher wired (dev without Meta creds) → ``None``, no exception;
- provider/storage failure → ``None``, no exception — the dispatcher then
  runs the turn text-only and the agent asks the customer to resend.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from nexus_worker.multimodal import media_fetch

pytestmark = pytest.mark.asyncio


@dataclass
class _Stored:
    key: str
    content_type: str | None
    size_bytes: int
    sha256: str | None


class _FakeStorage:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def put_inbound(self, *, tenant_slug, wamid, content, content_type, sha256):
        self.calls.append({"tenant_slug": tenant_slug, "wamid": wamid, "size": len(content)})
        return _Stored(
            key=f"{tenant_slug}/inbound/{wamid}.bin",
            content_type=content_type,
            size_bytes=len(content),
            sha256=sha256,
        )


@pytest.fixture(autouse=True)
def _reset_fetcher():
    yield
    media_fetch.set_media_fetcher(None)


@pytest.fixture
def storage(monkeypatch) -> _FakeStorage:
    fake = _FakeStorage()
    monkeypatch.setattr(media_fetch, "get_media_storage", lambda: fake)

    async def slug(_tid):
        return "tenant-slug"

    monkeypatch.setattr(media_fetch, "_tenant_slug_for", slug)
    return fake


async def test_fetch_resolves_bytes_to_s3(storage) -> None:
    seen: dict = {}

    async def fetcher(*, media_id, tenant_id, channel_id):
        seen["media_id"] = media_id
        seen["channel_id"] = channel_id
        return (b"x" * 100, "audio/ogg", "sha-abc")

    media_fetch.set_media_fetcher(fetcher)
    channel_id = uuid.uuid4()

    fetched = await media_fetch.fetch_inbound_media(
        tenant_id=uuid.uuid4(),
        channel_id=channel_id,
        provider_message_id="wamid.audio-1",
        media_provider_id="MEDIA-9",
    )

    assert fetched is not None
    assert fetched.s3_key == "tenant-slug/inbound/wamid.audio-1.bin"
    assert fetched.mime == "audio/ogg"
    assert fetched.size_bytes == 100
    # The download is scoped to the channel that received the message.
    assert seen["channel_id"] == channel_id
    assert seen["media_id"] == "MEDIA-9"


async def test_no_fetcher_wired_returns_none(storage) -> None:
    media_fetch.set_media_fetcher(None)
    fetched = await media_fetch.fetch_inbound_media(
        tenant_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        provider_message_id="wamid.x",
        media_provider_id="MEDIA-1",
    )
    assert fetched is None
    assert storage.calls == []


async def test_provider_failure_degrades_to_none(storage) -> None:
    async def fetcher(*, media_id, tenant_id, channel_id):
        raise RuntimeError("graph api down")

    media_fetch.set_media_fetcher(fetcher)
    fetched = await media_fetch.fetch_inbound_media(
        tenant_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        provider_message_id="wamid.x",
        media_provider_id="MEDIA-1",
    )
    assert fetched is None


async def test_oversized_media_is_rejected(storage, monkeypatch) -> None:
    class _Settings:
        media_max_size_mb = 1

    monkeypatch.setattr(media_fetch, "get_settings", lambda: _Settings())

    async def fetcher(*, media_id, tenant_id, channel_id):
        return (b"x" * (2 * 1024 * 1024), "video/mp4", None)

    media_fetch.set_media_fetcher(fetcher)
    fetched = await media_fetch.fetch_inbound_media(
        tenant_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        provider_message_id="wamid.big",
        media_provider_id="MEDIA-BIG",
    )
    assert fetched is None
    assert storage.calls == []  # rejected before touching storage
