"""«Sin datos del cliente» — spec 047, amendment of 2026-10-29 (requirement 58.5;
``contracts/admin-sector-guides.md`` §ClientDataFinding).

Before a generated guide becomes an Auphere guide (shared by every client with the
same label), nothing of the client it came from may remain in it. Two kinds of
check, over every string of ``{"guide": …, "tests": […]}``:

- **what belongs to that client**: its name, its website's domain, the names,
  addresses and phones of its locations, the names and e-mails of its staff, its
  owner's phone and e-mail, the names of its networks;
- **contact data of anyone**: any URL, e-mail or phone-like number. An Auphere
  guide never carries contact data.

A name is matched as whole words, ignoring case and accents. Short names (under 4
characters) are skipped: they would match ordinary words.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

_URL: Final = re.compile(
    r"\b(?:https?://|www\.)\S+|\b[a-z0-9-]+\.(?:com|es|net|org|io|eu|cat|info|shop|store)\b", re.I
)
_EMAIL: Final = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
# Seven or more digits, with spaces, dots or dashes between them: a phone.
_PHONE: Final = re.compile(r"(?<![\w])\+?\d(?:[\s.\-]?\d){6,}(?![\w])")
MIN_NAME: Final = 4
EXCERPT: Final = 80
#: The kinds that are how the client is called: the sector's label never exempts them.
_OWN: Final = frozenset({"client_name", "location"})


@dataclass(frozen=True)
class Finding:
    pointer: str
    kind: str
    excerpt: str

    def out(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ClientData:
    """What identifies the client, already normalised for matching."""

    names: tuple[tuple[str, str], ...] = ()  # (kind, value)
    domains: tuple[str, ...] = ()
    phones: tuple[str, ...] = ()  # digits only


def _plain(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in folded if not unicodedata.combining(c))


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    host = re.sub(r"^[a-z]+://", "", url.strip().lower()).split("/")[0].split(":")[0]
    host = host.removeprefix("www.")
    return host or None


def _strings(node: Any, pointer: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(node, str):
        yield pointer, node
    elif isinstance(node, Mapping):
        for key, value in node.items():
            yield from _strings(value, f"{pointer}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _strings(value, f"{pointer}/{i}")


def _excerpt(text: str, start: int, end: int) -> str:
    half = max(0, (EXCERPT - (end - start)) // 2)
    lo, hi = max(0, start - half), min(len(text), end + half)
    snippet = text[lo:hi].strip()
    prefix = "…" if lo > 0 else ""
    suffix = "…" if hi < len(text) else ""
    return (prefix + snippet + suffix)[: EXCERPT + 2]


def scan(doc: Mapping[str, Any], data: ClientData) -> list[Finding]:
    """Every place in ``doc`` that carries data of the client or contact data,
    in document order. Empty: nothing found."""
    found: list[Finding] = []
    seen: set[tuple[str, str]] = set()

    def add(pointer: str, kind: str, text: str, start: int, end: int) -> None:
        if (pointer, kind) in seen:
            return
        seen.add((pointer, kind))
        found.append(Finding(pointer=pointer, kind=kind, excerpt=_excerpt(text, start, end)))

    for pointer, text in _strings(doc):
        plain = _plain(text)
        for kind, value in data.names:
            words = "[^a-z0-9]+".join(re.escape(w) for w in value.split())
            hit = re.search(r"(?<![a-z0-9])" + words + r"(?![a-z0-9])", plain)
            if hit:
                add(pointer, kind, text, hit.start(), hit.end())
        for domain in data.domains:
            at = plain.find(domain)
            if at >= 0:
                add(pointer, "website", text, at, at + len(domain))
        for hit in _EMAIL.finditer(text):
            add(pointer, "email", text, hit.start(), hit.end())
        for hit in _URL.finditer(text):
            if not _EMAIL.search(hit.group(0)):
                add(pointer, "url", text, hit.start(), hit.end())
        for hit in _PHONE.finditer(text):
            add(pointer, "phone", text, hit.start(), hit.end())
        digits = _digits(text)
        for phone in data.phones:
            if phone and phone in digits:
                at = text.find(phone[-4:])
                add(pointer, "phone", text, max(0, at), max(0, at) + 4)
    return found


def _name(kind: str, value: str | None) -> tuple[str, str] | None:
    plain = " ".join(re.findall(r"[a-z0-9]+", _plain(value or "")))
    return (kind, plain) if len(plain) >= MIN_NAME else None


async def load(
    session: AsyncSession, tenant_id: uuid.UUID, *, label: str | None = None
) -> ClientData:
    """What identifies ``tenant_id``, read inside its own scope (the caller has
    declared it). Every query filters by the tenant itself.

    A name equal to the sector's ``label`` is the sector's word, not the client's:
    staff or an address that happen to say «Gimnasio» do not make every gym guide
    dirty. **Unless** the label is the client's own name (its name or a network
    handle) or the name of one of its locations (spec 047, T217, security review of
    2026-10-30): then it is how the client is called, and an Auphere guide shared by
    every client with that label must not carry it."""
    from nexus_api.db.models import Tenant
    from nexus_api.db.models.business import BusinessLink, BusinessLocation, BusinessProfile
    from nexus_api.db.models.reservation import ReservationStaff

    names: list[tuple[str, str] | None] = []
    domains: list[str | None] = []
    phones: list[str] = []
    tenant = await session.get(Tenant, tenant_id)
    if tenant is not None:
        names.append(_name("client_name", tenant.name))
        if tenant.owner_email:
            names.append(_name("email", tenant.owner_email))
        if tenant.owner_phone:
            phones.append(_digits(tenant.owner_phone))
    profile = await session.get(BusinessProfile, tenant_id)
    if profile is not None:
        domains.append(_domain(profile.website))
    for loc in (
        await session.scalars(
            sa.select(BusinessLocation).where(BusinessLocation.tenant_id == tenant_id)
        )
    ).all():
        names.append(_name("location", loc.name))
        names.append(_name("address", loc.address))
        if loc.phone_e164:
            phones.append(_digits(loc.phone_e164))
    for staff in (
        await session.scalars(
            sa.select(ReservationStaff).where(ReservationStaff.tenant_id == tenant_id)
        )
    ).all():
        names.append(_name("staff", staff.name))
        if staff.email:
            names.append(_name("email", staff.email))
    for link in (
        await session.scalars(sa.select(BusinessLink).where(BusinessLink.tenant_id == tenant_id))
    ).all():
        # The handle on a network is the client's name there.
        names.append(_name("client_name", (link.handle or "").lstrip("@")))
    generic = {"sede centro", "sede principal", "centro", "principal"}
    if label:
        word = " ".join(re.findall(r"[a-z0-9]+", _plain(label)))
        own = {value for kind, value in (n for n in names if n is not None) if kind in _OWN}
        if word not in own:
            generic.add(word)
    clean = [n for n in names if n is not None and n[1] not in generic]
    return ClientData(
        names=tuple(dict.fromkeys(clean)),
        domains=tuple(dict.fromkeys(d for d in domains if d and "." in d)),
        phones=tuple(dict.fromkeys(p[-9:] for p in phones if len(p) >= 7)),
    )


__all__ = ["ClientData", "Finding", "load", "scan"]
