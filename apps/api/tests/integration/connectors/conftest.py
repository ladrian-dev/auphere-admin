"""Fixtures for connector integration tests.

Each test runs against a fresh DB (truncate at top of conftest), so we
re-seed the connector catalog from the YAML files before every test.
"""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin import connectors as admin_connectors
from nexus_api.services.connectors import catalog as connector_catalog
from nexus_api.services.connectors.composio_client import (
    ComposioTool,
    FakeComposioClient,
)
from nexus_api.services.connectors.seed_loader import load_all_seeds
from nexus_api.services.connectors.seed_runner import apply_seeds


@pytest_asyncio.fixture
async def seeded_catalog(db_session: AsyncSession) -> None:
    """Apply the custom (non-OAuth) connector seeds to the test DB.

    OAuth connectors live in Composio dashboards now — the ``fake_composio``
    fixture pre-registers them so the catalog endpoint surfaces them
    dynamically. Only the custom seeds (``whatsapp_meta``, ``agendapro``, ``woocommerce``) are applied
    from local YAMLs.
    """
    seeds = load_all_seeds()
    await apply_seeds(db_session, seeds)


@pytest_asyncio.fixture
async def fake_composio() -> FakeComposioClient:
    """Fake Composio client wired into the admin DI singleton.

    Pre-registers:
    - Sample tools for googlecalendar / calendly / notion (so tools.list
      after consent returns non-empty).
    - Stub auth_config_ids per toolkit (so ``find_auth_config_id`` succeeds
      — mirrors the production setup where the operator pre-creates the
      auth_config in Composio dashboard).

    Test cleanup resets the singleton.
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
    c.register_auth_config(
        "googlecalendar",
        "ac_test_gc",
        display_name="Google Calendar",
        vendor="Google",
        category="Calendar",
        icon_url="https://images.composio.dev/v2/icons/googlecalendar.png",
    )
    c.register_auth_config(
        "calendly",
        "ac_test_cl",
        display_name="Calendly",
        vendor="Calendly Inc.",
        category="Scheduling",
    )
    c.register_auth_config(
        "notion",
        "ac_test_n",
        display_name="Notion",
        vendor="Notion Labs",
        category="Productivity",
    )
    admin_connectors.set_composio_client_for_tests(c)
    # The catalog uses a module-level cache for ``toolkits.get(slug)``
    # results. Reset it between tests so registrations don't leak.
    connector_catalog._TOOLKIT_METADATA_CACHE.clear()
    yield c
    admin_connectors.set_composio_client_for_tests(None)
    connector_catalog._TOOLKIT_METADATA_CACHE.clear()
