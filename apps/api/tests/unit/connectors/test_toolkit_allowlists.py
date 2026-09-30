"""Spec 023 (Requisitos 2.3, 2.5, 3.2): the closed lists per toolkit.

Every slug has a prefix, a coherent hint and — the rule that matters most
to a partner — a business name in both languages. Adding a slug without a
name makes this file red before it makes a screen ugly.
"""

from __future__ import annotations

from nexus_api.api.console.capability_names import CAPABILITY_NAMES
from nexus_api.services.connectors.toolkits import (
    TOOLKIT_ALLOWLISTS,
    allowlist_for,
    hint_for_slug,
)

EXPECTED_SIZES = {"stripe": 12, "calendly": 10, "hubspot": 11}


def test_the_three_toolkits_have_the_agreed_sizes() -> None:
    assert {k: len(v) for k, v in TOOLKIT_ALLOWLISTS.items()} == EXPECTED_SIZES


def test_every_slug_carries_its_toolkit_prefix() -> None:
    for toolkit, entries in TOOLKIT_ALLOWLISTS.items():
        for slug in entries:
            assert slug.startswith(toolkit.upper() + "_"), f"{slug} no es de {toolkit}"
            assert slug == slug.upper(), f"{slug} no está en mayúsculas"


def test_a_tool_either_reads_or_writes_never_both_never_neither() -> None:
    for entries in TOOLKIT_ALLOWLISTS.values():
        for slug, hint in entries.items():
            assert not (hint["read_only"] and hint["destructive"]), f"{slug} lee y escribe"
            if not hint["read_only"]:
                assert hint["destructive"], f"{slug} no lee pero tampoco nace bloqueada"


def test_every_allowlisted_slug_has_a_business_name() -> None:
    """Requisito 3.2: toda herramienta de la lista cerrada tiene nombre de
    negocio; una sin nombre no entra."""
    for entries in TOOLKIT_ALLOWLISTS.values():
        for slug in entries:
            entry = CAPABILITY_NAMES.get(("tool", slug))
            assert entry is not None, f"{slug} no tiene nombre de negocio"
            for lang in ("es", "en"):
                assert entry["name"].get(lang, "").strip(), f"{slug} sin nombre en {lang}"
                assert entry["name"][lang] != slug, f"{slug} repite el slug como nombre"
                assert entry["description"].get(lang, "").strip(), (
                    f"{slug} sin descripción en {lang}"
                )


def test_reads_and_writes_split_as_agreed() -> None:
    reads = {k: sum(1 for h in v.values() if h["read_only"]) for k, v in TOOLKIT_ALLOWLISTS.items()}
    assert reads == {"stripe": 8, "calendly": 7, "hubspot": 6}


def test_lookups_are_case_insensitive_and_prefix_based() -> None:
    assert allowlist_for("Stripe") is TOOLKIT_ALLOWLISTS["stripe"]
    assert allowlist_for("notion") is None
    assert hint_for_slug("CALENDLY_POST_INVITEE") == {"read_only": False, "destructive": True}
    assert hint_for_slug("CALENDLY_WHO_AM_I") == {"read_only": True, "destructive": False}
    assert hint_for_slug("CALENDLY_CANCEL_EVENT") is None  # slug que no existe
    assert hint_for_slug("NOTION_SEARCH") is None
    assert hint_for_slug("NOPREFIX") is None
