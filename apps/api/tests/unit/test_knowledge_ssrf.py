"""Knowledge URL ingestion refuses non-public destinations (SSRF)."""

from __future__ import annotations

import pytest

from nexus_api.services.knowledge_indexer import IndexingError, assert_public_url

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://127.0.0.1:8000/health",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "ftp://example.com/",
        "http:///nohost",
    ],
)
async def test_private_or_invalid_urls_are_refused(url: str) -> None:
    with pytest.raises(IndexingError):
        await assert_public_url(url)


async def test_public_url_passes() -> None:
    # 1.1.1.1 resolves to itself; no DNS needed and it is a global address.
    await assert_public_url("https://1.1.1.1/")
