"""Admin catalog endpoints — list + detail.

The catalog merges custom seeds (whatsapp_ycloud, agendapro) with the
dynamic auth_configs that Composio surfaces. The ``fake_composio`` fixture
pre-registers googlecalendar / calendly / notion in the fake Composio
project, so the catalog should expose 5 entries total.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_list_catalog_merges_seeds_and_composio(
    client, admin_headers, seeded_catalog, fake_composio
) -> None:
    r = await client.get("/admin/connectors", headers=admin_headers)
    assert r.status_code == 200
    slugs = {c["slug"] for c in r.json()}
    assert slugs == {
        "agendapro",
        "calendly",
        "googlecalendar",
        "notion",
        "whatsapp_ycloud",
    }


async def test_list_catalog_without_composio_falls_back_to_seeds(
    client, admin_headers, seeded_catalog, fake_composio
) -> None:
    """If Composio is unreachable, the catalog degrades to custom seeds only."""
    fake_composio.simulate_unavailable = True
    try:
        r = await client.get("/admin/connectors", headers=admin_headers)
        assert r.status_code == 200
        slugs = {c["slug"] for c in r.json()}
        assert slugs == {"agendapro", "whatsapp_ycloud"}
    finally:
        fake_composio.simulate_unavailable = False


async def test_list_catalog_filter_category(
    client, admin_headers, seeded_catalog, fake_composio
) -> None:
    r = await client.get("/admin/connectors?category=calendar", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert {c["slug"] for c in body} == {"googlecalendar"}


async def test_get_catalog_entry(
    client, admin_headers, seeded_catalog, fake_composio
) -> None:
    r = await client.get("/admin/connectors/googlecalendar", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "googlecalendar"
    assert body["auth_kind"] == "oauth_composio"
    assert body["mcp_server_ref"] == "composio:googlecalendar"
    assert body["auto_enable_destructive"] is False
    # Dynamic entries don't have a DB id until lazy upsert.
    assert body["id"] is None


async def test_get_catalog_entry_seed(
    client, admin_headers, seeded_catalog, fake_composio
) -> None:
    """Custom seeds keep their persisted ``id`` since they're seeded at deploy."""
    r = await client.get("/admin/connectors/agendapro", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "agendapro"
    assert body["auth_kind"] == "browser_credentials"
    assert body["id"] is not None


async def test_get_catalog_entry_unknown(
    client, admin_headers, seeded_catalog, fake_composio
) -> None:
    r = await client.get("/admin/connectors/no-such-thing", headers=admin_headers)
    assert r.status_code == 404


async def test_catalog_requires_auth(client, seeded_catalog) -> None:
    r = await client.get("/admin/connectors")
    assert r.status_code in {401, 403}
