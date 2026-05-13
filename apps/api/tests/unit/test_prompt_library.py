"""Block Q — tests for the prompt library loader + endpoint."""

from __future__ import annotations

import pytest

from nexus_api.services.prompt_library import (
    PromptSnippet,
    list_snippets,
    load_all_snippets,
)
from nexus_api.services.prompt_library.loader import VALID_CATEGORIES

_async = pytest.mark.asyncio


# ── Loader ────────────────────────────────────────────────────────────────


def test_loader_returns_at_least_the_seeded_snippets() -> None:
    """We ship 8 snippets in Phase 1. The count can grow but never
    shrink without a deliberate decision; treat the YAML directory as
    the source of truth."""
    snippets = load_all_snippets()
    assert len(snippets) >= 8


def test_every_snippet_has_a_valid_category() -> None:
    for s in load_all_snippets():
        assert s.category in VALID_CATEGORIES, f"snippet {s.id!r} has category {s.category!r}"


def test_snippet_ids_are_unique() -> None:
    """Duplicate ids would let the operator collide on insertion. The
    loader enforces uniqueness at import; this test confirms the
    invariant by reading the cached result."""
    ids = [s.id for s in load_all_snippets()]
    assert len(ids) == len(set(ids))


def test_applies_to_when_no_vertical_filter() -> None:
    snippet = PromptSnippet(
        id="x",
        title="x",
        category="tone",
        body="x",
        description="",
        verticals=("barbershop_v1",),
    )
    assert snippet.applies_to(None) is True


def test_applies_to_when_snippet_is_universal() -> None:
    """An empty ``verticals`` (or explicit ``["generic"]``) means the
    snippet is universal — matches any vertical filter."""
    universal = PromptSnippet(
        id="x", title="x", category="tone", body="x", description="", verticals=()
    )
    assert universal.applies_to("barbershop_v1") is True
    assert universal.applies_to("clinica_v1") is True

    generic = PromptSnippet(
        id="y",
        title="y",
        category="tone",
        body="x",
        description="",
        verticals=("generic",),
    )
    assert generic.applies_to("anything") is True


def test_applies_to_filters_by_vertical_list() -> None:
    snippet = PromptSnippet(
        id="x",
        title="x",
        category="tone",
        body="x",
        description="",
        verticals=("barbershop_v1", "restaurante_v1"),
    )
    assert snippet.applies_to("barbershop_v1") is True
    assert snippet.applies_to("clinica_v1") is False


def test_list_snippets_filters_by_category() -> None:
    tone_only = list_snippets(category="tone")
    assert tone_only
    assert all(s.category == "tone" for s in tone_only)


def test_list_snippets_filters_by_vertical_includes_universal() -> None:
    clinic = list_snippets(vertical="clinica_v1")
    ids = {s.id for s in clinic}
    # Universal snippets must be present.
    assert "escalate_when_unsure" in ids
    assert "handle_ambiguous_date" in ids
    # Vertical-specific snippets present.
    assert "tone_clinical_professional" in ids
    # Barbershop-only tone snippet must NOT be present (it doesn't
    # include clinica_v1 in its verticals list).
    assert "tone_warm_casual" not in ids


# ── Endpoint ──────────────────────────────────────────────────────────────


@_async
async def test_endpoint_returns_all_snippets_unfiltered(client, admin_headers) -> None:
    r = await client.get("/admin/prompt-library", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) >= 8
    # Shape check.
    sample = body[0]
    for key in ("id", "title", "category", "description", "body", "verticals", "tags"):
        assert key in sample


@_async
async def test_endpoint_filters_by_vertical(client, admin_headers) -> None:
    r = await client.get("/admin/prompt-library?vertical=clinica_v1", headers=admin_headers)
    assert r.status_code == 200
    ids = {s["id"] for s in r.json()}
    assert "tone_clinical_professional" in ids
    assert "tone_warm_casual" not in ids


@_async
async def test_endpoint_filters_by_category(client, admin_headers) -> None:
    r = await client.get("/admin/prompt-library?category=tone", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert all(s["category"] == "tone" for s in body)


@_async
async def test_endpoint_requires_auth(client) -> None:
    r = await client.get("/admin/prompt-library")
    assert r.status_code == 401
