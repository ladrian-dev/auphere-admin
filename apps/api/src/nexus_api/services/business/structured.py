"""schema.org structured data, read without a model — spec 047, amendment of
2026-10-29 (requirement 59.1; research D49).

Many small-business sites (Wix, Squarespace, WordPress with Yoast) publish their
name, address, phone, opening hours, services with prices and FAQ as JSON-LD or
microdata. The old reader dropped every ``<script>``, JSON-LD included. Here they
are read **without a model** and turned into the same JSON the reader asks the
model for, so they go through the very same validation (``reader.parse_extraction``):
only business data, bounded, typed. Nothing else in the markup — actions, targets,
free text that looks like an order — has a field to land in (§III).

What is mapped:

- a business (any item with a name and an address, a phone or opening hours) →
  a location: name, address, phone;
- ``openingHoursSpecification`` and ``openingHours`` → the weekly hours;
- ``makesOffer`` / ``hasOfferCatalog`` / ``Service`` items with ``offers`` →
  services with their price;
- ``FAQPage`` → questions and answers.

Malformed JSON-LD is skipped, never an error.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from html.parser import HTMLParser
from typing import Any, Final

WEEKDAYS: Final[tuple[str, ...]] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_DAY_NAMES: Final[dict[str, str]] = {
    "monday": "mon",
    "tuesday": "tue",
    "wednesday": "wed",
    "thursday": "thu",
    "friday": "fri",
    "saturday": "sat",
    "sunday": "sun",
    "mo": "mon",
    "tu": "tue",
    "we": "wed",
    "th": "thu",
    "fr": "fri",
    "sa": "sat",
    "su": "sun",
}
#: How much structured data is read from one page, at most.
MAX_BLOCKS: Final = 20
MAX_BLOCK_CHARS: Final = 200_000
MAX_ITEMS: Final = 200
_VOID: Final = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)
_TIME: Final = re.compile(r"^(\d{1,2}):(\d{2})")


# ── parsing the page ─────────────────────────────────────────────────────────


class StructuredParser(HTMLParser):
    """Collects the JSON-LD blocks and the microdata items of a page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.jsonld: list[str] = []
        self.items: list[dict[str, Any]] = []
        self._in_jsonld = False
        self._buffer: list[str] = []
        # Microdata: a stack of open elements; each knows whether it opened an
        # item and whether it is capturing text for a property.
        self._stack: list[dict[str, Any]] = []
        self._scopes: list[dict[str, Any]] = []

    # JSON-LD ------------------------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k.lower(): (v or "") for k, v in attrs}
        if tag == "script" and values.get("type", "").lower().startswith("application/ld+json"):
            self._in_jsonld = True
            self._buffer = []
            return
        self._microdata_start(tag, values, has_scope="itemscope" in values)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k.lower(): (v or "") for k, v in attrs}
        self._microdata_start(tag, values, has_scope="itemscope" in values, void=True)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            if len(self.jsonld) < MAX_BLOCKS:
                self.jsonld.append("".join(self._buffer)[:MAX_BLOCK_CHARS])
            return
        # Close up to the matching open element (HTML is forgiving).
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i]["tag"] == tag:
                for frame in reversed(self._stack[i:]):
                    self._close(frame)
                del self._stack[i:]
                break

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._buffer.append(data)
            return
        for frame in self._stack:
            if frame.get("text") is not None:
                frame["text"].append(data)

    # Microdata ----------------------------------------------------------------
    def _microdata_start(
        self, tag: str, values: dict[str, str], *, has_scope: bool, void: bool = False
    ) -> None:
        prop = values.get("itemprop", "").strip()
        frame: dict[str, Any] = {"tag": tag, "prop": prop, "item": None, "text": None}
        if has_scope:
            item: dict[str, Any] = {"@type": values.get("itemtype", "").strip()}
            frame["item"] = item
            if not self._scopes and len(self.items) < MAX_ITEMS:
                self.items.append(item)
            elif self._scopes and prop:
                _add(self._scopes[-1], prop, item)
            self._scopes.append(item)
        elif prop and self._scopes:
            direct = next(
                (
                    values[attr]
                    for attr in ("content", "datetime", "href", "src")
                    if values.get(attr)
                ),
                None,
            )
            if direct is not None:
                _add(self._scopes[-1], prop, direct.strip())
            elif not void and tag not in _VOID:
                frame["text"] = []
        if void or tag in _VOID:
            if frame["item"] is not None:
                self._scopes.pop()
            return
        self._stack.append(frame)

    def _close(self, frame: dict[str, Any]) -> None:
        if frame["item"] is not None and self._scopes and self._scopes[-1] is frame["item"]:
            self._scopes.pop()
        elif frame.get("text") is not None and frame["prop"] and self._scopes:
            text = " ".join("".join(frame["text"]).split())
            if text:
                _add(self._scopes[-1], frame["prop"], text)


