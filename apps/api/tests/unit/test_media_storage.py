"""Block N — media storage adapter (in-memory variant) sanity tests.

The S3 path is covered by integration tests with MinIO; here we exercise
the canonical contract (put → get → presign) on the in-memory impl that
ships with the platform for dev / test environments.
"""

from __future__ import annotations

import pytest

from nexus_api.services.media_storage import (
    InMemoryMediaStorage,
    MediaStorageError,
)

pytestmark = pytest.mark.asyncio


async def test_put_inbound_returns_handle_with_size_and_sha():
    storage = InMemoryMediaStorage()
    handle = await storage.put_inbound(
        tenant_slug="cultor",
        wamid="wamid.ABC",
        content=b"hello world",
        content_type="audio/ogg",
    )
    assert handle.size_bytes == len(b"hello world")
    assert handle.content_type == "audio/ogg"
    assert handle.bucket == "memory"
    assert "cultor" in handle.key
    assert handle.key.endswith(".ogg")
    # sha256 of "hello world"
    assert handle.sha256.startswith("b94d27b9934d3e08")


async def test_put_then_get_round_trip():
    storage = InMemoryMediaStorage()
    handle = await storage.put_inbound(
        tenant_slug="cultor",
        wamid="wamid.X",
        content=b"\x89PNG fake",
        content_type="image/png",
    )
    content, ct = await storage.get_object(handle.key)
    assert content == b"\x89PNG fake"
    assert ct == "image/png"


async def test_presign_get_returns_memory_url():
    storage = InMemoryMediaStorage()
    handle = await storage.put_inbound(
        tenant_slug="cultor",
        wamid="wamid.X",
        content=b"abc",
        content_type="text/plain",
    )
    url = await storage.presign_get(handle.key)
    assert url.startswith("memory://")
    assert handle.key in url


async def test_presign_unknown_key_raises():
    storage = InMemoryMediaStorage()
    with pytest.raises(MediaStorageError):
        await storage.presign_get("inbound/nope.bin")


async def test_extension_inference_for_voice_note():
    storage = InMemoryMediaStorage()
    handle = await storage.put_inbound(
        tenant_slug="t",
        wamid="w",
        content=b"...",
        content_type=None,
        suggested_extension="ogg",
    )
    assert handle.key.endswith(".ogg")
