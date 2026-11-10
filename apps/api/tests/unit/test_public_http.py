"""Spec 047, T217 (revisión de seguridad del 2026-10-30) — el rebinding de DNS en
el lector.

Antes, ``assert_public_url`` resolvía el nombre, lo daba por bueno y después
``httpx`` lo volvía a resolver para conectar: un DNS que contesta una dirección
pública la primera vez y una privada la segunda pasaba la guarda y llegaba a la
red interna. Lo que se fija aquí:

- el transporte resuelve **una vez**, valida **todas** las direcciones con la tabla
  de ``core/public_addresses.py`` (la del renderer) y conecta a la validada,
  manteniendo el ``Host`` y el SNI del nombre;
- solo los puertos 80 y 443;
- NAT64 (``64:ff9b::/96``) y la multidifusión IPv4, que ``is_global`` acepta, se
  rechazan también en la guarda;
- los clientes que leen webs de terceros (el lector del worker y ``fetch_url``)
  usan ese transporte;
- las dos copias de la tabla, la de la API y la del renderer, coinciden.
"""

from __future__ import annotations

import asyncio
import importlib.util
import ipaddress
import ssl
from pathlib import Path
from types import ModuleType
from typing import Any

import httpcore
import httpx
import pytest

from nexus_api.core import public_addresses
from nexus_api.core.public_http import (
    PublicNetworkBackend,
    PublicTransport,
    UnsafeAddress,
    public_client,
)
from nexus_api.services.business.reader import ReadFailure, guarded_get
from nexus_api.services.knowledge_indexer import IndexingError, assert_public_url, fetch_url

PUBLIC = "93.184.215.14"


# ── un DNS falso que cambia de respuesta, y una red que no sale ──────────────


class FlippingDNS:
    """Contesta ``answers`` en orden, una por pregunta, y repite la última."""

    def __init__(self, *answers: list[str]) -> None:
        self.answers = list(answers)
        self.asked: list[str] = []

    async def __call__(self, host: str, port: int) -> list[str]:
        self.asked.append(host)
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


class FakeStream(httpcore.AsyncNetworkStream):
    """Una conexión que anota lo que se le escribe y el SNI, y contesta 200."""

    def __init__(self, seen: dict[str, Any]) -> None:
        self.seen = seen
        self.reply = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nok"

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        out, self.reply = self.reply, b""
        return out

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self.seen.setdefault("written", b"")
        self.seen["written"] += buffer

    async def aclose(self) -> None:
        return None

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.AsyncNetworkStream:
        self.seen["sni"] = server_hostname
        return self

    def get_extra_info(self, info: str) -> Any:
        return None


class FakeNetwork(httpcore.AsyncNetworkBackend):
    """La red de debajo: anota a qué dirección y puerto se conecta."""

    def __init__(self) -> None:
        self.connected: list[tuple[str, int]] = []
        self.seen: dict[str, Any] = {}

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        self.connected.append((host, port))
        return FakeStream(self.seen)

    async def connect_unix_socket(
        self, path: str, timeout: float | None = None, socket_options: Any = None
    ) -> httpcore.AsyncNetworkStream:  # pragma: no cover - never reached
        raise AssertionError("no unix sockets")

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


def _client(dns: FlippingDNS, net: FakeNetwork) -> httpx.AsyncClient:
    return public_client(backend=PublicNetworkBackend(resolve=dns, inner=net))


async def _allow(_url: str) -> None:
    return None


# ── el transporte: una resolución, todas validadas, la validada ─────────────


async def test_it_connects_to_the_address_it_checked_keeping_host_and_sni() -> None:
    dns, net = FlippingDNS([PUBLIC]), FakeNetwork()
    async with _client(dns, net) as http:
        got = await guarded_get(http, "https://shop.example/precios", guard=_allow)
    assert got.status == 200 and got.data == b"ok"
    assert dns.asked == ["shop.example"], "una sola resolución"
    assert net.connected == [(PUBLIC, 443)], "a la dirección validada, no al nombre"
    assert net.seen["sni"] == "shop.example", "el SNI es el del nombre"
    assert b"Host: shop.example\r\n" in net.seen["written"]


async def test_a_rebinding_dns_never_reaches_the_private_address() -> None:
    """La guarda ve una pública; el transporte, al resolver, una privada: no conecta."""
    dns, net = FlippingDNS([PUBLIC], ["127.0.0.1"]), FakeNetwork()

    async def guard(url: str) -> None:  # lo que hacía assert_public_url: resolver aparte
        await dns(httpx.URL(url).host, 443)

    async with _client(dns, net) as http:
        with pytest.raises(ReadFailure) as failure:
            await guarded_get(http, "https://rebind.example/", guard=guard)
    assert failure.value.code == "unreachable"
    assert net.connected == []


async def test_every_connection_checks_its_own_answer() -> None:
    dns, net = FlippingDNS([PUBLIC], ["169.254.169.254"]), FakeNetwork()
    limits = httpx.Limits(max_keepalive_connections=0)
    async with public_client(
        backend=PublicNetworkBackend(resolve=dns, inner=net), limits=limits
    ) as http:
        assert (await http.get("http://rebind.example/a")).status_code == 200
        with pytest.raises(httpx.ConnectError):
            await http.get("http://rebind.example/b")
    assert net.connected == [(PUBLIC, 80)]


