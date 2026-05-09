"""Load Meta-approved WhatsApp template definitions from YAML.

Phase 1: templates live on disk under
``apps/channels/src/nexus_channels/whatsapp_ycloud/templates/<tenant_slug>/``.
The owner creates the templates manually in the YCloud dashboard (with a
Meta approval lead time of 24-72h); these YAML files exist so:

1. The agent code knows which templates are safe to call (the loader
   validates ``template_name`` exists before send).
2. The repo is the source-of-truth for the template name + body + parameter
   list — re-creating the templates after a tenant migration is mechanical.
3. Tests can build a faithful payload without hitting YCloud.

Phase 4+ may add a sync job that pushes YAML changes to YCloud via API,
but that requires admin credentials we don't have wired today.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import yaml

TemplateCategory = Literal["UTILITY", "MARKETING", "AUTHENTICATION"]


@dataclass(frozen=True)
class TemplateDefinition:
    """Frozen snapshot of an approved Meta template.

    ``params`` lists positional placeholders. The body uses ``{{1}}``,
    ``{{2}}`` etc. — same convention Meta enforces. ``params`` lets the
    template loader validate the dict passed at send time has all keys.
    """

    name: str
    language: str
    category: TemplateCategory
    body: str
    params: list[str]
    tenant_slug: str | None = None


TEMPLATES_ROOT = Path(__file__).parent / "templates"


def load_template(
    name: str, *, tenant_slug: str | None = None, root: Path | None = None
) -> TemplateDefinition:
    """Look up a template by name. Searches the tenant directory first,
    then a ``shared/`` folder if present.

    Raises :class:`KeyError` if not found — call sites should treat that as
    a hard programming error (the agent tried to send a template the tenant
    has not got approved).
    """
    base = root or TEMPLATES_ROOT
    candidates: list[Path] = []
    if tenant_slug is not None:
        candidates.append(base / tenant_slug / f"{name}.yaml")
    candidates.append(base / "shared" / f"{name}.yaml")
    for path in candidates:
        if path.exists():
            return _load_yaml(path, tenant_slug=tenant_slug)
    raise KeyError(
        f"template {name!r} not found for tenant {tenant_slug!r} "
        f"(searched: {[str(c) for c in candidates]})"
    )


def list_templates(
    *, tenant_slug: str | None = None, root: Path | None = None
) -> list[TemplateDefinition]:
    """Return every template the tenant has on disk (tenant + shared)."""
    base = root or TEMPLATES_ROOT
    out: list[TemplateDefinition] = []
    seen: set[str] = set()
    dirs: list[Path] = []
    if tenant_slug is not None:
        dirs.append(base / tenant_slug)
    dirs.append(base / "shared")
    for d in dirs:
        if not d.exists():
            continue
        for path in sorted(d.glob("*.yaml")):
            tpl = _load_yaml(path, tenant_slug=tenant_slug)
            if tpl.name in seen:
                continue
            seen.add(tpl.name)
            out.append(tpl)
    return out


def render_body_params(definition: TemplateDefinition, values: dict[str, Any]) -> list[str]:
    """Validate that every declared param has a value, and return them in
    declaration order so the YCloud client can stuff them into ``components``.
    """
    missing = [p for p in definition.params if p not in values]
    if missing:
        raise KeyError(
            f"template {definition.name!r} missing params: {missing} "
            f"(provided keys: {sorted(values)})"
        )
    return [str(values[p]) for p in definition.params]


def _load_yaml(path: Path, *, tenant_slug: str | None) -> TemplateDefinition:
    raw_data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw_data, dict):
        raise ValueError(f"{path}: expected mapping at the top level")
    raw = cast(dict[str, Any], raw_data)
    name = raw.get("name")
    language = raw.get("language")
    category = raw.get("category")
    body = raw.get("body")
    raw_params = raw.get("params") or []
    if not isinstance(name, str) or not name:
        raise ValueError(f"{path}: missing/invalid 'name'")
    if not isinstance(language, str) or not language:
        raise ValueError(f"{path}: missing/invalid 'language'")
    if category not in {"UTILITY", "MARKETING", "AUTHENTICATION"}:
        raise ValueError(f"{path}: 'category' must be UTILITY/MARKETING/AUTHENTICATION")
    if not isinstance(body, str) or not body:
        raise ValueError(f"{path}: missing/invalid 'body'")
    if not isinstance(raw_params, list):
        raise ValueError(f"{path}: 'params' must be a list")
    params = [str(p) for p in raw_params]
    return TemplateDefinition(
        name=name,
        language=language,
        category=cast(TemplateCategory, category),
        body=body,
        params=params,
        tenant_slug=tenant_slug,
    )
