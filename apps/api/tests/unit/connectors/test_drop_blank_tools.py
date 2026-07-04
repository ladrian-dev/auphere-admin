"""Regression: a Composio tool with a blank slug must be dropped before sync.

``tool_catalog.name`` is derived from the slug, so a blank slug inserts
``name=''`` and violates ``tool_catalog_name_key`` — the IntegrityError
aborted the whole tools sync and spammed ``connector_reconcile.tick_failed``
every tick (googlecalendar on a real tenant did exactly this).
"""

from __future__ import annotations

import pytest

from nexus_api.services.connectors.composio_client import ComposioTool
from nexus_api.services.connectors.service import _drop_blank_tools

pytestmark = [pytest.mark.unit]


def _tool(slug: str) -> ComposioTool:
    return ComposioTool(slug=slug, description="x", input_schema={})


def test_drops_blank_and_whitespace_slugs() -> None:
    tools = [
        _tool("GOOGLECALENDAR_LIST_EVENTS"),
        _tool(""),  # the offender
        _tool("   "),  # whitespace-only
        _tool("GOOGLECALENDAR_CREATE_EVENT"),
    ]
    kept = _drop_blank_tools(tools, connector_slug="googlecalendar")
    assert [t.slug for t in kept] == [
        "GOOGLECALENDAR_LIST_EVENTS",
        "GOOGLECALENDAR_CREATE_EVENT",
    ]


def test_keeps_all_when_none_blank() -> None:
    tools = [_tool("A"), _tool("B")]
    assert _drop_blank_tools(tools, connector_slug="x") == tools


def test_empty_input() -> None:
    assert _drop_blank_tools([], connector_slug="x") == []