@pytest.mark.parametrize(
    "answer",
    [
        [PUBLIC, "10.0.0.7"],  # una pública y una privada: ninguna
        ["64:ff9b::a9fe:a9fe"],  # NAT64 de 169.254.169.254
        ["::ffff:127.0.0.1"],
        ["224.0.0.1"],  # multidifusión IPv4
        ["fd00:ec2::254"],
        [],
    ],
)
async def test_one_bad_address_refuses_them_all(answer: list[str]) -> None:
    dns, net = FlippingDNS(answer), FakeNetwork()
    async with _client(dns, net) as http:
        with pytest.raises(httpx.ConnectError) as error:
            await http.get("https://mixed.example/")
    assert isinstance(error.value.__context__ or error.value.__cause__, UnsafeAddress) or (
        "refused" in str(error.value)
    )
    assert net.connected == []


@pytest.mark.parametrize("url", ["http://shop.example:8080/", "https://shop.example:22/"])
async def test_only_ports_80_and_443(url: str) -> None:
    dns, net = FlippingDNS([PUBLIC]), FakeNetwork()
    async with _client(dns, net) as http:
        with pytest.raises(httpx.ConnectError):
            await http.get(url)
    assert net.connected == []


async def test_a_literal_address_is_checked_without_asking_the_dns() -> None:
    dns, net = FlippingDNS([PUBLIC]), FakeNetwork()
    async with _client(dns, net) as http:
        assert (await http.get(f"http://{PUBLIC}/")).status_code == 200
        with pytest.raises(httpx.ConnectError):
            await http.get("http://[::1]/")
    assert dns.asked == [] and net.connected == [(PUBLIC, 80)]


def test_the_client_ignores_proxies_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un ``HTTPS_PROXY`` del entorno montaría otro transporte que no valida nada."""
    monkeypatch.setenv("HTTPS_PROXY", "http://10.0.0.1:3128")
    monkeypatch.setenv("HTTP_PROXY", "http://10.0.0.1:3128")
    client = public_client()
    assert isinstance(client._transport, PublicTransport)
    assert not client._mounts, client._mounts
    assert isinstance(client._transport._pool._network_backend, PublicNetworkBackend)


# ── la guarda, con la misma tabla y los mismos puertos ─────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "http://[64:ff9b::a9fe:a9fe]/",
        "http://224.0.0.251/",
        "http://[ff02::1]/",
        "http://shop.example:8080/",
        "ftp://shop.example/",
    ],
)
async def test_the_guard_refuses_what_is_global_but_not_public(url: str) -> None:
    with pytest.raises(IndexingError):
        await assert_public_url(url)


async def test_the_worker_reader_and_fetch_url_use_the_pinned_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nexus_worker.jobs.handlers import client_read

    http = client_read.default_http()
    try:
        assert isinstance(http._transport, PublicTransport)
        assert not http._mounts
    finally:
        await http.aclose()

    made: list[httpx.AsyncClient] = []
    real = public_client

    def spy(**kwargs: Any) -> httpx.AsyncClient:
        made.append(real(**kwargs))
        return made[-1]

    from nexus_api.services import knowledge_indexer

    monkeypatch.setattr(knowledge_indexer, "public_client", spy)
    with pytest.raises(IndexingError):
        await fetch_url("http://localhost./")
    assert made and isinstance(made[0]._transport, PublicTransport)


# ── las dos copias de la tabla ──────────────────────────────────────────────

_RENDERER = Path(__file__).resolve().parents[3] / "renderer/src/nexus_renderer/addresses.py"


def _renderer_addresses() -> ModuleType:
    spec = importlib.util.spec_from_file_location("renderer_addresses_copy", _RENDERER)
    assert spec is not None and spec.loader is not None, _RENDERER
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_api_and_the_renderer_tables_are_the_same() -> None:
    """``apps/renderer`` tiene su propio entorno y su propio lock: no depende de la
    API. La tabla está copiada, y esta prueba es lo que las mantiene iguales."""
    renderer = _renderer_addresses()
    assert renderer._BLOCKED_V4 == public_addresses._BLOCKED_V4
    assert renderer._BLOCKED_V6 == public_addresses._BLOCKED_V6
    assert renderer.ALLOWED_PORTS == public_addresses.ALLOWED_PORTS == frozenset({80, 443})
    samples = [
        *(str(net[0]) for net in public_addresses._BLOCKED_V4),
        *(str(net[-1]) for net in public_addresses._BLOCKED_V4),
        *(str(net[0]) for net in public_addresses._BLOCKED_V6),
        PUBLIC,
        "8.8.8.8",
        "2606:4700::1111",
        "::ffff:8.8.8.8",
    ]
    for literal in samples:
        addr = ipaddress.ip_address(literal)
        assert renderer.is_public_address(addr) == public_addresses.is_public_address(addr), literal
        assert renderer.parse_ip(f"[{literal}]") == public_addresses.parse_ip(f"[{literal}]")
