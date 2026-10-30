"""El cliente del navegador de respaldo — spec 047, T203 (requisito 59.2, D50).

Lo que se fija aquí: sin ``NEXUS_RENDERER_URL`` no hace nada; con ella, pide la
página con su token y devuelve ``Rendered`` solo si la respuesta es sana; ante
cualquier fallo del servicio devuelve ``None`` y no lanza. Y una tabla de
direcciones: el proxy del renderer (``apps/renderer``) nunca acepta una que
``assert_public_url`` rechaza.
"""

from __future__ import annotations

import asyncio
import importlib.util
import ipaddress
import json
from pathlib import Path
from types import ModuleType

import httpx
import pytest
import respx
from pydantic import SecretStr

from nexus_api.db.models import KnowledgeErrorCode
from nexus_api.services.business import renderer_client
from nexus_api.services.business.renderer_client import (
    MAX_HTML_BYTES,
    Rendered,
    RendererSettings,
    render,
)
from nexus_api.services.knowledge_indexer import IndexingError, assert_public_url

BASE = "http://renderer.nexus-staging.internal:8080"
TOKEN = "r" * 48
PAGE = "https://shop.example/"


def settings(**overrides: object) -> RendererSettings:
    values: dict[str, object] = {"url": BASE, "token": SecretStr(TOKEN), "timeout_s": 5.0}
    values.update(overrides)
    return RendererSettings.model_construct(**values)


async def allow(_url: str) -> None:
    return None


def ok_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "final_url": "https://shop.example/es/",
        "status": 200,
        "html": "<html><body><p>Corte 15 €</p></body></html>",
    }
    body.update(overrides)
    return body


# ── apagado ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("url", ["", "   "])
async def test_off_without_url_makes_no_call(url: str) -> None:
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(f"{BASE}/render")
        assert await render(PAGE, settings=settings(url=url), guard=allow) is None
    assert not route.called


async def test_without_token_makes_no_call() -> None:
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(f"{BASE}/render")
        assert await render(PAGE, settings=settings(token=SecretStr("")), guard=allow) is None
    assert not route.called


def test_settings_read_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_RENDERER_URL", BASE)
    monkeypatch.setenv("NEXUS_RENDERER_TOKEN", TOKEN)
    cfg = RendererSettings(_env_file=None)
    assert cfg.enabled
    assert cfg.url == BASE
    assert cfg.token.get_secret_value() == TOKEN
    assert TOKEN not in repr(cfg)


def test_settings_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXUS_RENDERER_URL", raising=False)
    monkeypatch.delenv("NEXUS_RENDERER_TOKEN", raising=False)
    assert RendererSettings(_env_file=None).enabled is False


# ── una página ───────────────────────────────────────────────────────────────


async def test_renders_with_the_token() -> None:
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/render").respond(200, json=ok_body())
        result = await render(PAGE, settings=settings(url=BASE + "/"), guard=allow)

    assert result == Rendered(
        final_url="https://shop.example/es/",
        status=200,
        html="<html><body><p>Corte 15 €</p></body></html>",
    )
    request = route.calls.last.request
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert json.loads(request.content) == {"url": PAGE}


async def test_page_status_is_passed_through() -> None:
    """Un 404 de la web no es un fallo del renderer: lo decide el lector."""
    with respx.mock() as mock:
        mock.post(f"{BASE}/render").respond(200, json=ok_body(status=404))
        result = await render(PAGE, settings=settings(), guard=allow)
    assert result is not None and result.status == 404


# ── nunca lanza ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", [400, 401, 413, 422, 500, 502, 503, 504])
async def test_renderer_errors_are_none(status: int) -> None:
    with respx.mock() as mock:
        mock.post(f"{BASE}/render").respond(status, json={"error": "whatever"})
        assert await render(PAGE, settings=settings(), guard=allow) is None


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("refused"),
        httpx.ReadTimeout("slow"),
        httpx.RemoteProtocolError("garbage"),
        OSError("network down"),
    ],
)
async def test_transport_failures_are_none(error: Exception) -> None:
    with respx.mock() as mock:
        mock.post(f"{BASE}/render").mock(side_effect=error)
        assert await render(PAGE, settings=settings(), guard=allow) is None


