"""Unit tests for the connector seed YAML loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus_api.services.connectors.seed_loader import (
    ConnectorSeed,
    ConnectorSeedInvalid,
    ConnectorSeedNotFound,
    list_seed_slugs,
    load_all_seeds,
    load_seed,
)


def test_all_seeds_parse() -> None:
    """Local seeds cover only the custom (non-OAuth) integrations now —
    Composio owns the catalog for OAuth toolkits."""
    seeds = load_all_seeds()
    slugs = {s.slug for s in seeds}
    assert slugs == {
        "agendapro",
        "whatsapp_meta",
        "whatsapp_ycloud",
        "woocommerce",
    }


def test_list_seed_slugs_sorted() -> None:
    slugs = list_seed_slugs()
    assert slugs == sorted(slugs)


def test_oauth_composio_requires_consent_template(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "slug: bad\n"
        "display_name: Bad\n"
        "vendor: V\n"
        "category: c\n"
        "auth_kind: oauth_composio\n"
        "mcp_server_ref: composio:bad\n"
        "consent_link_template_name: null\n",
        encoding="utf-8",
    )
    with pytest.raises(ConnectorSeedInvalid, match="consent_link_template_name"):
        load_seed("bad", seeds_dir=tmp_path)


def test_unknown_auth_kind_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "slug: bad\n"
        "display_name: Bad\n"
        "vendor: V\n"
        "category: c\n"
        "auth_kind: laser_beam\n"
        "mcp_server_ref: internal:bad\n",
        encoding="utf-8",
    )
    with pytest.raises(ConnectorSeedInvalid):
        load_seed("bad", seeds_dir=tmp_path)


def test_filename_and_slug_must_match(tmp_path: Path) -> None:
    bad = tmp_path / "googlecalendar.yaml"
    bad.write_text(
        "slug: google_calendar\n"
        "display_name: GC\n"
        "vendor: G\n"
        "category: calendar\n"
        "auth_kind: oauth_composio\n"
        "mcp_server_ref: composio:googlecalendar\n"
        "consent_link_template_name: x\n",
        encoding="utf-8",
    )
    with pytest.raises(ConnectorSeedInvalid, match="mismatch"):
        load_seed("googlecalendar", seeds_dir=tmp_path)


def test_file_not_found_raises() -> None:
    with pytest.raises(ConnectorSeedNotFound):
        load_seed("__never_exists__")


def test_oauth_mcp_server_ref_prefix(tmp_path: Path) -> None:
    bad = tmp_path / "x.yaml"
    bad.write_text(
        "slug: x\n"
        "display_name: X\n"
        "vendor: V\n"
        "category: c\n"
        "auth_kind: oauth_composio\n"
        "mcp_server_ref: internal:wrong\n"
        "consent_link_template_name: t\n",
        encoding="utf-8",
    )
    with pytest.raises(ConnectorSeedInvalid, match="composio:"):
        load_seed("x", seeds_dir=tmp_path)


def test_icon_url_must_be_https(tmp_path: Path) -> None:
    bad = tmp_path / "x.yaml"
    bad.write_text(
        "slug: x\n"
        "display_name: X\n"
        "vendor: V\n"
        "category: c\n"
        "auth_kind: webhook_manual\n"
        "mcp_server_ref: internal:x\n"
        "provider_meta:\n"
        "  icon_url: http://insecure/icon.png\n",
        encoding="utf-8",
    )
    with pytest.raises(ConnectorSeedInvalid, match="https"):
        load_seed("x", seeds_dir=tmp_path)


def test_auto_enable_destructive_requires_auto_enable(tmp_path: Path) -> None:
    bad = tmp_path / "x.yaml"
    bad.write_text(
        "slug: x\n"
        "display_name: X\n"
        "vendor: V\n"
        "category: c\n"
        "auth_kind: webhook_manual\n"
        "mcp_server_ref: internal:x\n"
        "auto_enable_on_connect: false\n"
        "auto_enable_destructive: true\n",
        encoding="utf-8",
    )
    with pytest.raises(ConnectorSeedInvalid, match="auto_enable_destructive"):
        load_seed("x", seeds_dir=tmp_path)


def test_seed_model_is_frozen() -> None:
    """Pydantic frozen model raises ValidationError on attribute assignment."""
    from pydantic import ValidationError

    s = load_seed("agendapro")
    assert isinstance(s, ConnectorSeed)
    with pytest.raises(ValidationError):
        s.slug = "mutated"  # type: ignore[misc]
