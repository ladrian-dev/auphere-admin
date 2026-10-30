"""Auphere's sector guides derived from the vertical templates — spec 047, amendment
of 2026-10-29 (requirement 58.1; research D47).

``guides.yaml`` holds, per sector of ``sectors.SECTORS``, what the trade asks, its
procedures and what goes to a person, curated from the templates of that sector
(``TEMPLATE_SECTOR``), plus ``generic``: Auphere's generic guide and its 12 tests,
the base to generate a guide for a sector without one (58.4).

The tools are **not** written by hand: they are the ``tools.required`` of the
sector's templates, already moved to Reservas by spec 048, minus ``booking.*`` and
anything retired. A guide only *suggests* them: the builder sees a tool only if
it exists in the catalog and this client has it available, and ``reservas.*``
only when Reservas is on and the description asks for it (D67).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import yaml

from nexus_api.services.agent_spec.retired import RETIRED_PREFIX, RETIRED_TOOLS
from nexus_api.services.builder.guides.schema import TOOLS_MAX, Guide, validate_guide
from nexus_api.services.builder.sectors import SECTORS, TEMPLATE_SECTOR

DATA_FILE: Final = Path(__file__).with_name("guides.yaml")
GENERIC: Final = "generic"


@dataclass(frozen=True)
class AuphereGuide:
    """One of Auphere's guides: from the templates (``source = "template"``) or
    converted from a generated one (``source = "promoted"``, table 0207)."""

    key: str
    label: str
    guide: Guide
    source: str = "template"
    templates: tuple[str, ...] = ()
    version: int = 1
    published_by: str | None = None
    published_at: Any = None


@lru_cache(maxsize=1)
def _data() -> dict[str, Any]:
    raw = yaml.safe_load(DATA_FILE.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError("guides.yaml must be a mapping")
    return raw


def template_tools(templates: tuple[str, ...]) -> list[str]:
    """The union of the templates' tools, in order, without ``booking.*`` nor
    anything retired."""
    from nexus_api.services.templating.seed_templates import load_seed_template

    out: list[str] = []
    for name in templates:
        for tool in load_seed_template(name).tools_required:
            if tool.startswith(RETIRED_PREFIX) or tool in RETIRED_TOOLS or tool in out:
                continue
            out.append(tool)
    return out[:TOOLS_MAX]


def _build(key: str, entry: dict[str, Any], label: str) -> AuphereGuide:
    templates = tuple(str(t) for t in entry.get("templates") or ())
    tools = entry.get("tools") or template_tools(templates)
    guide = validate_guide(
        {
            "ask": entry.get("ask") or [],
            "procedures": entry.get("procedures") or [],
            "risks": entry.get("risks") or [],
            "tools": list(tools),
        }
    )
    return AuphereGuide(key=key, label=label, guide=guide, templates=templates)


@lru_cache(maxsize=1)
def template_guides() -> dict[str, AuphereGuide]:
    """The six guides of the templates, in the order of the sectors."""
    data = _data()
    return {key: _build(key, data[key], label) for key, label in SECTORS.items()}


def auphere_guide(key: str | None) -> AuphereGuide | None:
    """The guide of a sector of the closed list (``None`` for «otro»)."""
    return template_guides().get(key or "")


@lru_cache(maxsize=1)
def generic_guide() -> AuphereGuide:
    """Auphere's generic guide: the base to generate one for a sector without
    guide, never data of any client (58.4)."""
    return _build(GENERIC, _data()[GENERIC], "Genérica")


@lru_cache(maxsize=1)
def generic_tests() -> tuple[dict[str, Any], ...]:
    """The 12 tests of the generic guide, valid for any business."""
    from nexus_api.services.builder.guides.schema import validate_tests

    return tuple(validate_tests(list(_data()[GENERIC].get("tests") or [])))


def templates_of(sector: str) -> tuple[str, ...]:
    """The templates a sector's guide comes from (``TEMPLATE_SECTOR``)."""
    return tuple(name for name, group in TEMPLATE_SECTOR.items() if group == sector)


__all__ = [
    "GENERIC",
    "AuphereGuide",
    "auphere_guide",
    "generic_guide",
    "generic_tests",
    "template_guides",
    "template_tools",
    "templates_of",
]
