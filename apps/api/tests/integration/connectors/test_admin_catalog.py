"""Admin catalog endpoints — list + detail.

The catalog merges custom seeds (whatsapp_ycloud, whatsapp_meta,
agendapro, woocommerce) with the dynamic auth_configs that Composio
surfaces. The ``fake_composio`` fixture pre-registers googlecalendar /
calendly / notion in the fake Composio project.
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
        "whatsapp_meta",
        "whatsapp_ycloud",
        "woocommerce",
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
        assert slugs == {
            "agendapro",
            "whatsapp_meta",
            "whatsapp_ycloud",
            "woocommerce",
        }
    finally:
        fake_composio.simulate_unavailable = False


async def test_list_catalog_filter_category(
    client, admin_headers, seeded_catalog, fake_composio
) -> None:
    r = await client.get("/admin/connectors?category=calendar", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert {c["slug"] for c in body} == {"googlecalendar"}


async def test_get_catalog_entry(client, admin_headers, seeded_catalog, fake_composio) -> None:
    r = await client.get("/admin/connectors/googlecalendar", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "googlecalendar"
    assert body["auth_kind"] == "oauth_composio"
    assert body["mcp_server_ref"] == "composio:googlecalendar"
    assert body["auto_enable_destructive"] is False
    # Dynamic entries don't have a DB id until lazy upsert.
    assert body["id"] is None


async def test_get_catalog_entry_seed(client, admin_headers, seeded_catalog, fake_composio) -> None:
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


async def test_catalog_enriches_dynamic_with_toolkit_metadata(
    client, admin_headers, seeded_catalog, fake_composio
) -> None:
    """When Composio publishes canonical toolkit metadata, the catalog
    surfaces the human name + category instead of the auth_config alias
    and 'otros' fallback.
    """
    fake_composio.register_toolkit_metadata(
        "googlecalendar",
        name="Google Calendar",
        description="Schedule meetings, manage events.",
        logo="https://images.composio.dev/v2/icons/googlecalendar.png",
        category_slug="calendar",
        category_name="Calendar",
    )
    r = await client.get("/admin/connectors", headers=admin_headers)
    assert r.status_code == 200
    by_slug = {c["slug"]: c for c in r.json()}
    gcal = by_slug["googlecalendar"]
    assert gcal["display_name"] == "Google Calendar"
    assert gcal["vendor"] == "Google Calendar"
    assert gcal["category"] == "calendar"
    # Toolkit logo wins over the AuthConfigSummary icon as the source.
    assert gcal["provider_meta"]["icon_url"] == (
        "https://images.composio.dev/v2/icons/googlecalendar.png"
    )


async def test_catalog_falls_back_to_slug_title_when_no_metadata(
    client, admin_headers, seeded_catalog, fake_composio
) -> None:
    """If toolkit.get returns None and the auth_config alias looks like
    the SDK default ``<slug>-<random>``, we title-case the slug instead
    of exposing the alias verbatim.
    """
    # The fake doesn't have metadata for googlecalendar in this test;
    # the alias the auth_configs fixture registered is ``googlecalendar``
    # (no random suffix). Hit a slug whose alias DOES look default to
    # confirm the cleanup path.
    fake_composio.register_auth_config(
        "linear",
        "ac_linear",
        display_name="linear-abc123",
        category="Project Management",
    )
    r = await client.get("/admin/connectors", headers=admin_headers)
    assert r.status_code == 200
    by_slug = {c["slug"]: c for c in r.json()}
    assert "linear" in by_slug
    assert by_slug["linear"]["display_name"] == "Linear"
