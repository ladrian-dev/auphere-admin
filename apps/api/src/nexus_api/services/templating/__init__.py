"""Seed-template loading and rendering for agent_config v1 bootstrap.

The KB at ``Auphere/nexus/verticals/<vertical>_v<N>.md`` is the canonical
spec for a vertical. The runtime mirror lives at ``seeds/<name>.yaml`` —
any divergence is a bug. See ``seed_templates.py`` for the loader API.
"""

from nexus_api.services.templating.seed_templates import (
    RenderedSeedTemplate,
    SeedTemplate,
    SeedTemplateNotFound,
    SeedTemplatePlaceholderMissing,
    list_seed_templates,
    load_seed_template,
    render_seed_template,
)

__all__ = [
    "RenderedSeedTemplate",
    "SeedTemplate",
    "SeedTemplateNotFound",
    "SeedTemplatePlaceholderMissing",
    "list_seed_templates",
    "load_seed_template",
    "render_seed_template",
]
