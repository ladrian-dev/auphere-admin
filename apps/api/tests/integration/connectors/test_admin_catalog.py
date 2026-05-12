"""Admin catalog endpoints — list + detail."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_list_catalog_returns_5(client, admin_headers, seeded_catalog) -> None:
    r = await client.get("/admin/connectors", headers=admin_headers)
    assert r.status_code == 200
    slugs = {c["slug"] for c in r.json()}
    assert slugs == {
        "agendapro",
        "calendly",
        "google_calendar",
        "notion",
        "whatsapp_ycloud",
    }


async def test_list_catalog_filter_category(client, admin_headers, seeded_catalog) -> None:
    r = await client.get("/admin/connectors?category=calendar", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert {c["slug"] for c in body} == {"google_calendar"}


async def test_get_catalog_entry(client, admin_headers, seeded_catalog) -> None:
    r = await client.get("/admin/connectors/google_calendar", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "google_calendar"
    assert body["auth_kind"] == "oauth_composio"
    assert body["mcp_server_ref"] == "composio:googlecalendar"
    assert body["auto_enable_destructive"] is False


async def test_get_catalog_entry_unknown(client, admin_headers, seeded_catalog) -> None:
    r = await client.get("/admin/connectors/no-such-thing", headers=admin_headers)
    assert r.status_code == 404


async def test_catalog_requires_auth(client, seeded_catalog) -> None:
    r = await client.get("/admin/connectors")
    assert r.status_code in {401, 403}
