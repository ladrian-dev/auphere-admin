"""Snippet loader — same convention as ``seed_templates`` (YAML files
in a sibling directory parsed once and cached for the process
lifetime).

Snippet schema:

::

    id: handle_late_cancellation
    title: "Cancelación tardía con cargo"
    verticals: [barbershop_v1, clinica_v1, restaurante_v1]
    # ``["generic"]`` (or omitted) means "any vertical".
    category: edge_case
    tags: [cancellation, fee, policy]
    description: |
      What the snippet is for, when to use it.
    body: |
      The text the operator pastes. Placeholders are
      ``{policies.cancellation.free_hours_before}`` style — the
      operator fills them by hand (the seed render pipeline never
      runs over snippets).

Categories are validated against :data:`VALID_CATEGORIES`. Anything
else makes load fail loudly — typos in the YAML must never reach
the API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import yaml

_SNIPPETS_DIR: Final[Path] = Path(__file__).resolve().parent / "snippets"


VALID_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        "tone",
        "edge_case",
        "escalation",
        "output_format",
        "tool_calling",
        "policy",
    }
)


class SnippetLoadError(Exception):
    """Raised at module import time when a snippet YAML is malformed.

    Failing loud at startup is intentional — a typoed snippet must
    NEVER surface in the API.
    """


@dataclass(frozen=True)
class PromptSnippet:
    id: str
    title: str
    category: str
    body: str
    description: str
    verticals: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    def applies_to(self, vertical: str | None) -> bool:
        """Match policy:

        - No filter requested (``vertical is None``) → snippet matches.
        - Snippet has no ``verticals`` declared, or contains ``"generic"``
          → matches any vertical.
        - Otherwise → matches when ``vertical`` is in the list.
        """
        if vertical is None:
            return True
        if not self.verticals or "generic" in self.verticals:
            return True
        return vertical in self.verticals


def _parse_one(path: Path, raw: dict[str, Any]) -> PromptSnippet:
    try:
        snippet_id = str(raw["id"]).strip()
        title = str(raw["title"]).strip()
        category = str(raw["category"]).strip()
        body = str(raw["body"]).rstrip()
    except KeyError as exc:
        raise SnippetLoadError(f"{path.name}: missing required key {exc.args[0]!r}") from exc
    if not snippet_id:
        raise SnippetLoadError(f"{path.name}: id must be non-empty")
    if category not in VALID_CATEGORIES:
        raise SnippetLoadError(
            f"{path.name}: category {category!r} not in {sorted(VALID_CATEGORIES)}"
        )
    if not body:
        raise SnippetLoadError(f"{path.name}: body must be non-empty")

    verticals_raw = raw.get("verticals", []) or []
    if not isinstance(verticals_raw, list) or not all(isinstance(v, str) for v in verticals_raw):
        raise SnippetLoadError(f"{path.name}: verticals must be a list of strings")

    tags_raw = raw.get("tags", []) or []
    if not isinstance(tags_raw, list) or not all(isinstance(t, str) for t in tags_raw):
        raise SnippetLoadError(f"{path.name}: tags must be a list of strings")

    return PromptSnippet(
        id=snippet_id,
        title=title,
        category=category,
        body=body,
        description=str(raw.get("description") or "").strip(),
        verticals=tuple(verticals_raw),
        tags=tuple(tags_raw),
    )


@lru_cache(maxsize=1)
def load_all_snippets() -> tuple[PromptSnippet, ...]:
    """Parse every ``*.yaml`` in the snippets directory.

    Cached for the process lifetime — snippet curation happens via
    redeploy, not hot-reload. The cache also guards against duplicate
    ``id`` declarations across files (raises at first import).
    """
    if not _SNIPPETS_DIR.exists():
        return ()

    snippets: list[PromptSnippet] = []
    seen_ids: set[str] = set()
    for path in sorted(_SNIPPETS_DIR.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise SnippetLoadError(f"{path.name}: invalid YAML — {exc}") from exc
        if not isinstance(raw, dict):
            raise SnippetLoadError(f"{path.name}: top level must be a mapping")
        snippet = _parse_one(path, raw)
        if snippet.id in seen_ids:
            raise SnippetLoadError(
                f"{path.name}: duplicate snippet id {snippet.id!r} (already declared)"
            )
        seen_ids.add(snippet.id)
        snippets.append(snippet)
    return tuple(snippets)


def list_snippets(
    *,
    vertical: str | None = None,
    category: str | None = None,
) -> list[PromptSnippet]:
    """Return all loaded snippets, filtered.

    ``vertical`` matches per :meth:`PromptSnippet.applies_to`.
    ``category`` is an exact-string match when given.
    """
    out: list[PromptSnippet] = []
    for s in load_all_snippets():
        if not s.applies_to(vertical):
            continue
        if category is not None and s.category != category:
            continue
        out.append(s)
    return out


# Re-export for backwards compatibility / convenience.
_ = field  # silence unused import when dataclass field defaults change
