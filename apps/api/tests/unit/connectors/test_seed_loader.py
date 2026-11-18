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
    # Spec 048: no AgendaPro seed, so release.sh cannot bring it back.
    assert slugs == {
        "amigable_cobro",
        "amigable_venta",
        "quedate",
        "tiktok_bm",
        "whatsapp_meta",
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


def _seed_with(tmp_path: Path, provider_meta: str) -> Path:
    path = tmp_path / "x.yaml"
    path.write_text(
        "slug: x\n"
        "display_name: X\n"
        "vendor: V\n"
        "category: c\n"
        "auth_kind: api_key\n"
        "mcp_server_ref: internal:x\n"
        "provider_meta:\n" + provider_meta,
        encoding="utf-8",
    )
    return path


def test_icon_url_may_be_one_of_our_own_logos(tmp_path: Path) -> None:
    """Spec 061, 1.8: un logotipo que servimos nosotros, desde ``public/connector-logos/``
    de la consola y del panel. Solo esa carpeta y un nombre de archivo, nada más."""
    _seed_with(tmp_path, "  icon_url: /connector-logos/x.png\n")
    assert load_seed("x", seeds_dir=tmp_path).provider_meta["icon_url"] == "/connector-logos/x.png"


@pytest.mark.parametrize(
    "icon",
    [
        "/otra-carpeta/x.png",
        "/connector-logos/../x.png",
        "/connector-logos/sub/x.png",
        "//cdn.example/connector-logos/x.png",
        "/connector-logos/x.exe",
    ],
)
def test_any_other_local_icon_is_refused(tmp_path: Path, icon: str) -> None:
    _seed_with(tmp_path, f"  icon_url: {icon}\n")
    with pytest.raises(ConnectorSeedInvalid, match="icon_url"):
        load_seed("x", seeds_dir=tmp_path)


@pytest.mark.parametrize(
    "options",
    [
        "[]",
        "[{label: Uno}]",
        "[{value: a}, {value: a}]",
        "[{value: 1}]",
    ],
    ids=["vacía", "sin valor", "repetida", "no es texto"],
)
def test_a_dropdown_field_needs_distinct_text_values(tmp_path: Path, options: str) -> None:
    _seed_with(
        tmp_path,
        f"  credentials_form:\n    - field: mode\n      options: {options}\n",
    )
    with pytest.raises(ConnectorSeedInvalid, match="options"):
        load_seed("x", seeds_dir=tmp_path)


def test_quedate_asks_for_the_environment_with_a_dropdown_and_short_labels() -> None:
    """Spec 061, 1.7 y 1.8 (Luis, 2026-11-18): el entorno era un texto libre y la
    etiqueta, con toda la explicación, se cortaba en la consola."""
    meta = load_seed("quedate").provider_meta
    form = {f["field"]: f for f in meta["credentials_form"]}
    assert [o["value"] for o in form["environment"]["options"]] == ["production", "dev"]
    assert all(len(f["label"]) <= 20 for f in form.values()), "la etiqueta cabe en una línea"
    assert "Gestión de Tokens" in form["api_key"]["hint"]

    assert meta["icon_url"] == "/connector-logos/quedate.png"
    root = Path(__file__).resolve().parents[5]
    for app in ("console", "admin"):
        assert (root / "apps" / app / "public/connector-logos/quedate.png").is_file(), app


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

    s = load_seed("woocommerce")
    assert isinstance(s, ConnectorSeed)
    with pytest.raises(ValidationError):
        s.slug = "mutated"  # type: ignore[misc]
