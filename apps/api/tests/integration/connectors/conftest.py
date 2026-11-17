"""Fixtures for connector integration tests.

Each test runs against a fresh DB (truncate at top of conftest), so we
re-seed the connector catalog from the YAML files before every test.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin import connectors as admin_connectors
from nexus_api.db.models import Connector, ToolCatalog
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
    dynamically. Only the custom seeds (``whatsapp_meta``, ``woocommerce``, ``amigable_*``…) are
    applied from local YAMLs.
    """
    seeds = load_all_seeds()
    await apply_seeds(db_session, seeds)


#: Las filas de ``tool_catalog`` de Quédate tal como quedan tras las migraciones:
#: la 0233 las crea y la 0234 y la 0235 cambian descripciones y esquemas.
_ALEMBIC_DATA = Path(__file__).parents[3] / "alembic" / "data"
_QUEDATE_SNAPSHOTS = (
    "0233_quedate_tools.json",
    "0234_quedate_tool_descriptions.json",
    "0235_quedate_listing_catalog_ids.json",
)


def quedate_tools() -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    for snapshot in _QUEDATE_SNAPSHOTS:
        for name, spec in json.loads((_ALEMBIC_DATA / snapshot).read_text("utf-8")).items():
            catalog[name] = {**catalog.get(name, {}), **spec}
    return catalog


@pytest_asyncio.fixture
async def quedate_catalog(db_session: AsyncSession, seeded_catalog: None) -> None:
    """Las 27 herramientas de Quédate, enlazadas a su conector.

    Las crea la migración con ``connector_id``, y la limpieza de ``db_session``
    borra después de cada prueba toda fila con ``connector_id`` y todos los
    conectores. Sin este fixture solo existen en la primera prueba de la sesión: así
    falló la del constructor en la tubería del 2026-11-17, sola en verde.
    """
    connector_id = await db_session.scalar(
        sa.select(Connector.id).where(Connector.slug == "quedate")
    )
    assert connector_id is not None, "el seed de quedate no está aplicado"
    rows = [
        {
            "name": name,
            "description": spec["description"],
            "mcp_server": "quedate-server",
            "input_schema": spec["input_schema"],
            "output_schema": spec["output_schema"],
            "side_effects": list(spec["side_effects"]),
            "capability_tags": ["quedate", "read" if spec["read_only"] else "write"],
            "cost_estimate": {},
            "connector_id": connector_id,
            "read_only": bool(spec["read_only"]),
            "destructive": False,
            "requires_consent": True,
            "default_mode": "always",
        }
        for name, spec in quedate_tools().items()
    ]
    stmt = insert(ToolCatalog).values(rows)
    await db_session.execute(
        stmt.on_conflict_do_update(
            index_elements=[ToolCatalog.name],
            set_={"connector_id": stmt.excluded.connector_id},
        )
    )
    await db_session.commit()


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
