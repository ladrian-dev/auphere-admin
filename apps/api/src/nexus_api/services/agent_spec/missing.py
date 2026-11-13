"""What an agent needs and we do not have — spec 047, amendment of 2026-10-30
(requirements 65.3 and 65.4; ``contracts/console-api.md`` §11).

One shape for the builder's job, the draft and the copilot, so the console can
say «No tenemos herramienta para: …» the same way everywhere:

- ``integration``: an integration that is not an offered connector, proposed in a
  skill or a connection request (``integration_unknown``), or the Meta catalog of
  the channel, which is linked in Channels and never «connected» (``not_linked``);
- ``module``: a module of the client that is off (``module_off``; today Reservas);
- ``tool``: a tool name that is not in the catalog (``tool_unknown``);
- ``action``: a text of the agent that promises an action none of its tools does
  (``no_tool``), with the pointer to that text.

Nothing here ever becomes a «Conectar {X}»: what is missing stays out of the
AgentSpec and the agent keeps its alternative (65.4, the limits of 65.6).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal

from nexus_api.services.agent_spec.schema import AgentSpec, dump

if TYPE_CHECKING:
    from nexus_api.services.agent_spec.validator import Context

Kind = Literal["integration", "module", "tool", "action"]
Reason = Literal["integration_unknown", "module_off", "not_linked", "tool_unknown", "no_tool"]
Source = Literal["skill", "connection_request", "tool", "text"]

#: How the console names what is not a connector.
MODULE_LABELS: Final[dict[str, str]] = {
    "reservas": "la agenda (Reservas no está activo para este cliente)",
}
NOT_LINKED_LABELS: Final[dict[str, str]] = {
    "channel_catalog": "el catálogo de productos de WhatsApp (se enlaza en Canales)",
}


@dataclass(frozen=True)
class MissingCapability:
    kind: Kind
    key: str
    label: str
    reason: Reason
    source: Source
    pointer: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "key": self.key,
            "label": self.label,
            "reason": self.reason,
            "source": self.source,
            "pointer": self.pointer,
        }


def integration(slug: str, *, source: Source, skill: str | None = None) -> MissingCapability:
    """An integration that is not an offered connector."""
    label = f"{skill} ({slug})" if skill and skill != slug else slug
    return MissingCapability("integration", slug, label, "integration_unknown", source)


def not_offered(
    slug: str, *, module: bool, source: Source, skill: str | None = None
) -> MissingCapability:
    """What a tool, a skill or a request needs and is not a connector: a module
    that is off, the Meta catalog that is not linked, or an unknown integration."""
    if module:
        return MissingCapability(
            "module", slug, MODULE_LABELS.get(slug, f"el módulo {slug}"), "module_off", source
        )
    if slug in NOT_LINKED_LABELS:
        return MissingCapability("integration", slug, NOT_LINKED_LABELS[slug], "not_linked", source)
    return integration(slug, source=source, skill=skill)


def tool(name: str) -> MissingCapability:
    return MissingCapability("tool", name, name, "tool_unknown", "tool")


def action(key: str, label: str, pointer: str | None) -> MissingCapability:
    return MissingCapability("action", key, label, "no_tool", "text", pointer)


def from_promises(spec: AgentSpec) -> list[MissingCapability]:
    """The promises of ``spec`` that none of its tools keeps (65.5), with where they
    are. Pure: it reads only the spec and ``capability_names``."""
    from nexus_api.services.agent_spec.compiler import incoherences

    return [
        action(inc.action or "", inc.detail, inc.pointer)
        for inc in incoherences(spec, None, spec.tools or [])
        if inc.code == "promises_without_tool"
    ]


def strip_doc(
    doc: Mapping[str, Any], ctx: Context
) -> tuple[dict[str, Any], list[MissingCapability]]:
    """65.3: ``doc`` without the skills and connection requests that name what is
    not an offered connector, and what was taken out. A request for something the
    client already has and does not connect (Reservas on) leaves without a note.

    Spec 047, amendment of 2026-10-30 (research D72): an agent drafted before the
    amendment can carry one of these, and the new console cannot edit skills nor
    connection requests. So every read and write of its draft goes through here:
    nothing is refused for it, and the console reads it as missing."""
    lacking: list[MissingCapability] = []
    # Spec 060 (5.7): lo de un conector que el partner perdió y el agente ya tenía
    # se conserva sin anotarse como «falta»: vuelve al rehabilitarlo.
    skill_ok = ctx.skill_integrations() | ctx.held_integrations
    offered = ctx.offered_connectors() | ctx.held_integrations
    out = dict(doc)
    skills = []
    for skill in doc.get("skills") or []:
        integ = skill.get("integration") if isinstance(skill, Mapping) else None
        if integ is not None and integ not in skill_ok:
            lacking.append(
                not_offered(
                    str(integ),
                    module=integ in MODULE_LABELS,
                    source="skill",
                    skill=str(skill.get("key") or ""),
                )
            )
            continue
        skills.append(skill)
    requests = []
    for request in doc.get("connection_requests") or []:
        integ = request.get("integration") if isinstance(request, Mapping) else None
        if integ in offered:
            requests.append(request)
        elif integ not in skill_ok:
            lacking.append(
                not_offered(str(integ), module=integ in MODULE_LABELS, source="connection_request")
            )
    for key, value in (("skills", skills), ("connection_requests", requests)):
        if value:
            out[key] = value
        else:
            out.pop(key, None)
    return out, merge(lacking)


def strip_spec(spec: AgentSpec, ctx: Context) -> tuple[AgentSpec, list[MissingCapability]]:
    """:func:`strip_doc` on a structured spec; an «instructions» one has neither."""
    if spec.mode != "structured" or not (spec.skills or spec.connection_requests):
        return spec, []
    doc = dump(spec)
    cleaned, lacking = strip_doc(doc, ctx)
    if cleaned == doc:
        return spec, lacking
    return AgentSpec.model_validate(cleaned), lacking


def _kept_by(item: MissingCapability) -> frozenset[str] | None:
    """The actions any one of which keeps the promise of an ``action`` note: by its
    key (``compiler.PROMISES``) or, for a note that only kept the label, by how the
    console says it. ``None``: a promise this code does not know."""
    from nexus_api.services.agent_spec.compiler import PROMISES

    for promise, _pattern in PROMISES:
        if promise.key == item.key:
            return promise.needs
    for promise, _pattern in PROMISES:
        if promise.label == item.label:
            return promise.needs
    return None


def _has(ctx: Context, slug: str) -> bool:
    """The client has ``slug`` now: a connected integration, the Meta catalog
    linked, or the module on (``validator.load_context`` marks them connected)."""
    return any(info.integration == slug and info.connected for info in ctx.tools.values())


def still_missing(
    items: Iterable[MissingCapability], spec: AgentSpec, ctx: Context
) -> list[MissingCapability]:
    """Spec 057, requirement 6 (research R6): of what was noted as missing
    (``policies.builder``, copied to every version and never recomputed), what is
    still missing for ``spec`` and the client of ``ctx``:

    - ``action``: out when one of the version's tools does it — the same test as
      ``compiler.uncovered_promises``;
    - ``module``: out when the module is on (Reservas);
    - ``integration``: out when it is connected now (or the catalog is linked);
    - ``tool`` (``tool_unknown``): stays.

    Worked out on every read, never written back as a migration: an agent with a
    stale note looks right as it is (6.4)."""
    from nexus_api.api.console.capability_names import actions_of

    doable = actions_of(spec.tools or [])
    out: list[MissingCapability] = []
    for item in items:
        if item.kind == "action":
            needs = _kept_by(item)
            if needs is not None and needs & doable:
                continue
        elif item.kind in ("module", "integration") and _has(ctx, item.key):
            continue
        out.append(item)
    return merge(out)


def merge(*groups: Iterable[MissingCapability]) -> list[MissingCapability]:
    """All of them, in order, once each: the console says each missing capability
    once (by kind and key), with the first place it was found."""
    seen: set[tuple[str, str]] = set()
    out: list[MissingCapability] = []
    for group in groups:
        for item in group:
            mark = (item.kind, item.key)
            if mark in seen:
                continue
            seen.add(mark)
            out.append(item)
    return out


def from_json(items: Sequence[Mapping[str, Any]] | None) -> list[MissingCapability]:
    """What was stored on a version (``policies.builder.missing_capabilities``);
    whatever does not have the shape is left out."""
    out: list[MissingCapability] = []
    for raw in items or []:
        try:
            out.append(
                MissingCapability(
                    kind=raw["kind"],
                    key=str(raw["key"]),
                    label=str(raw["label"]),
                    reason=raw["reason"],
                    source=raw["source"],
                    pointer=raw.get("pointer"),
                )
            )
        except (KeyError, TypeError):
            continue
    return out


__all__ = [
    "MODULE_LABELS",
    "NOT_LINKED_LABELS",
    "MissingCapability",
    "action",
    "from_json",
    "from_promises",
    "integration",
    "merge",
    "not_offered",
    "still_missing",
    "strip_doc",
    "strip_spec",
    "tool",
]
