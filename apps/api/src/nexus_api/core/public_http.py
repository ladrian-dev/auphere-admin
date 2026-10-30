"""An HTTP client that only reaches the public internet — spec 047, T217 (security
review of 2026-10-30; requirement 59.2).

The reader (``services/business/reader.py``), the knowledge indexer
(``services/knowledge_indexer.fetch_url``) and the worker's ``client_read`` job
fetch URLs a partner typed. ``assert_public_url`` checks them, but it resolves the
name on its own and then ``httpx`` resolves it again to connect: a DNS answer
that is public the first time and private the second (DNS rebinding) passed the
check and reached the VPC, the cloud metadata endpoint or localhost.

:class:`PublicNetworkBackend` closes that gap where the socket is opened. For
every connection it:

1. refuses any port but 80 and 443 (``public_addresses.ALLOWED_PORTS``);
2. resolves the name **once** (an address literal is not resolved);
3. validates **every** address of the answer with the shared table
   (``public_addresses.is_public_address``) — one bad address refuses them all;
4. connects to an address it validated.

The URL is not rewritten, so the ``Host`` header and the TLS SNI (and the
certificate check) stay those of the name. Redirects are still followed by hand
by the callers, each hop through the same transport.

:func:`public_client` builds the ``httpx.AsyncClient`` with that transport and
``trust_env=False``: a proxy from the environment would mount another transport
that checks nothing. ``tests/unit/test_public_http.py`` pins all of it, with a
DNS that changes its answer.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

import httpcore
import httpx

from nexus_api.core.public_addresses import ALLOWED_PORTS, is_public_address, parse_ip

#: ``(host, port) -> addresses``: the system resolver by default; tests pass a fake.
Resolver = Callable[[str, int], Awaitable[list[str]]]


class UnsafeAddress(httpcore.ConnectError):
    """A connection the transport refused: a port that is not the web's, a name
    with no address, or an answer with any non-public address. ``httpx`` reports
    it as ``httpx.ConnectError``."""


async def system_resolve(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def _checked(addresses: Iterable[str]) -> list[str]:
    """The addresses, deduplicated and in order, if every one is public."""
    out: list[str] = []
    for raw in addresses:
        try:
            addr = ipaddress.ip_address(raw.split("%", 1)[0])
        except ValueError as exc:
            raise UnsafeAddress("refused: not an address") from exc
        if not is_public_address(addr):
            raise UnsafeAddress("refused: not a public address")
        if str(addr) not in out:
            out.append(str(addr))
    if not out:
        raise UnsafeAddress("refused: no address")
    return out


class PublicNetworkBackend(httpcore.AsyncNetworkBackend):
    """Resolve once, validate every address, connect to a validated one."""

    def __init__(
        self,
        *,
        resolve: Resolver | None = None,
        inner: httpcore.AsyncNetworkBackend | None = None,
        ports: frozenset[int] = ALLOWED_PORTS,
    ) -> None:
        self._resolve = resolve or system_resolve
        self._inner = inner or httpcore.AnyIOBackend()
        self._ports = ports

    async def addresses(self, host: str, port: int) -> list[str]:
        """The validated addresses ``host`` may be reached at, or :class:`UnsafeAddress`."""
        if port not in self._ports:
            raise UnsafeAddress("refused: port")
        literal = parse_ip(host)
        if literal is not None:
            return _checked([str(literal)])
        try:
            answer = await self._resolve(host, port)
        except OSError as exc:
            raise httpcore.ConnectError(f"cannot resolve: {type(exc).__name__}") from exc
        return _checked(answer)

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        last: Exception | None = None
        for address in await self.addresses(host, port):
            try:
                return await self._inner.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last = exc
        assert last is not None
        raise last

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise UnsafeAddress("refused: unix socket")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class PublicTransport(httpx.AsyncHTTPTransport):
    """``httpx``'s transport with its connection pool on :class:`PublicNetworkBackend`.

    ``httpx`` does not take a network backend, so the pool it builds is replaced by
    one that has it (``_pool`` is what ``handle_async_request`` uses). The test
    that asserts the backend in place catches an ``httpx`` that renames it."""

    def __init__(
        self,
        *,
        backend: httpcore.AsyncNetworkBackend | None = None,
        limits: httpx.Limits = httpx.Limits(max_connections=100, max_keepalive_connections=20),
    ) -> None:
        super().__init__(trust_env=False, limits=limits)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(),
            max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry,
            network_backend=backend or PublicNetworkBackend(),
        )


def public_client(
    *,
    backend: httpcore.AsyncNetworkBackend | None = None,
    limits: httpx.Limits | None = None,
    **kwargs: Any,
) -> httpx.AsyncClient:
    """An ``httpx.AsyncClient`` that only reaches public addresses on 80 and 443.
    ``kwargs`` go to the client (``timeout``, ``headers``…); redirects stay off,
    so the caller checks every hop."""
    kwargs.setdefault("follow_redirects", False)
    transport = (
        PublicTransport(backend=backend, limits=limits)
        if limits is not None
        else PublicTransport(backend=backend)
    )
    return httpx.AsyncClient(transport=transport, trust_env=False, **kwargs)


__all__ = [
    "PublicNetworkBackend",
    "PublicTransport",
    "Resolver",
    "UnsafeAddress",
    "public_client",
    "system_resolve",
]
