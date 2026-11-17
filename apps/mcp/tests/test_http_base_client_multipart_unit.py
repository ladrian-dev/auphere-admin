"""El cliente HTTP compartido envía ``multipart/form-data`` (spec 061, T004;
requisitos 3.8 y 4.2) sin cambiar lo que ya hacía con JSON.

Un transporte falso guarda la petición tal como sale.
"""

from __future__ import annotations

import json

import httpx
import pytest

from nexus_mcp.http import BaseHTTPConnectorClient

pytestmark = [pytest.mark.unit]


def _client(seen: list[httpx.Request]) -> BaseHTTPConnectorClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    return BaseHTTPConnectorClient(
        base_url="https://api.example.test/v1",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )


async def test_json_requests_are_unchanged() -> None:
    seen: list[httpx.Request] = []
    _, body = await _client(seen).request("POST", "/things", json={"a": 1}, params={"q": "x"})
    assert body == {"ok": True}
    (req,) = seen
    assert req.headers["content-type"] == "application/json"
    assert json.loads(req.content) == {"a": 1}
    assert dict(req.url.params) == {"q": "x"}


async def test_files_go_as_multipart_with_their_field_names_in_order() -> None:
    seen: list[httpx.Request] = []
    files = [
        ("files[]", ("foto-1.jpg", b"\xff\xd8one", "image/jpeg")),
        ("files[]", ("foto-2.png", b"\x89PNGtwo", "image/png")),
    ]
    await _client(seen).request("POST", "/media", files=files, data={"note": "hola"})
    (req,) = seen
    assert req.headers["content-type"].startswith("multipart/form-data; boundary=")
    raw = req.content
    assert raw.index(b'name="files[]"; filename="foto-1.jpg"') < raw.index(
        b'name="files[]"; filename="foto-2.png"'
    )
    assert b"Content-Type: image/jpeg" in raw and b"\xff\xd8one" in raw
    assert b'name="note"' in raw and b"hola" in raw


def test_plaintext_bases_are_still_refused() -> None:
    with pytest.raises(ValueError):
        BaseHTTPConnectorClient(base_url="http://api.example.test")
