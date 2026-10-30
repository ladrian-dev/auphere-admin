"""The forward proxy Chromium is launched behind — every byte leaves through here.

Chromium starts with ``--proxy-server`` pointing at this listener on
127.0.0.1 and with ``--proxy-bypass-list=<-loopback>``, so the navigation, every
redirect, every subresource, XHR/fetch and WebSocket comes here first,
loopback and link-local included. For each connection the proxy:

1. reads the request head (``CONNECT host:port`` for TLS and WebSockets, an
   absolute-form ``GET http://…`` for plain HTTP);
2. asks :class:`~nexus_renderer.egress.EgressGuard` — port 80/443 only, the
   name resolved **here**, every answer public;
3. dials the **vetted IP** itself. Chromium never resolves the target, and the
   proxy never resolves it twice, so DNS rebinding has no second lookup to win.

A refusal is a ``403`` with the :data:`REFUSED_HEADER` marker (the renderer
recognises it on the main document); nothing is dialled.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Final
from urllib.parse import urlsplit

from nexus_renderer.egress import EgressGuard, Refused

log = logging.getLogger(__name__)

Streams = tuple[asyncio.StreamReader, asyncio.StreamWriter]
Connector = Callable[[str, int], Awaitable[Streams]]

#: Header on every refusal; its value is the reason (``port``, ``address``…).
REFUSED_HEADER: Final = "X-Nexus-Renderer-Refused"

_HOP_BY_HOP: Final = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "upgrade",
    }
)
_VERSIONS: Final = frozenset({"HTTP/1.0", "HTTP/1.1"})
_CHUNK: Final = 64 * 1024


async def open_tcp(ip: str, port: int) -> Streams:
    """Dial an already-vetted IP."""
    return await asyncio.open_connection(ip, port)


class _BadRequest(Exception):
    pass


class ForwardProxy:
    def __init__(
        self,
        guard: EgressGuard,
        *,
        connect: Connector = open_tcp,
        host: str = "127.0.0.1",
        port: int = 0,
        connect_timeout_s: float = 10.0,
        head_timeout_s: float = 10.0,
        idle_timeout_s: float = 30.0,
        max_head_bytes: int = 64 * 1024,
        max_connections: int = 256,
    ) -> None:
        self._guard = guard
        self._connect = connect
        self._host = host
        self._port = port
        self._connect_timeout_s = connect_timeout_s
        self._head_timeout_s = head_timeout_s
        self._idle_timeout_s = idle_timeout_s
        self._max_head_bytes = max_head_bytes
        self._max_connections = max_connections
        self._active = 0
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle, self._host, self._port, limit=self._max_head_bytes
        )

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._server.wait_closed(), 5)
            self._server = None

    @property
    def address(self) -> tuple[str, int]:
        if self._server is None:
            raise RuntimeError("proxy not started")
        sockname = self._server.sockets[0].getsockname()
        return str(sockname[0]), int(sockname[1])

    @property
    def url(self) -> str:
        host, port = self.address
        return f"http://{host}:{port}"

    # ── one client connection ──────────────────────────────────────────────

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self._active >= self._max_connections:
            await _reply(writer, 503, "Service Unavailable")
            await _discard(reader)
            await _close(writer)
            return
        self._active += 1
        try:
            await self._serve(reader, writer)
        except Exception:  # never let one connection take the listener down
            log.exception("proxy.connection_failed")
        finally:
            self._active -= 1
            await _close(writer)

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            async with asyncio.timeout(self._head_timeout_s):
                head = await reader.readuntil(b"\r\n\r\n")
        except asyncio.LimitOverrunError:
            await _reply(writer, 431, "Request Header Fields Too Large")
            await _discard(reader)
            return
        except (asyncio.IncompleteReadError, TimeoutError, ConnectionError):
            return

        try:
            method, target, version, headers = _parse_head(head)
            if method == "CONNECT":
                host, port = _parse_authority(target)
                upstream_head = b""
            else:
                host, port, upstream_head = _origin_form(method, target, version, headers)
        except _BadRequest:
            await _reply(writer, 400, "Bad Request")
            return

        try:
            vetted = await self._guard.vet(host, port)
        except Refused as exc:
            log.info("proxy.refused reason=%s port=%s", exc.reason, port)
            await _reply(writer, 403, "Forbidden", refused=exc.reason)
            return

        upstream = await self._dial([str(ip) for ip in vetted], port)
        if upstream is None:
            await _reply(writer, 502, "Bad Gateway")
            return
        up_reader, up_writer = upstream
        try:
            if method == "CONNECT":
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
                await self._relay(reader, writer, up_reader, up_writer, rewrite_response=False)
            else:
                up_writer.write(upstream_head)
                await up_writer.drain()
                await self._relay(reader, writer, up_reader, up_writer, rewrite_response=True)
        finally:
            await _close(up_writer)

    async def _dial(self, ips: list[str], port: int) -> Streams | None:
        for ip in ips:
            try:
                async with asyncio.timeout(self._connect_timeout_s):
                    return await self._connect(ip, port)
            except (OSError, TimeoutError):
                continue
        return None

    async def _relay(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        up_reader: asyncio.StreamReader,
        up_writer: asyncio.StreamWriter,
        *,
        rewrite_response: bool,
    ) -> None:
        downstream: Awaitable[None] = (
            self._pump_response(up_reader, writer)
            if rewrite_response
            else self._pump(up_reader, writer)
        )
        tasks = [
            asyncio.ensure_future(self._pump(reader, up_writer)),
            asyncio.ensure_future(downstream),
        ]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _pump(self, src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
        with contextlib.suppress(ConnectionError, TimeoutError, asyncio.IncompleteReadError):
            while True:
                async with asyncio.timeout(self._idle_timeout_s):
                    chunk = await src.read(_CHUNK)
                if not chunk:
                    return
                dst.write(chunk)
                await dst.drain()

    async def _pump_response(self, src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
        """Plain HTTP: the response head gains ``Connection: close`` so Chromium
        does not reuse this socket for another origin, then the body flows."""
        try:
            async with asyncio.timeout(self._idle_timeout_s):
                head = await src.readuntil(b"\r\n\r\n")
        except (
            asyncio.LimitOverrunError,
            asyncio.IncompleteReadError,
            TimeoutError,
            ConnectionError,
        ):
            return
        lines = head[:-4].split(b"\r\n")
        kept = [lines[0]]
        for line in lines[1:]:
            name = line.split(b":", 1)[0].strip().lower()
            if name in (b"connection", b"keep-alive", b"proxy-connection"):
                continue
            kept.append(line)
        kept += [b"Connection: close", b"Proxy-Connection: close"]
        with contextlib.suppress(ConnectionError):
            dst.write(b"\r\n".join(kept) + b"\r\n\r\n")
            await dst.drain()
        await self._pump(src, dst)


# ── parsing ─────────────────────────────────────────────────────────────


def _parse_head(head: bytes) -> tuple[str, str, str, list[tuple[str, str]]]:
    try:
        text = head.decode("latin-1")
    except UnicodeDecodeError as exc:  # pragma: no cover - latin-1 decodes everything
        raise _BadRequest from exc
    lines = text[:-4].split("\r\n")
    parts = lines[0].split(" ")
    if len(parts) != 3 or parts[2] not in _VERSIONS or not parts[0].isalpha():
        raise _BadRequest
    method, target, version = parts
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        name, sep, value = line.partition(":")
        if not sep or not name or name != name.strip():
            raise _BadRequest
        headers.append((name, value.strip()))
    return method.upper(), target, version, headers


def _parse_authority(target: str) -> tuple[str, int]:
    """``host:port`` / ``[v6]:port`` from a CONNECT line."""
    if target.startswith("["):
        host, sep, rest = target[1:].partition("]")
        if not sep or not rest.startswith(":"):
            raise _BadRequest
        port_text = rest[1:]
    else:
        host, sep, port_text = target.rpartition(":")
        if not sep:
            raise _BadRequest
    if not host or not port_text.isdigit() or len(port_text) > 5:
        raise _BadRequest
    return host, int(port_text)


def _origin_form(
    method: str, target: str, version: str, headers: list[tuple[str, str]]
) -> tuple[str, int, bytes]:
    """Absolute-form ``http://`` request → what the origin server receives."""
    try:
        parts = urlsplit(target)
        port = parts.port or 80
    except ValueError as exc:
        raise _BadRequest from exc
    if parts.scheme != "http" or not parts.hostname or parts.username or parts.password:
        raise _BadRequest
    host = parts.hostname
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    host_header = f"[{host}]" if ":" in host else host
    if parts.port:
        host_header = f"{host_header}:{parts.port}"

    named_in_connection = {
        token.strip().lower()
        for name, value in headers
        if name.lower() == "connection"
        for token in value.split(",")
    }
    lines = [f"{method} {path} {version}", f"Host: {host_header}"]
    for name, value in headers:
        lowered = name.lower()
        if lowered in _HOP_BY_HOP or lowered in named_in_connection or lowered == "host":
            continue
        lines.append(f"{name}: {value}")
    lines.append("Connection: close")
    return host, port, ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")


async def _reply(
    writer: asyncio.StreamWriter, status: int, reason: str, *, refused: str | None = None
) -> None:
    head = [f"HTTP/1.1 {status} {reason}", "Content-Length: 0", "Connection: close"]
    if refused is not None:
        head.append(f"{REFUSED_HEADER}: {refused}")
    with contextlib.suppress(ConnectionError):
        writer.write(("\r\n".join(head) + "\r\n\r\n").encode("latin-1"))
        await writer.drain()


async def _discard(reader: asyncio.StreamReader, *, budget_s: float = 0.5) -> None:
    """Read and drop what the client already sent before closing: closing a
    socket with unread input sends a reset, and the reset can overtake the
    error reply on its way to the client."""
    with contextlib.suppress(Exception):
        async with asyncio.timeout(budget_s):
            for _ in range(16):
                if not await reader.read(_CHUNK):
                    return


async def _close(writer: asyncio.StreamWriter) -> None:
    if writer.is_closing():
        return
    writer.close()
    with contextlib.suppress(Exception):
        await asyncio.wait_for(writer.wait_closed(), 2)


__all__ = ["REFUSED_HEADER", "Connector", "ForwardProxy", "open_tcp"]
