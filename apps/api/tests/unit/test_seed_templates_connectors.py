"""Spec 023 (Requisito 4.1): the sector template says which connectors
Conectores suggests. A YAML without the block loads as before; a malformed
block fails like any other schema error.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from nexus_api.services.templating import seed_templates
from nexus_api.services.templating.seed_templates import load_seed_template

APPOINTMENTS = [
    "barbershop_v1",
    "beauty_salon_v1",
    "clinica_v1",
    "dental_v1",
    "medspa_v1",
    "nail_studio_v1",
    "spa_v1",
    "aesthetic_clinic_v1",
]


@pytest.mark.parametrize("name", APPOINTMENTS)
def test_appointment_sectors_recommend_calendly_next_to_agendapro(name: str) -> None:
    assert load_seed_template(name).connectors_recommended == ["agendapro", "calendly"]


def test_collections_recommend_stripe_next_to_amigable_cobro() -> None:
    assert load_seed_template("cobranza_v1").connectors_recommended == ["amigable_cobro", "stripe"]


@pytest.mark.parametrize("name", ["woocommerce_sales_v1", "inventario_v1"])
def test_store_sectors_keep_recommending_woocommerce(name: str) -> None:
    assert load_seed_template(name).connectors_recommended == ["woocommerce"]


@pytest.mark.parametrize("name", ["generic_v1", "restaurante_v1"])
def test_a_template_without_the_block_recommends_nobody(name: str) -> None:
    assert load_seed_template(name).connectors_recommended == []


def _write_variant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, connectors: object) -> str:
    raw = yaml.safe_load(
        (seed_templates._SEEDS_DIR / "generic_v1.yaml").read_text(encoding="utf-8")
    )
    raw["connectors"] = connectors
    (tmp_path / "variant_v1.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    monkeypatch.setattr(seed_templates, "_SEEDS_DIR", tmp_path)
    return "variant_v1"


def test_the_block_is_a_list_of_slugs_or_it_is_a_repo_bug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = _write_variant(tmp_path, monkeypatch, {"recommended": "stripe"})
    with pytest.raises(ValueError, match=r"connectors\.recommended"):
        load_seed_template(name)


def test_an_empty_block_is_fine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    name = _write_variant(tmp_path, monkeypatch, {"recommended": []})
    assert load_seed_template(name).connectors_recommended == []
