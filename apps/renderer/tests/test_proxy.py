"""The in-process forward proxy Chromium is forced through (D50).

Real sockets on loopback, no browser and no network: the resolver is a table
and the connector maps the vetted public IP to a local test server, recording
every address it is asked to dial. That record is the point — a refused
request must never reach the connector, and an accepted one must reach it
with the IP that was vetted, never with a name that could resolve again
(DNS rebinding).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest

from nexus_renderer.egress import EgressGuard
from nexus_renderer.proxy import REFUSED_HEADER, ForwardProxy

PUBLIC_IP = "93.184.215.14"

Streams = tuple[asyncio.StreamReader, asyncio.StreamWriter]


class Upstream:
    """A loopback server standing in for the public site."""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.heads: list[bytes] = []
        self.server: asyncio.Server | None = None

    async def __aenter__(self) -> Upstream:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self

    async def __aexit__(self, *_exc: object) -> None:
        assert self.server is not None
        self.server.close()
        await self.server.wait_closed()

    @property
    def port(self) -> int:
        assert self.server is not None
        return int(self.server.sockets[0].getsockname()[1])

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            if self.mode == "echo":
                while chunk := await reader.read(1024):
                    writer.write(chunk)
                    await writer.drain()
                return
            head = await reader.readuntil(b"\r\n\r\n")
            self.heads.append(head)
            writer.write(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/plain\r\n"
                b"Content-Length: 5\r\n"
                b"Connection: keep-alive\r\n"
                b"Keep-Alive: timeout=5\r\n"
                b"\r\n"
                b"hello"
            )
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()


def table_resolver(
    table: dict[str, list[str]], calls: list[str]
) -> Callable[[str], Awaitable[list[str]]]:
    async def resolve(host: str) -> list[str]:
        calls.append(host)
        if host not in table:
            raise OSError("unknown host")
        return table[host]

    return resolve


TABLE = {
    "shop.example": [PUBLIC_IP],
    "localhost": ["127.0.0.1", "::1"],
    "internal.example": ["10.0.3.7"],
    "metadata.example": ["169.254.169.254"],
}


@pytest.fixture
async def http_upstream() -> AsyncIterator[Upstream]:
    async with Upstream("http") as upstream:
        yield upstream


@pytest.fixture
async def echo_upstream() -> AsyncIterator[Upstream]:
    async with Upstream("echo") as upstream:
        yield upstream


class Dialled(list[tuple[str, int]]):
    pass


def connector_to(upstream: Upstream, dialled: Dialled) -> Callable[[str, int], Awaitable[Streams]]:
    async def connect(ip: str, port: int) -> Streams:
        dialled.append((ip, port))
        if ip != PUBLIC_IP:
            raise AssertionError(f"the proxy dialled {ip!r}, which was never vetted")
        return await asyncio.open_connection("127.0.0.1", upstream.port)

    return connect


async def start_proxy(
    upstream: Upstream,
    dialled: Dialled,
    *,
    resolve: Callable[[str], Awaitable[list[str]]] | None = None,
    **kwargs: float | int,
) -> ForwardProxy:
    calls: list[str] = []
    guard = EgressGuard(resolve or table_resolver(TABLE, calls))
    proxy = ForwardProxy(guard, connect=connector_to(upstream, dialled), **kwargs)  # type: ignore[arg-type]
    await proxy.start()
    return proxy


async def exchange(proxy: ForwardProxy, raw: bytes, *, then: bytes = b"") -> bytes:
    host, port = proxy.address
    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write(raw)
        await writer.drain()
        if then:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            writer.write(then)
            await writer.drain()
            body = await asyncio.wait_for(reader.read(len(then)), 5)
            return head + body
        return await asyncio.wait_for(reader.read(), 5)
    finally:
        writer.close()


async def test_listens_on_loopback_only(http_upstream: Upstream) -> None:
    proxy = await start_proxy(http_upstream, Dialled())
    try:
        assert proxy.url.startswith("http://127.0.0.1:")
        assert proxy.address[0] == "127.0.0.1"
    finally:
        await proxy.close()


async def test_plain_http_is_forwarded_in_origin_form(http_upstream: Upstream) -> None:
    dialled = Dialled()
    proxy = await start_proxy(http_upstream, dialled)
    try:
        response = await exchange(
            proxy,
            b"GET http://shop.example/hello?x=1 HTTP/1.1\r\n"
            b"Host: shop.example\r\n"
            b"Proxy-Connection: keep-alive\r\n"
            b"Proxy-Authorization: Basic c2VjcmV0\r\n"
            b"User-Agent: NexusReader/1.0\r\n"
            b"\r\n",
        )
    finally:
        await proxy.close()

    assert dialled == [(PUBLIC_IP, 80)]
    [head] = http_upstream.heads
    lines = head.decode("latin-1").split("\r\n")
    assert lines[0] == "GET /hello?x=1 HTTP/1.1"
    lowered = [line.lower() for line in lines]
    assert "host: shop.example" in lowered
    assert "connection: close" in lowered
    assert "user-agent: nexusreader/1.0" in lowered
    assert not any(line.startswith("proxy-") for line in lowered)

    assert response.startswith(b"HTTP/1.1 200 OK\r\n")
    assert response.endswith(b"hello")
    response_head = response.split(b"\r\n\r\n", 1)[0].decode("latin-1").lower()
    assert "connection: close" in response_head
    assert "keep-alive" not in response_head


async def test_connect_tunnels_to_the_vetted_ip(echo_upstream: Upstream) -> None:
    dialled = Dialled()
    proxy = await start_proxy(echo_upstream, dialled)
    try:
        response = await exchange(
            proxy,
            b"CONNECT shop.example:443 HTTP/1.1\r\nHost: shop.example:443\r\n\r\n",
            then=b"\x16\x03\x01tls-bytes",
        )
    finally:
        await proxy.close()

    assert response.startswith(b"HTTP/1.1 200 ")
    assert response.endswith(b"\x16\x03\x01tls-bytes")
    assert dialled == [(PUBLIC_IP, 443)]


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (b"GET http://127.0.0.1/ HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n", b"address"),
        (b"GET http://[::1]/ HTTP/1.1\r\nHost: [::1]\r\n\r\n", b"address"),
        (b"GET http://localhost/ HTTP/1.1\r\nHost: localhost\r\n\r\n", b"address"),
        (
            b"GET http://169.254.169.254/latest/meta-data/ HTTP/1.1\r\nHost: 169.254.169.254\r\n\r\n",
            b"address",
        ),
        (
            b"GET http://169.254.170.2/v2/credentials HTTP/1.1\r\nHost: 169.254.170.2\r\n\r\n",
            b"address",
        ),
        (b"GET http://metadata.example/ HTTP/1.1\r\nHost: metadata.example\r\n\r\n", b"address"),
        (b"GET http://[::ffff:127.0.0.1]/ HTTP/1.1\r\nHost: x\r\n\r\n", b"address"),
        (b"CONNECT 10.0.0.1:443 HTTP/1.1\r\nHost: 10.0.0.1:443\r\n\r\n", b"address"),
        (b"CONNECT internal.example:443 HTTP/1.1\r\nHost: internal.example\r\n\r\n", b"address"),
        (b"CONNECT [fd00:ec2::254]:443 HTTP/1.1\r\nHost: x\r\n\r\n", b"address"),
        (b"GET http://shop.example:8080/ HTTP/1.1\r\nHost: shop.example:8080\r\n\r\n", b"port"),
        (b"CONNECT shop.example:22 HTTP/1.1\r\nHost: shop.example:22\r\n\r\n", b"port"),
        (b"CONNECT shop.example:6379 HTTP/1.1\r\nHost: shop.example:6379\r\n\r\n", b"port"),
        (b"CONNECT nowhere.example:443 HTTP/1.1\r\nHost: nowhere.example\r\n\r\n", b"unresolvable"),
    ],
)
async def test_refused_targets_never_reach_the_connector(
    http_upstream: Upstream, raw: bytes, reason: bytes
) -> None:
    dialled = Dialled()
    proxy = await start_proxy(http_upstream, dialled)
    try:
        response = await exchange(proxy, raw)
    finally:
        await proxy.close()

    assert response.startswith(b"HTTP/1.1 403 ")
    assert f"{REFUSED_HEADER}: ".encode() + reason in response
    assert dialled == []
    assert http_upstream.heads == []


async def test_rebinding_cannot_swap_the_address(http_upstream: Upstream) -> None:
    """The name is resolved ONCE per connection, by the proxy, and the
    connector receives the vetted IP. A resolver that answers public first and
    loopback afterwards (the rebinding trick) gets the second request refused,
    and the first one was already pinned to the public IP."""
    answers = iter([[PUBLIC_IP], ["127.0.0.1"]])
    calls: list[str] = []

    async def rebinding(host: str) -> list[str]:
        calls.append(host)
        return next(answers)

    dialled = Dialled()
    proxy = await start_proxy(http_upstream, dialled, resolve=rebinding)
    request = b"GET http://rebind.example/ HTTP/1.1\r\nHost: rebind.example\r\n\r\n"
    try:
        first = await exchange(proxy, request)
        second = await exchange(proxy, request)
    finally:
        await proxy.close()

    assert first.startswith(b"HTTP/1.1 200 ")
    assert second.startswith(b"HTTP/1.1 403 ")
    assert calls == ["rebind.example", "rebind.example"]  # once per connection
    assert dialled == [(PUBLIC_IP, 80)]  # an IP, never the name


@pytest.mark.parametrize(
    "raw",
    [
        b"GET / HTTP/1.1\r\nHost: shop.example\r\n\r\n",  # origin-form: not a proxy request
        b"GET https://shop.example/ HTTP/1.1\r\nHost: shop.example\r\n\r\n",  # https must CONNECT
        b"GET ftp://shop.example/ HTTP/1.1\r\nHost: shop.example\r\n\r\n",
        b"GET file:///etc/passwd HTTP/1.1\r\nHost: x\r\n\r\n",
        b"GET http://user:pw@shop.example/ HTTP/1.1\r\nHost: shop.example\r\n\r\n",
        b"GET http://shop.example:http/ HTTP/1.1\r\nHost: shop.example\r\n\r\n",
        b"CONNECT shop.example HTTP/1.1\r\nHost: shop.example\r\n\r\n",
        b"CONNECT shop.example:abc HTTP/1.1\r\nHost: shop.example\r\n\r\n",
        b"HELLO\r\n\r\n",
        b"GET http://shop.example/ SPDY/3\r\n\r\n",
    ],
)
async def test_malformed_requests_get_400(http_upstream: Upstream, raw: bytes) -> None:
    dialled = Dialled()
    proxy = await start_proxy(http_upstream, dialled)
    try:
        response = await exchange(proxy, raw)
    finally:
        await proxy.close()
    assert response.startswith(b"HTTP/1.1 400 ")
    assert dialled == []


async def test_oversized_head_gets_431(http_upstream: Upstream) -> None:
    dialled = Dialled()
    proxy = await start_proxy(http_upstream, dialled, max_head_bytes=1024)
    try:
        response = await exchange(
            proxy,
            b"GET http://shop.example/ HTTP/1.1\r\nX-Pad: " + b"a" * 4096 + b"\r\n\r\n",
        )
    finally:
        await proxy.close()
    assert response.startswith(b"HTTP/1.1 431 ")
    assert dialled == []


async def test_unreachable_upstream_gets_502(http_upstream: Upstream) -> None:
    async def failing(_ip: str, _port: int) -> Streams:
        raise OSError("connection refused")

    proxy = ForwardProxy(
        EgressGuard(table_resolver(TABLE, [])),
        connect=failing,
    )
    await proxy.start()
    try:
        response = await exchange(proxy, b"CONNECT shop.example:443 HTTP/1.1\r\n\r\n")
    finally:
        await proxy.close()
    assert response.startswith(b"HTTP/1.1 502 ")


async def test_connection_cap_answers_503(echo_upstream: Upstream) -> None:
    dialled = Dialled()
    proxy = await start_proxy(echo_upstream, dialled, max_connections=1)
    host, port = proxy.address
    try:
        reader, writer = await asyncio.open_connection(host, port)
        writer.write(b"CONNECT shop.example:443 HTTP/1.1\r\n\r\n")
        await writer.drain()
        await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)  # tunnel held open
        second = await exchange(proxy, b"CONNECT shop.example:443 HTTP/1.1\r\n\r\n")
        writer.close()
    finally:
        await proxy.close()
    assert second.startswith(b"HTTP/1.1 503 ")
    assert dialled == [(PUBLIC_IP, 443)]