async def test_own_timeout_is_enforced() -> None:
    async def slow(_request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(2)
        return httpx.Response(200, json=ok_body())

    # El plazo puede vencer antes de que la petición llegue al transporte.
    with respx.mock(assert_all_called=False) as mock:
        mock.post(f"{BASE}/render").mock(side_effect=slow)
        assert await render(PAGE, settings=settings(timeout_s=0.05), guard=allow) is None


@pytest.mark.parametrize(
    "content",
    [
        b"not json",
        b"[]",
        json.dumps({"final_url": "https://shop.example/", "status": "200", "html": ""}).encode(),
        json.dumps({"final_url": "https://shop.example/", "status": True, "html": ""}).encode(),
        json.dumps({"final_url": "https://shop.example/", "status": 200}).encode(),
        json.dumps({"final_url": 5, "status": 200, "html": ""}).encode(),
        json.dumps({"final_url": "file:///etc/passwd", "status": 200, "html": ""}).encode(),
        json.dumps(
            {"final_url": "chrome-error://chromewebdata/", "status": 0, "html": ""}
        ).encode(),
        json.dumps({"final_url": "https://shop.example/", "status": 9999, "html": ""}).encode(),
    ],
)
async def test_malformed_answers_are_none(content: bytes) -> None:
    with respx.mock() as mock:
        mock.post(f"{BASE}/render").respond(200, content=content)
        assert await render(PAGE, settings=settings(), guard=allow) is None


async def test_html_over_two_megabytes_is_none() -> None:
    html = "a" * (MAX_HTML_BYTES + 1)
    with respx.mock() as mock:
        mock.post(f"{BASE}/render").respond(200, json=ok_body(html=html))
        assert await render(PAGE, settings=settings(), guard=allow) is None


async def test_response_is_cut_while_it_arrives() -> None:
    with respx.mock() as mock:
        mock.post(f"{BASE}/render").respond(
            200, content=b"x" * (renderer_client.MAX_RESPONSE_BYTES + 1)
        )
        assert await render(PAGE, settings=settings(), guard=allow) is None


async def test_unexpected_bug_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_raw: bytes) -> Rendered:
        raise RuntimeError("bug")

    monkeypatch.setattr(renderer_client, "_parse", boom)
    with respx.mock() as mock:
        mock.post(f"{BASE}/render").respond(200, json=ok_body())
        assert await render(PAGE, settings=settings(), guard=allow) is None


# ── las guardas del lector, también aquí ────────────────────────────────────


async def test_non_public_target_is_not_sent() -> None:
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(f"{BASE}/render")
        result = await render("http://169.254.169.254/latest/meta-data/", settings=settings())
    assert result is None
    assert not route.called


async def test_final_url_goes_through_the_guard_too() -> None:
    seen: list[str] = []

    async def guard(url: str) -> None:
        seen.append(url)
        if "intranet" in url:
            raise IndexingError(KnowledgeErrorCode.FETCH_FAILED)

    with respx.mock() as mock:
        mock.post(f"{BASE}/render").respond(
            200, json=ok_body(final_url="http://intranet.example/admin")
        )
        assert await render(PAGE, settings=settings(), guard=guard) is None
    assert seen == [PAGE, "http://intranet.example/admin"]


# ── la misma regla de direcciones en el proxy del renderer ──────────────────
#
# ``apps/renderer`` no depende de ``nexus_api`` (su imagen no la lleva), así
# que su tabla está escrita aparte. Aquí se carga por ruta —es solo biblioteca
# estándar— y se compara con ``assert_public_url`` dirección a dirección.

_ADDRESSES = Path(__file__).resolve().parents[3] / "renderer/src/nexus_renderer/addresses.py"

BOTH_ACCEPT = ["8.8.8.8", "1.1.1.1", "93.184.215.14", "2606:4700::1111", "2001:4860:4860::8888"]
BOTH_REFUSE = [
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "::",
    "10.0.0.1",
    "172.16.0.1",
    "192.168.1.1",
    "169.254.169.254",
    "169.254.170.2",
    "100.64.0.1",
    "fe80::1",
    "fd00:ec2::254",
    "fc00::1",
    "240.0.0.1",
    "255.255.255.255",
    "192.0.2.1",
    "198.18.0.1",
    "2001:db8::1",
    "::ffff:127.0.0.1",
    "::ffff:169.254.169.254",
]
#: Donde la tabla es más estricta que ``is_global`` (multidifusión, IPv4 dentro de
#: IPv6, NAT64, site-local obsoleto). Desde la T217 (revisión de seguridad del
#: 2026-10-30) la API usa la misma tabla (``core/public_addresses.py``) y también
#: las rechaza; que las dos copias coincidan lo fija ``test_public_http.py``.
RENDERER_STRICTER = [
    "224.0.0.1",
    "ff02::1",
    "::ffff:8.8.8.8",
    "64:ff9b::a9fe:a9fe",
    "fec0::1",
    "192.0.0.9",
    "192.88.99.1",
]


def _load_renderer_addresses() -> ModuleType:
    spec = importlib.util.spec_from_file_location("renderer_addresses", _ADDRESSES)
    assert spec is not None and spec.loader is not None, _ADDRESSES
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _api_accepts(literal: str) -> bool:
    host = f"[{literal}]" if ":" in literal else literal
    try:
        await assert_public_url(f"http://{host}/")
    except IndexingError:
        return False
    return True


def _renderer_accepts(module: ModuleType, literal: str) -> bool:
    return bool(module.is_public_address(ipaddress.ip_address(literal)))


async def test_renderer_and_api_agree_on_the_address_table() -> None:
    addresses = _load_renderer_addresses()
    for literal in BOTH_ACCEPT:
        assert await _api_accepts(literal), literal
        assert _renderer_accepts(addresses, literal), literal
    for literal in BOTH_REFUSE:
        assert not await _api_accepts(literal), literal
        assert not _renderer_accepts(addresses, literal), literal
    for literal in RENDERER_STRICTER:
        assert not _renderer_accepts(addresses, literal), literal
        assert not await _api_accepts(literal), literal


async def test_renderer_never_accepts_what_the_api_refuses() -> None:
    addresses = _load_renderer_addresses()
    for literal in BOTH_ACCEPT + BOTH_REFUSE + RENDERER_STRICTER:
        if not await _api_accepts(literal):
            assert not _renderer_accepts(addresses, literal), literal
