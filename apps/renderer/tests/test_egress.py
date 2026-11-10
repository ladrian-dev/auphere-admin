"""The egress guard: resolve once, vet every address, refuse odd ports."""

from __future__ import annotations

import ipaddress

import pytest

from nexus_renderer.egress import EgressGuard, Refused


def resolver(table: dict[str, list[str]]):  # type: ignore[no-untyped-def]
    calls: list[str] = []

    async def resolve(host: str) -> list[str]:
        calls.append(host)
        if host not in table:
            raise OSError("nodename nor servname provided")
        return table[host]

    resolve.calls = calls  # type: ignore[attr-defined]
    return resolve


async def test_public_host_returns_vetted_addresses() -> None:
    guard = EgressGuard(resolver({"shop.example": ["93.184.215.14", "93.184.215.14"]}))
    vetted = await guard.vet("shop.example", 443)
    assert vetted == [ipaddress.ip_address("93.184.215.14")]


@pytest.mark.parametrize("port", [22, 25, 3306, 5432, 6379, 8000, 8080, 0, 65535])
async def test_non_web_port_is_refused_before_resolving(port: int) -> None:
    resolve = resolver({"shop.example": ["93.184.215.14"]})
    with pytest.raises(Refused) as exc:
        await EgressGuard(resolve).vet("shop.example", port)
    assert exc.value.reason == "port"
    assert resolve.calls == []  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "::1", "[::1]", "169.254.169.254", "169.254.170.2", "10.1.2.3", "fd00:ec2::254"],
)
async def test_private_literal_is_refused_without_dns(host: str) -> None:
    resolve = resolver({})
    with pytest.raises(Refused) as exc:
        await EgressGuard(resolve).vet(host, 80)
    assert exc.value.reason == "address"
    assert resolve.calls == []  # type: ignore[attr-defined]


async def test_name_resolving_to_private_is_refused() -> None:
    guard = EgressGuard(resolver({"metadata.example": ["169.254.169.254"]}))
    with pytest.raises(Refused) as exc:
        await guard.vet("metadata.example", 80)
    assert exc.value.reason == "address"


async def test_one_private_answer_taints_the_whole_name() -> None:
    """A name that answers public AND private is a rebinding set-up: refused,
    the same rule as ``assert_public_url`` (any non-global answer refuses)."""
    guard = EgressGuard(resolver({"mixed.example": ["93.184.215.14", "127.0.0.1"]}))
    with pytest.raises(Refused) as exc:
        await guard.vet("mixed.example", 443)
    assert exc.value.reason == "address"


async def test_link_local_answer_with_zone_is_refused() -> None:
    guard = EgressGuard(resolver({"zone.example": ["fe80::1%eth0"]}))
    with pytest.raises(Refused):
        await guard.vet("zone.example", 443)


@pytest.mark.parametrize("answers", [[], ["not-an-ip"]])
async def test_empty_or_garbled_answer_is_refused(answers: list[str]) -> None:
    guard = EgressGuard(resolver({"odd.example": answers}))
    with pytest.raises(Refused) as exc:
        await guard.vet("odd.example", 443)
    assert exc.value.reason == "unresolvable"


async def test_unknown_name_is_refused() -> None:
    with pytest.raises(Refused) as exc:
        await EgressGuard(resolver({})).vet("nowhere.example", 443)
    assert exc.value.reason == "unresolvable"


@pytest.mark.parametrize("host", ["", " ", "a" * 254, "bad host", "x\x00y"])
async def test_malformed_host_is_refused(host: str) -> None:
    with pytest.raises(Refused) as exc:
        await EgressGuard(resolver({})).vet(host, 443)
    assert exc.value.reason == "bad_host"


async def test_slow_resolver_is_refused() -> None:
    import asyncio

    async def slow(_host: str) -> list[str]:
        await asyncio.sleep(5)
        return ["93.184.215.14"]

    with pytest.raises(Refused) as exc:
        await EgressGuard(slow, resolve_timeout_s=0.05).vet("slow.example", 443)
    assert exc.value.reason == "unresolvable"
