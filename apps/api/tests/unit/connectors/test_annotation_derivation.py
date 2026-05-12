"""Unit tests for the upstream-tool annotation resolution.

These tests pin the conservative defaults: unknown destructive intent goes
to ``destructive=True``, well-known read patterns (LIST/GET/FIND/SEARCH/READ)
become ``read_only=True``, and explicit MCP tags win over both.
"""

from __future__ import annotations

import pytest

from nexus_api.services.connectors.composio_client import ComposioTool
from nexus_api.services.connectors.service import (
    _default_mode_for,
    _derive_annotations,
)


def test_known_slug_read_only() -> None:
    t = ComposioTool(
        slug="GOOGLECALENDAR_LIST_EVENTS",
        description="d",
        input_schema={},
    )
    assert _derive_annotations(t) == {"read_only": True, "destructive": False}


def test_known_slug_destructive() -> None:
    t = ComposioTool(
        slug="GOOGLECALENDAR_CREATE_EVENT",
        description="d",
        input_schema={},
    )
    assert _derive_annotations(t) == {"read_only": False, "destructive": True}


def test_unknown_slug_with_list_prefix_is_read_only() -> None:
    t = ComposioTool(
        slug="WEIRD_TOOLKIT_LIST_SOMETHING",
        description="d",
        input_schema={},
    )
    assert _derive_annotations(t) == {"read_only": True, "destructive": False}


def test_unknown_slug_default_destructive() -> None:
    """Conservative fallback: if we can't tell, assume destructive."""
    t = ComposioTool(slug="WEIRD_TOOLKIT_DO_THING", description="d", input_schema={})
    assert _derive_annotations(t) == {"read_only": False, "destructive": True}


def test_upstream_tags_win() -> None:
    """If Composio surfaces readOnlyHint, we honour it even if the slug
    pattern would say otherwise."""
    t = ComposioTool(
        slug="LOOKS_DESTRUCTIVE_BUT_ISNT",
        description="d",
        input_schema={},
        raw_tags={"readOnlyHint": True},
    )
    assert _derive_annotations(t) == {"read_only": True, "destructive": False}


@pytest.mark.parametrize(
    "read_only,destructive,auto_d,expected",
    [
        (True, False, False, "always"),
        (False, False, False, "always"),
        (False, True, False, "blocked"),
        (False, True, True, "always"),
        (True, True, False, "always"),  # read_only takes precedence
    ],
)
def test_default_mode_table(
    read_only: bool,
    destructive: bool,
    auto_d: bool,
    expected: str,
) -> None:
    assert (
        _default_mode_for(
            read_only=read_only,
            destructive=destructive,
            auto_enable_destructive=auto_d,
        )
        == expected
    )