def _add(item: dict[str, Any], prop: str, value: Any) -> None:
    for name in prop.split():
        if name in item:
            current = item[name]
            item[name] = [*current, value] if isinstance(current, list) else [current, value]
        else:
            item[name] = value


def _jsonld_nodes(blocks: list[str]) -> list[Any]:
    """Each JSON-LD block that parses. One nested too deep makes ``json.loads``
    raise ``RecursionError`` (spec 047, T217): that block is skipped, the others
    and the rest of the reading go on."""
    nodes: list[Any] = []
    for raw in blocks:
        try:
            data = json.loads(raw.strip())
        except (json.JSONDecodeError, ValueError, RecursionError):
            continue
        nodes.append(data)
    return nodes


# ── walking schema.org items ─────────────────────────────────────────────────


def _types(node: dict[str, Any]) -> set[str]:
    raw = node.get("@type") or node.get("type") or ()
    names = [raw] if isinstance(raw, str) else [t for t in raw if isinstance(t, str)]
    return {name.rsplit("/", 1)[-1].lower() for name in names}


def _walk(node: Any, depth: int = 0) -> Iterator[dict[str, Any]]:
    if depth > 8:
        return
    if isinstance(node, list):
        for item in node[:MAX_ITEMS]:
            yield from _walk(item, depth + 1)
    elif isinstance(node, dict):
        yield node
        for key, value in node.items():
            if key in {"@graph", "mainEntity", "itemListElement", "hasOfferCatalog", "makesOffer",
                       "department", "subOrganization", "location", "containsPlace"}:  # fmt: skip
                yield from _walk(value, depth + 1)


def _text(value: Any) -> str | None:
    if isinstance(value, list):
        value = next((v for v in value if isinstance(v, str | int | float)), None)
    if isinstance(value, dict):
        value = value.get("@value") or value.get("name") or value.get("text")
    if isinstance(value, str | int | float) and not isinstance(value, bool):
        text = " ".join(str(value).split())
        return text or None
    return None


def _address(value: Any) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, str):
        return _text(value)
    if not isinstance(value, dict):
        return None
    street = _text(value.get("streetAddress"))
    city = " ".join(
        part
        for part in (_text(value.get("postalCode")), _text(value.get("addressLocality")))
        if part
    )
    return ", ".join(part for part in (street, city) if part) or None


def _hm(raw: Any) -> str | None:
    match = _TIME.match(str(raw or "").strip())
    if not match:
        return None
    hours, minutes = int(match.group(1)), int(match.group(2))
    if hours > 24 or minutes > 59:
        return None
    return f"{hours:02d}:{minutes:02d}"


def _day(raw: Any) -> str | None:
    name = str(raw or "").rsplit("/", 1)[-1].strip().lower()
    return _DAY_NAMES.get(name) or _DAY_NAMES.get(name[:2])


def _days_range(spec: str) -> list[str]:
    days: list[str] = []
    for part in spec.split(","):
        bounds = [_day(p) for p in part.split("-")]
        if len(bounds) == 2 and bounds[0] and bounds[1]:
            start, end = WEEKDAYS.index(bounds[0]), WEEKDAYS.index(bounds[1])
            span = range(start, end + 1) if start <= end else [*range(start, 7), *range(end + 1)]
            days += [WEEKDAYS[i] for i in span]
        elif len(bounds) == 1 and bounds[0]:
            days.append(bounds[0])
    return days


def opening_hours(values: list[str]) -> dict[str, list[dict[str, str]]]:
    """``"Mo-Fr 09:00-14:00"`` (schema.org ``openingHours``) → the weekly hours."""
    out: dict[str, list[dict[str, str]]] = {}
    for value in values:
        for chunk in str(value).split(";"):
            match = re.match(r"^\s*([A-Za-z,\- ]+?)\s+(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", chunk)
            if not match:
                continue
            opens, closes = _hm(match.group(2)), _hm(match.group(3))
            if not opens or not closes:
                continue
            for day in _days_range(match.group(1).replace(" ", "")):
                shift = {"open": opens, "close": closes}
                if shift not in out.setdefault(day, []):
                    out[day].append(shift)
    return out


