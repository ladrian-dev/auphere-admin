"""Spec 063, requisito 1.6 y 1.7 — los idiomas se deciden en un solo sitio.

«Cómo habla» del AgentSpec es lo único que los escribe (se copian a
``policies.console.languages`` al guardar). La página de ajustes antigua y el
Companion ya no los cambian: ``merge_console_policy`` conserva los guardados.
"""

from __future__ import annotations

from nexus_api.companion.tools.proposals import POLICY_FIELDS
from nexus_api.services.agent_console_policy import (
    ConsolePolicy,
    LanguagesPolicy,
    merge_console_policy,
)


def test_languages_are_not_limited_by_default() -> None:
    assert LanguagesPolicy().limited is False
    assert ConsolePolicy().languages.limited is False


def test_the_old_settings_page_cannot_change_the_languages() -> None:
    stored = {"console": {"languages": {"primary": "es", "allowed": ["es", "en"], "limited": True}}}
    incoming = ConsolePolicy.model_validate(
        {"objective": "agendar", "languages": {"primary": "fr", "allowed": ["fr"]}}
    )
    out = merge_console_policy(stored, incoming, actor="person:1")
    assert out["console"]["objective"] == "agendar"
    assert out["console"]["languages"] == {
        "primary": "es",
        "allowed": ["es", "en"],
        "limited": True,
    }


def test_without_stored_languages_the_old_page_writes_the_default() -> None:
    incoming = ConsolePolicy.model_validate({"languages": {"primary": "fr", "allowed": ["fr"]}})
    out = merge_console_policy({}, incoming, actor="person:1")
    assert out["console"]["languages"] == LanguagesPolicy().model_dump(mode="json")


def test_the_companion_no_longer_proposes_the_main_language() -> None:
    assert "primary_language" not in POLICY_FIELDS
    assert all(path[0] != "languages" for path in POLICY_FIELDS.values())
