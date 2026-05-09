"""Seed-template loader for agent_config v1 bootstrap.

Phase 1 ships ``barbershop_v1`` (Cultor Barber). Future verticals
(``pharmacy_v1``, ``beauty_spa_v1``, etc.) drop YAML files in the
``seeds/`` sibling directory.

Render flow:

    template = load_seed_template("barbershop_v1")
    rendered = render_seed_template(
        template,
        placeholders={
            "tenant.name": "Cultor Barber",
            "tenant.address": "Las Condes, Santiago",
            "tenant.timezone": "America/Santiago",
            "tenant.business_hours_label": "Lun-Sáb 10-19",
            "owner.first_name": "Diego",
        },
    )
    # rendered.system_prompt → str con placeholders resueltos
    # rendered.tools         → list[str]
    # rendered.policies      → dict[str, Any]

If a placeholder is referenced by the prompt but missing from the
caller (and has no default), ``render_seed_template`` raises
``SeedTemplatePlaceholderMissing`` with the offending key. Fail-fast
before persisting an agent_config — el seed roto no debe llegar al
runtime.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_SEEDS_DIR = Path(__file__).resolve().parent / "seeds"
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z][a-zA-Z0-9_.]*)\}")


class SeedTemplateNotFound(Exception):
    """Raised when ``load_seed_template`` cannot find the YAML file."""


class SeedTemplatePlaceholderMissing(Exception):
    """Raised by ``render_seed_template`` when a placeholder has no value.

    ``key`` is the dotted path that appeared in the prompt
    (e.g. ``tenant.business_hours_label``). The error message tells the
    operator which field of the client onboarding form is expected.
    """

    def __init__(self, key: str) -> None:
        super().__init__(
            f"seed template placeholder {{{key}}} has no value and no default; "
            f"provide it via the placeholders dict before rendering"
        )
        self.key = key


@dataclass(frozen=True)
class SeedTemplate:
    """Parsed seed template. Raw YAML kept under ``raw`` for debugging."""

    name: str
    version: str
    display_name: str
    system_prompt: str
    tools_required: list[str]
    policies_default: dict[str, Any]
    agent_defaults: dict[str, str]
    raw: dict[str, Any] = field(repr=False)


@dataclass(frozen=True)
class RenderedSeedTemplate:
    """Result of ``render_seed_template`` — ready to feed into
    ``AgentConfigService.stage_new_version``."""

    seed_template_ref: str
    system_prompt: str
    tools: list[str]
    policies: dict[str, Any]


def list_seed_templates() -> list[str]:
    """Return template names available on disk (without ``.yaml``)."""
    if not _SEEDS_DIR.is_dir():
        return []
    return sorted(p.stem for p in _SEEDS_DIR.glob("*.yaml"))


def load_seed_template(name: str) -> SeedTemplate:
    """Load and shape-validate ``seeds/<name>.yaml``.

    Raises ``SeedTemplateNotFound`` if the file is missing.
    Raises ``ValueError`` if a required key is absent — this is a repo
    bug (the YAML shipped wrong), not a runtime input error.
    """
    path = _SEEDS_DIR / f"{name}.yaml"
    if not path.is_file():
        raise SeedTemplateNotFound(f"seed template {name!r} not found at {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"seed template {name!r}: top-level must be a mapping")
    missing = [
        k
        for k in ("version", "display_name", "system_prompt", "tools", "policies", "agent")
        if k not in raw
    ]
    if missing:
        raise ValueError(f"seed template {name!r}: missing keys {missing}")
    tools_block = raw["tools"]
    if not isinstance(tools_block, dict) or "required" not in tools_block:
        raise ValueError(f"seed template {name!r}: tools.required must be a list")
    required = tools_block["required"]
    if not isinstance(required, list) or not all(isinstance(t, str) for t in required):
        raise ValueError(f"seed template {name!r}: tools.required must be list[str]")
    agent = raw["agent"]
    return SeedTemplate(
        name=name,
        version=str(raw["version"]),
        display_name=str(raw["display_name"]),
        system_prompt=str(raw["system_prompt"]),
        tools_required=list(required),
        policies_default=dict(raw["policies"]),
        agent_defaults={
            "name": str(agent.get("name_default", "Alex")),
            "tone": str(agent.get("tone_default", "casual")),
            "language": str(agent.get("language_default", "es")),
        },
        raw=raw,
    )


def render_seed_template(
    template: SeedTemplate,
    *,
    placeholders: dict[str, Any],
) -> RenderedSeedTemplate:
    """Resolve every ``{a.b.c}`` token in ``template.system_prompt``.

    Lookup order for each token:
      1. Exact match in ``placeholders`` (key = dotted path).
      2. Default in ``template.agent_defaults`` (for ``agent.*``).
      3. Default in ``template.policies_default`` (for ``policies.*``).
      4. Raise ``SeedTemplatePlaceholderMissing``.

    Returns a ``RenderedSeedTemplate`` with the resolved prompt + the
    template's recommended tools + the merged policies (defaults +
    overrides from ``placeholders``).
    """

    def _resolve(key: str) -> str:
        if key in placeholders:
            return str(placeholders[key])
        if key.startswith("agent."):
            sub = key.removeprefix("agent.")
            if sub in template.agent_defaults:
                return template.agent_defaults[sub]
        if key.startswith("policies."):
            value = _walk(template.policies_default, key.removeprefix("policies.").split("."))
            if value is not None:
                return str(value)
        raise SeedTemplatePlaceholderMissing(key)

    def _walk(node: Any, parts: list[str]) -> Any:
        for p in parts:
            if not isinstance(node, dict) or p not in node:
                return None
            node = node[p]
        return node

    rendered = _PLACEHOLDER_RE.sub(lambda m: _resolve(m.group(1)), template.system_prompt)

    # Merge policies: start from defaults, then apply any caller override
    # under ``policies.*`` keys (e.g. {"policies.no_show.fee_pct": 75}).
    merged_policies = _deep_copy(template.policies_default)
    for key, value in placeholders.items():
        if not key.startswith("policies."):
            continue
        parts = key.removeprefix("policies.").split(".")
        _set_nested(merged_policies, parts, value)

    return RenderedSeedTemplate(
        seed_template_ref=template.name,
        system_prompt=rendered,
        tools=list(template.tools_required),
        policies=merged_policies,
    )


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _deep_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_copy(v) for v in value]
    return value


def _set_nested(node: dict[str, Any], parts: list[str], value: Any) -> None:
    for p in parts[:-1]:
        nxt = node.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            node[p] = nxt
        node = nxt
    node[parts[-1]] = value