def _hours_of(node: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    days: dict[str, list[dict[str, str]]] = {}
    specs = node.get("openingHoursSpecification")
    for spec in specs if isinstance(specs, list) else [specs]:
        if not isinstance(spec, dict):
            continue
        opens, closes = _hm(spec.get("opens")), _hm(spec.get("closes"))
        raw_days = spec.get("dayOfWeek")
        for raw in raw_days if isinstance(raw_days, list) else [raw_days]:
            day = _day(raw)
            if day is None:
                continue
            if opens and closes and opens != closes:
                shift = {"open": opens, "close": closes}
                if shift not in days.setdefault(day, []):
                    days[day].append(shift)
            else:
                days.setdefault(day, [])
    strings = node.get("openingHours")
    if strings:
        for day, shifts in opening_hours(
            strings if isinstance(strings, list) else [strings]
        ).items():
            for shift in shifts:
                if shift not in days.setdefault(day, []):
                    days[day].append(shift)
    return days


def _offers(node: dict[str, Any]) -> list[dict[str, Any]]:
    """A ``Service``/``Product``/``Offer`` as one or more services with a price."""
    types = _types(node)
    out: list[dict[str, Any]] = []
    if "offer" in types:
        offered = node.get("itemOffered")
        name = _text(offered.get("name")) if isinstance(offered, dict) else _text(offered)
        description = _text(offered.get("description")) if isinstance(offered, dict) else None
        price, currency = node.get("price"), _text(node.get("priceCurrency"))
    elif types & {"service", "product", "menuitem"}:
        name, description = _text(node.get("name")), _text(node.get("description"))
        offer = node.get("offers")
        offer = offer[0] if isinstance(offer, list) and offer else offer
        price = offer.get("price") if isinstance(offer, dict) else None
        currency = _text(offer.get("priceCurrency")) if isinstance(offer, dict) else None
    else:
        return out
    if not name:
        return out
    service: dict[str, Any] = {"name": name[:120], "bookable": False}
    if description:
        service["description"] = description[:1000]
    try:
        amount = float(str(price).replace(",", ".")) if price not in (None, "") else None
    except ValueError:
        amount = None
    if amount is not None and currency:
        service["price_amount"] = amount
        service["currency"] = currency
    out.append(service)
    return out


def _is_business(node: dict[str, Any]) -> bool:
    if _types(node) & {"faqpage", "question", "answer", "offer", "service", "product", "postaladdress",
                       "openinghoursspecification", "website", "webpage", "breadcrumblist",
                       "imageobject", "person", "menuitem"}:  # fmt: skip
        return False
    return bool(_text(node.get("name"))) and any(
        node.get(key)
        for key in ("address", "telephone", "openingHours", "openingHoursSpecification")
    )


def to_extraction(nodes: list[Any]) -> dict[str, Any]:
    """schema.org nodes → the JSON the reader asks the model for (only the keys
    it found). Nothing else survives."""
    locations: list[dict[str, Any]] = []
    hours: dict[str, list[dict[str, str]]] = {}
    services: list[dict[str, Any]] = []
    faqs: list[dict[str, str]] = []
    for node in _walk(nodes):
        types = _types(node)
        if _is_business(node):
            location: dict[str, Any] = {"name": _text(node.get("name"))}
            address = _address(node.get("address"))
            phone = _text(node.get("telephone"))
            if address:
                location["address"] = address
            if phone:
                location["phone"] = phone
            if location not in locations:
                locations.append(location)
            for day, shifts in _hours_of(node).items():
                for shift in shifts:
                    if shift not in hours.setdefault(day, []):
                        hours[day].append(shift)
                hours.setdefault(day, [])
        if "question" in types:
            answer = node.get("acceptedAnswer")
            q = _text(node.get("name"))
            a = _text(answer.get("text")) if isinstance(answer, dict) else _text(answer)
            if q and a and {"q": q, "a": a} not in faqs:
                faqs.append({"q": q[:300], "a": a[:2000]})
        for service in _offers(node):
            if not any(s["name"] == service["name"] for s in services):
                services.append(service)
    out: dict[str, Any] = {}
    if locations:
        out["locations"] = locations[:50]
    if any(hours.values()):
        out["hours"] = hours
    if services:
        out["services"] = services[:500]
    if faqs:
        out["faqs"] = faqs[:200]
    return out


def _microdata_nodes(items: list[dict[str, Any]]) -> list[Any]:
    """Microdata items as JSON-LD-like nodes (``@type`` already in place)."""
    return list(items)


def extract_structured(html: str) -> dict[str, Any]:
    """The JSON-LD and the microdata of a page, as the reader's extraction JSON."""
    parser = StructuredParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # pragma: no cover - HTMLParser is lenient
        return {}
    nodes = [*_jsonld_nodes(parser.jsonld), *_microdata_nodes(parser.items)]
    return to_extraction(nodes) if nodes else {}


__all__ = ["StructuredParser", "extract_structured", "opening_hours", "to_extraction"]
