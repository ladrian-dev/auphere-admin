"""WooCommerce-specific seed checks.

The connector lands in the catalog with the api_key auth_kind variant
that stores Consumer Key + Secret in tenant_credentials (Fernet) and
the store URL in credentials_ref.endpoint_meta. These tests pin those
invariants so a future seed edit can't quietly break the runtime
contract the tools rely on.
"""

from __future__ import annotations

import pytest

from nexus_api.services.connectors.seed_loader import load_seed


@pytest.fixture(scope="module")
def woo_seed():
    return load_seed("woocommerce")


def test_woocommerce_seed_basic_metadata(woo_seed) -> None:
    assert woo_seed.slug == "woocommerce"
    assert woo_seed.display_name == "WooCommerce"
    assert woo_seed.vendor == "Automattic"
    assert woo_seed.category == "ecommerce"
    assert set(woo_seed.capabilities) == {"read", "write"}
    # Beta until validated against a real client store. Bump to
    # "available" in a follow-up release.
    assert woo_seed.status == "beta"


def test_woocommerce_seed_uses_api_key_auth(woo_seed) -> None:
    assert woo_seed.auth_kind == "api_key"
    # Internal MCP server, not Composio.
    assert woo_seed.mcp_server_ref == "internal:woocommerce"
    # No client-side consent template — operator-driven setup.
    assert woo_seed.consent_link_template_name is None


def test_woocommerce_seed_conservative_destructive_flag(woo_seed) -> None:
    """Destructive tools must start blocked. The operator opts in per
    tenant via tenant_connector_tool_overrides once the read-only
    surface has been validated against the live store."""
    assert woo_seed.auto_enable_on_connect is True
    assert woo_seed.auto_enable_destructive is False


def test_woocommerce_seed_advertises_credentials_form(woo_seed) -> None:
    """The admin wizard renders the form from provider_meta.credentials_form.
    Tests pin the field names + secret flags so a UI change can't drift
    silently from the schema the tools expect."""
    form = woo_seed.provider_meta.get("credentials_form")
    assert isinstance(form, list)
    by_field = {f["field"]: f for f in form}
    assert set(by_field) == {"store_url", "consumer_key", "consumer_secret"}
    assert by_field["store_url"]["secret"] is False
    assert by_field["consumer_key"]["secret"] is True
    assert by_field["consumer_secret"]["secret"] is True
    for f in form:
        assert f["required"] is True


def test_woocommerce_seed_icon_is_https(woo_seed) -> None:
    """The shared seed loader enforces this globally, but pin it here
    too so the WooCommerce-specific URL is locked down."""
    assert woo_seed.provider_meta["icon_url"].startswith("https://")
