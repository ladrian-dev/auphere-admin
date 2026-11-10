"""A tool whose name says it deletes or creates is never read-only.

The heuristic read ``_LIST_`` anywhere in the name, so
``GOOGLECALENDAR_CALENDAR_LIST_DELETE`` was born read-only when Composio sent no
hints, and under «Solo leer» an agent could use it.
"""

from __future__ import annotations

import pytest

from nexus_api.services.connectors.composio_client import ComposioTool
from nexus_api.services.connectors.service import _derive_annotations, name_says_it_writes


def _tool(slug: str, tags: dict[str, bool] | None = None) -> ComposioTool:
    return ComposioTool(slug=slug, description="d", input_schema={}, raw_tags=tags)


@pytest.mark.parametrize(
    "slug",
    [
        "GOOGLECALENDAR_CALENDAR_LIST_DELETE",
        "GOOGLECALENDAR_CALENDAR_LIST_INSERT",
        "GOOGLECALENDAR_CALENDAR_LIST_PATCH",
        "GOOGLECALENDAR_CALENDAR_LIST_UPDATE",
        "GOOGLEDOCS_FIND_AND_REPLACE_TEXT",
        "WEIRD_GET_OR_CREATE_THING",
        "WEIRD_SEARCH_AND_REMOVE_THING",
    ],
)
def test_the_name_of_what_changes_is_never_read_only(slug: str) -> None:
    assert _derive_annotations(_tool(slug)) == {"read_only": False, "destructive": True}


def test_an_upstream_tag_cannot_make_a_delete_read_only() -> None:
    tool = _tool("WEIRD_TOOLKIT_DELETE_THING", {"readOnlyHint": True})
    assert _derive_annotations(tool) == {"read_only": False, "destructive": True}


@pytest.mark.parametrize(
    "slug",
    [
        "WEIRD_LIST_THINGS",
        "WEIRD_GET_CREATED_THINGS",
        "WEIRD_SEARCH_SENT_MESSAGES",
        "WEIRD_FIND_ADDRESS",
        "WEIRD_READ_UPDATES",
    ],
)
def test_what_only_reads_still_reads(slug: str) -> None:
    assert _derive_annotations(_tool(slug)) == {"read_only": True, "destructive": False}


def test_an_upstream_tag_still_decides_a_name_that_says_nothing() -> None:
    assert _derive_annotations(_tool("WEIRD_DO_THING", {"readOnlyHint": True}))["read_only"] is True


def test_the_console_asks_the_same_question() -> None:
    assert name_says_it_writes("GOOGLECALENDAR_CALENDAR_LIST_DELETE") is True
    assert name_says_it_writes("tienda_test.create_order") is True
    assert name_says_it_writes("tienda_test.list_items") is False
