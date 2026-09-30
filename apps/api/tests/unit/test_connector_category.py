"""Spec 023 (Requisito 1.1): Stripe is «Cobros», Calendly «Citas», HubSpot
«Clientes», whatever label the provider publishes — and the next payments
or store toolkit no longer falls into «otros».
"""

from __future__ import annotations

import pytest

from nexus_api.services.connectors.catalog import _project_dynamic, _resolve_category
from nexus_api.services.connectors.composio_client import AuthConfigSummary, ToolkitMetadata


def _ac(slug: str, category: str | None) -> AuthConfigSummary:
    return AuthConfigSummary(
        auth_config_id=f"ac_{slug}",
        toolkit_slug=slug,
        display_name=f"{slug}-abc123",
        auth_scheme="OAUTH2",
        category=category,
    )


def _md(slug: str, category_slug: str | None) -> ToolkitMetadata:
    return ToolkitMetadata(
        slug=slug,
        name=slug.title(),
        description="",
        logo=None,
        category_slug=category_slug,
        category_name=None,
    )


@pytest.mark.parametrize(
    "slug,expected",
    [("stripe", "billing"), ("calendly", "booking"), ("hubspot", "crm")],
)
@pytest.mark.parametrize("published", [None, "other", "developer-tools", "Productivity"])
def test_the_three_toolkits_land_where_the_partner_expects(
    slug: str, expected: str, published: str | None
) -> None:
    assert _project_dynamic(_ac(slug, published), _md(slug, published)).category == expected
    assert _project_dynamic(_ac(slug, published), None).category == expected


def test_toolkits_without_a_fixed_category_still_follow_the_provider() -> None:
    assert _project_dynamic(_ac("notion", "Productivity"), None).category == "docs"
    assert _project_dynamic(_ac("weirdtool", None), _md("weirdtool", "scheduling")).category == (
        "booking"
    )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("payments", "billing"),
        ("Payments & Finance", "billing"),
        ("invoicing", "billing"),
        ("e-commerce", "ecommerce"),
        ("commerce-platforms", "ecommerce"),
        ("online-store", "ecommerce"),
        ("crm", "crm"),
        ("developer-tools", "otros"),
        (None, "otros"),
    ],
)
def test_payments_and_commerce_no_longer_fall_into_otros(raw: str | None, expected: str) -> None:
    assert _resolve_category(raw) == expected
