"""Which addresses Chromium may reach (spec 047, requirement 59.2, D50).

The verdict is explicit — an IANA special-purpose table — so it does not move
with the Python patch release (``is_global`` changed in 3.11.10, 3.12.4 and
3.13, and the base image ships Ubuntu's 3.12). The API suite checks this same
file against ``knowledge_indexer.assert_public_url``
(``apps/api/tests/unit/test_renderer_client.py``).
"""

from __future__ import annotations

import ipaddress

import pytest

from nexus_renderer.addresses import ALLOWED_PORTS, is_public_address, parse_ip

PUBLIC = [
    "8.8.8.8",
    "1.1.1.1",
    "93.184.215.14",
    "151.101.1.140",
    "2606:4700::1111",
    "2001:4860:4860::8888",
    "2a00:1450:4001:80b::200e",
]

NOT_PUBLIC = [
    # loopback
    "127.0.0.1",
    "127.255.255.254",
    "::1",
    # "this network" / unspecified
    "0.0.0.0",
    "0.1.2.3",
    "::",
    # RFC 1918
    "10.0.0.1",
    "172.16.0.1",
    "172.31.255.255",
    "192.168.1.1",
    # link-local, with the two cloud metadata endpoints by name
    "169.254.169.254",  # EC2 instance metadata (IMDS)
    "169.254.170.2",  # ECS task metadata and task-role credentials
    "169.254.169.253",  # VPC DNS resolver
    "fe80::1",
    # CGNAT (RFC 6598)
    "100.64.0.1",
    "100.127.255.254",
    # multicast and broadcast
    "224.0.0.1",
    "239.255.255.250",
    "255.255.255.255",
    "ff02::1",
    "ff0e::1",
    # reserved and documentation / benchmarking
    "240.0.0.1",
    "192.0.0.9",
    "192.0.2.1",
    "198.18.0.1",
    "198.51.100.7",
    "203.0.113.9",
    "192.88.99.1",
    "2001:db8::1",
    "3fff::1",
    # IPv6 unique-local, incl. the IPv6 IMDS endpoint
    "fd00:ec2::254",
    "fc00::1",
    # deprecated site-local
    "fec0::1",
    # IPv4 embedded in IPv6: mapped, compatible, NAT64, 6to4, Teredo
    "::ffff:127.0.0.1",
    "::ffff:169.254.169.254",
    "::ffff:8.8.8.8",  # mapped is refused even when the IPv4 inside is public
    "::127.0.0.1",
    "64:ff9b::a9fe:a9fe",
    "64:ff9b::808:808",
    "64:ff9b:1::1",
    "2002:7f00:1::",
    "2002:808:808::",
    "2001:0:4136:e378:8000:63bf:3fff:fdd2",
]


@pytest.mark.parametrize("literal", PUBLIC)
def test_public_addresses_pass(literal: str) -> None:
    assert is_public_address(ipaddress.ip_address(literal)) is True


@pytest.mark.parametrize("literal", NOT_PUBLIC)
def test_non_public_addresses_are_refused(literal: str) -> None:
    assert is_public_address(ipaddress.ip_address(literal)) is False


def test_only_web_ports() -> None:
    assert frozenset({80, 443}) == ALLOWED_PORTS


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("8.8.8.8", "8.8.8.8"),
        ("[::1]", "::1"),
        ("fe80::1%eth0", "fe80::1"),
        ("[fe80::1%25eth0]", "fe80::1"),
        ("example.com", None),
        ("", None),
        ("2130706433", None),  # not an address literal: the resolver decides it
    ],
)
def test_parse_ip(text: str, expected: str | None) -> None:
    parsed = parse_ip(text)
    assert (str(parsed) if parsed is not None else None) == expected
