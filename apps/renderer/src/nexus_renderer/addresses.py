"""Which addresses Chromium may reach — spec 047, requirement 59.2, research D50.

The same rule as the reader's ``knowledge_indexer.assert_public_url`` (only
globally routable addresses), written as an explicit table so the verdict does
not depend on the Python patch release: ``ipaddress.is_global`` changed in
3.11.10, 3.12.4 and 3.13, and the base image runs Ubuntu's 3.12. Where the two
differ, this one is stricter (multicast, IPv4 embedded in IPv6, deprecated
site-local); never the other way round.

**Standard library only, on purpose.** The API suite loads this file by path
(``apps/api/tests/unit/test_renderer_client.py``) and checks it never accepts
an address the API refuses, without installing the renderer.
"""

from __future__ import annotations

import ipaddress
from typing import Final

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

#: The only ports a page may open: the web's.
ALLOWED_PORTS: Final = frozenset({80, 443})

# IANA IPv4 Special-Purpose Address Registry, plus multicast and class E.
_BLOCKED_V4: Final = tuple(
    ipaddress.IPv4Network(net)
    for net in (
        "0.0.0.0/8",  # "this network"
        "10.0.0.0/8",  # RFC 1918
        "100.64.0.0/10",  # shared address space / CGNAT (RFC 6598)
        "127.0.0.0/8",  # loopback
        # link-local: 169.254.169.254 (EC2 IMDS), 169.254.170.2 (ECS task
        # metadata and task-role credentials), 169.254.169.253 (VPC DNS)
        "169.254.0.0/16",
        "172.16.0.0/12",  # RFC 1918
        "192.0.0.0/24",  # IETF protocol assignments
        "192.0.2.0/24",  # TEST-NET-1
        "192.31.196.0/24",  # AS112-v4
        "192.52.193.0/24",  # AMT
        "192.88.99.0/24",  # 6to4 relay anycast (deprecated)
        "192.168.0.0/16",  # RFC 1918
        "192.175.48.0/24",  # direct delegation AS112
        "198.18.0.0/15",  # benchmarking
        "198.51.100.0/24",  # TEST-NET-2
        "203.0.113.0/24",  # TEST-NET-3
        "224.0.0.0/4",  # multicast
        "240.0.0.0/4",  # reserved, incl. 255.255.255.255 broadcast
    )
)

# IANA IPv6 Special-Purpose Address Registry. Every form that carries an IPv4
# address inside (mapped, compatible, NAT64, 6to4, Teredo) is refused whole:
# it is the classic way round an IPv4 deny-list, and no public site needs it.
_BLOCKED_V6: Final = tuple(
    ipaddress.IPv6Network(net)
    for net in (
        "::/96",  # unspecified, loopback and IPv4-compatible (deprecated)
        "::ffff:0:0/96",  # IPv4-mapped
        "64:ff9b::/96",  # NAT64 well-known prefix
        "64:ff9b:1::/48",  # NAT64 local use
        "100::/64",  # discard-only
        "2001::/23",  # IETF protocol assignments (Teredo, ORCHID, benchmarking…)
        "2001:db8::/32",  # documentation
        "2002::/16",  # 6to4
        "3fff::/20",  # documentation (RFC 9637)
        "5f00::/16",  # SRv6 SIDs
        "fc00::/7",  # unique-local, incl. fd00:ec2::254 (IMDS over IPv6)
        "fe80::/10",  # link-local
        "fec0::/10",  # site-local (deprecated)
        "ff00::/8",  # multicast
    )
)


def parse_ip(text: str) -> IPAddress | None:
    """The address in ``text`` if it is a literal (``[v6]`` and ``%zone``
    allowed), else ``None``: names are for the resolver to answer."""
    candidate = text.strip()
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    candidate = candidate.split("%", 1)[0]
    if not candidate:
        return None
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        return None


def is_public_address(addr: IPAddress) -> bool:
    """``True`` only for an address on the public internet."""
    if isinstance(addr, ipaddress.IPv4Address):
        if any(addr in net for net in _BLOCKED_V4):
            return False
    elif any(addr in net for net in _BLOCKED_V6):
        return False
    # Belt and braces: whatever the running Python also considers special.
    return addr.is_global and not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


__all__ = ["ALLOWED_PORTS", "IPAddress", "is_public_address", "parse_ip"]
