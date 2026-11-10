"""The shape of a sector guide — spec 047, amendment of 2026-10-29 (requirement 58;
research D47 and D66; ``contracts/admin-sector-guides.md`` §Guide).

One shape for the three kinds of guide:

- Auphere's guides derived from the vertical templates (``guides.yaml``);
- the guides Auphere converted from a generated one (``sector_guides``, 0207);
- the guide the builder generates **for one client** whose sector has no guide
  (``generated_guides``, 0206).

A guide is a trade example for the builder (requirement 15.6), never an order: the
generated one comes from a model fed with an untrusted label, so it is validated
here (closed shape, bounded lengths) and fenced in the prompt.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from typing import Annotated, Any, Final

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)

from nexus_api.services.agent_spec.retired import RETIRED_PREFIX

ASK_MAX: Final = 10
PROCEDURES_MAX: Final = 10
RISKS_MAX: Final = 10
TOOLS_MAX: Final = 20
LABEL_KEY_MAX: Final = 60

Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
ToolName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$", max_length=80)]


class GuideInvalid(ValueError):
    """A guide or its tests that cannot be stored: ``invalid_guide``,
    ``invalid_test``, ``twelve_tests_required`` or ``duplicate_key``."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


class GuideProcedure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    when: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""
    steps: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1500)]


class Guide(BaseModel):
    """What to ask the business, its typical procedures, what goes to a person and
    the tools the trade usually needs (58.1)."""

    model_config = ConfigDict(extra="forbid")

    ask: list[Line] = Field(min_length=1, max_length=ASK_MAX)
    procedures: list[GuideProcedure] = Field(default_factory=list, max_length=PROCEDURES_MAX)
    risks: list[Line] = Field(default_factory=list, max_length=RISKS_MAX)
    tools: list[ToolName] = Field(default_factory=list, max_length=TOOLS_MAX)

    @field_validator("tools")
    @classmethod
    def _never_retired(cls, value: list[str]) -> list[str]:
        # Spec 048: the agenda is Reservas; no guide ever names ``booking.*``.
        if any(name.startswith(RETIRED_PREFIX) for name in value):
            raise ValueError("booking.* is retired")
        return list(dict.fromkeys(value))


def validate_guide(raw: object) -> Guide:
    """``raw`` as a :class:`Guide`, or :class:`GuideInvalid` (``invalid_guide``)."""
    if isinstance(raw, Guide):
        return raw
    if not isinstance(raw, Mapping):
        raise GuideInvalid("invalid_guide")
    try:
        return Guide.model_validate(dict(raw))
    except ValidationError as exc:
        raise GuideInvalid("invalid_guide", str(exc)) from exc


def validate_tests(raw: object) -> list[dict[str, Any]]:
    """Exactly 12 sector tests in the catalog's shape (``sector_catalog.SectorTest``)."""
    from nexus_api.services.testing.sector_catalog import SectorCatalogError
    from nexus_api.services.testing.sector_catalog import validate_tests as validate_catalog

    if not isinstance(raw, list) or not all(isinstance(item, Mapping) for item in raw):
        raise GuideInvalid("invalid_test")
    try:
        return [test.model_dump() for test in validate_catalog(raw)]
    except SectorCatalogError as exc:
        raise GuideInvalid(exc.code, str(exc)) from exc


def label_key(label: object) -> str:
    """The normalised label: lower case, no accents, words of ``[a-z0-9]`` split by
    one space. «Gimnásio» and «gimnasio» are the same sector (``label_key`` in
    ``generated_guides`` and ``sector_guides``). Empty for an empty label."""
    text = unicodedata.normalize("NFKD", str(label or "").lower())
    plain = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", plain))[:LABEL_KEY_MAX].strip()


def render(guide: Guide) -> str:
    """The guide as text for a prompt, in a stable order."""
    lines: list[str] = ["Qué preguntar al negocio si no está en la ficha:"]
    lines += [f"- {item}" for item in guide.ask]
    if guide.procedures:
        lines.append("Procedimientos típicos del oficio:")
        for proc in guide.procedures:
            when = f" (cuando: {proc.when})" if proc.when else ""
            lines.append(f"- {proc.title}{when}: {proc.steps}")
    if guide.risks:
        lines.append("Lo que hay que pasar a una persona:")
        lines += [f"- {item}" for item in guide.risks]
    if guide.tools:
        lines.append(
            "Herramientas que el oficio suele necesitar (solo si están en <herramientas>):"
        )
        lines.append("- " + ", ".join(guide.tools))
    return "\n".join(lines)


__all__ = [
    "Guide",
    "GuideInvalid",
    "GuideProcedure",
    "label_key",
    "render",
    "validate_guide",
    "validate_tests",
]
