"""Block Q — Prompt Library.

Curated snippets the operator inserts into a draft prompt while
iterating. Loaded once at import time from YAML files in
``snippets/``. Cada snippet declara qué verticales aplica, qué
categoría tiene y un body con placeholders Auphere-style
(``{policies.cancellation.free_hours_before}``).

Phase 1 ships ~8-10 snippets. New patterns drop a YAML in the
snippets dir — no code change.
"""

from __future__ import annotations

from nexus_api.services.prompt_library.loader import (
    PromptSnippet,
    SnippetLoadError,
    list_snippets,
    load_all_snippets,
)

__all__ = [
    "PromptSnippet",
    "SnippetLoadError",
    "list_snippets",
    "load_all_snippets",
]
