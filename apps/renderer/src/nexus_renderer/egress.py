"""Resolve a host once, vet every answer, and hand back only vetted IPs.

The proxy dials what this returns — an IP, never the name — so a DNS answer
that changes between the check and the connection (rebinding) has nothing to
change: there is no second lookup.
"""

from __future__ import annotations

import asyncio
import re
import socket
from collections.abc import Awaitable, Callable
from typing import Final

from nexus_renderer.addresses import ALLOWED_PORTS, IPAddress, is_public_address, parse_ip

Resolver = Callable[[str], Awaitable[list[str]]]

#: The reasons a target is refused; the proxy puts them in its 403.
REASONS: Final = ("port", "address", "unresolvable", "bad_host")

_MAX_HOST_CHARS: Final = 253
_HOST_CHARS: Final = re.compile(r"^[A-Za-z0-9.\-_:\[\]%]+$")


class Refused(Exception):
    """The target is not on the public web (or not on a web port)."""

    def __init__(self, reason: str) -> None:
        if reason not in REASONS:
            raise ValueError(f"unknown refusal reason: {reason!r}")
        super().__init__(reason)
        self.reason = reason


async def system_resolve(host: str) -> list[str]:
    """Every address the system resolver gives for ``host``."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


class EgressGuard:
    def __init__(self, resolver: Resolver = system_resolve, *, resolve_timeout_s: float = 5.0):
        self._resolve = resolver
        self._resolve_timeout_s = resolve_timeout_s

    async def vet(self, host: str, port: int) -> list[IPAddress]:
        """The addresses ``host:port`` may be dialled at, in resolver order.

        Raises :class:`Refused` when the port is not 80/443, the host is
        malformed or does not resolve, or **any** answer is not public — the
        same rule as ``assert_public_url``: a name that answers public and
        private at once is a rebinding set-up, not a site.
        """
        if port not in ALLOWED_PORTS:
            raise Refused("port")
        name = host.strip()
        if not name or len(name) > _MAX_HOST_CHARS or not _HOST_CHARS.match(name):
            raise Refused("bad_host")

        literal = parse_ip(name)
        if literal is not None:
            candidates: list[IPAddress] = [literal]
        else:
            try:
                async with asyncio.timeout(self._resolve_timeout_s):
                    answers = await self._resolve(name)
            except (OSError, TimeoutError, UnicodeError) as exc:
                raise Refused("unresolvable") from exc
            candidates = []
            for answer in answers:
                parsed = parse_ip(answer)
                if parsed is None:
                    raise Refused("unresolvable")
                candidates.append(parsed)
        if not candidates:
            raise Refused("unresolvable")
        if not all(is_public_address(addr) for addr in candidates):
            raise Refused("address")
        return list(dict.fromkeys(candidates))


__all__ = ["REASONS", "EgressGuard", "Refused", "Resolver", "system_resolve"]
