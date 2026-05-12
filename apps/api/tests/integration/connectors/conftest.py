"""Fixtures for connector integration tests.

Each test runs against a fresh DB (truncate at top of conftest), so we
re-seed the connector catalog from the YAML files before every test.
"""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin import connectors as admin_connectors
from nexus_api.services.connectors.composio_client import (
    ComposioTool,
    FakeComposioClient,
)
from nexus_api.services.connectors.seed_loader import load_all_seeds
from nexus_api.services.connectors.seed_runner import apply_seeds


@pytest_asyncio.fixture
async def seeded_catalog(db_session: AsyncSession) -> None:
    """Apply the 5 connector seed YAMLs to the test DB."""
    seeds = load_all_seeds()
    await apply_seeds(db_session, seeds)


@pytest_asyncio.fixture
async def fake_composio() -> FakeComposioClient:
    """Fake Composio client wired into the admin DI singleton.

    Pre-registers GOOGLECALENDAR / CALENDLY / NOTION sample tools so tests
    that drive ``initiate_consent → webhook → sync`` see a non-empty
    tools/list response. Test cleanup resets the singleton.
    """
    c = FakeComposioClient()
    c.register_tools(
        "googlecalendar",
        [
            ComposioTool(
                slug="GOOGLECALENDAR_LIST_EVENTS",
                description="List events",
                input_schema={"type": "object"},
            ),
            ComposioTool(
                slug="GOOGLECALENDAR_CREATE_EVENT",
                description="Create event",
                input_schema={"type": "object"},
            ),
        ],
    )
    c.register_tools(
        "calendly",
        [
            ComposioTool(
                slug="CALENDLY_LIST_EVENT_TYPES",
                description="List event types",
                input_schema={"type": "object"},
            ),
        ],
    )
    c.register_tools(
        "notion",
        [
            ComposioTool(
                slug="NOTION_SEARCH",
                description="Search pages",
                input_schema={"type": "object"},
            ),
        ],
    )
    admin_connectors.set_composio_client_for_tests(c)
    yield c
    admin_connectors.set_composio_client_for_tests(None)
