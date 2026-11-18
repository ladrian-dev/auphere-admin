"""Spec 063, requisitos 1.6 y 1.9 — «Responder solo en estos idiomas».

El límite vive en ``voice.languages_limited`` del AgentSpec. Es opcional y su
ausencia es «sin límite». Solo una persona lo enciende o lo apaga: el constructor,
el copiloto y las sugerencias no lo cambian (como el aviso de IA, 047 16.6).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from nexus_api.services.agent_spec.schema import Voice
from nexus_api.services.agent_spec.validator import validate_spec
from nexus_api.services.builder.agent_draft import DraftRequest, sanitize
from nexus_api.services.business.compilation import Facts
from tests.unit.test_agent_spec_validator import CTX, STRUCTURED

CONTRACT = (
    Path(__file__).resolve().parents[4]
    / "specs"
    / "047-la-fabrica-de-agentes"
    / "contracts"
    / "agent-spec.schema.json"
)
LIMIT = ("/voice/languages_limited", "languages_limit_by_builder")


def _doc(limited: bool | None) -> dict[str, Any]:
    doc = copy.deepcopy(STRUCTURED)
    voice = dict(doc.get("voice") or {})
    voice["languages"] = ["es", "en"]
    voice.pop("languages_limited", None)
    if limited is not None:
        voice["languages_limited"] = limited
    doc["voice"] = voice
    return doc


def _codes(doc: dict[str, Any], **kw: Any) -> set[tuple[str, str]]:
    _spec, problems = validate_spec(doc, CTX, **kw)
    return {(p.pointer, p.code) for p in problems}


def test_voice_takes_the_limit_and_it_is_off_when_absent() -> None:
    assert Voice.model_validate({"languages": ["es"], "languages_limited": True}).languages_limited
    assert Voice.model_validate({"languages": ["es"]}).languages_limited is None


def test_the_contract_describes_the_limit_as_an_optional_boolean() -> None:
    voice = json.loads(CONTRACT.read_text())["properties"]["voice"]
    assert voice["properties"]["languages_limited"] == {"type": "boolean"}
    assert "languages_limited" not in voice.get("required", [])


@pytest.mark.parametrize("author", ["builder", "copilot", "suggestion", "correction"])
def test_only_a_person_turns_the_limit_on_or_off(author: str) -> None:
    off, on = _doc(None), _doc(True)
    spec_off, _ = validate_spec(off, CTX)
    spec_on, _ = validate_spec(on, CTX)
    # Encenderlo o apagarlo no lo puede quien no es una persona…
    assert LIMIT in _codes(on, author=author, base=spec_off)
    assert LIMIT in _codes(_doc(False), author=author, base=spec_on)
    # …sin base (un borrador nuevo), tampoco nace limitado…
    assert LIMIT in _codes(on, author=author)
    # …y lo que no lo toca pasa.
    assert LIMIT not in _codes(on, author=author, base=spec_on)
    assert LIMIT not in _codes(off, author=author)


def test_a_person_changes_it_as_they_like() -> None:
    spec_off, _ = validate_spec(_doc(None), CTX)
    assert LIMIT not in _codes(_doc(True), author="person", base=spec_off)


def test_the_builder_draft_never_carries_the_limit() -> None:
    raw = {
        "voice": {"languages": ["es", "en"], "languages_limited": True},
        "instructions": [{"title": "Cómo atiendes", "body": "Responde con la ficha."}],
        "tools": [],
    }
    request = DraftRequest.clean("Recepción", "Atiende el WhatsApp del negocio y responde dudas.")
    draft = sanitize(raw, request, CTX, Facts(name="Salón Rita"), model_policy=None)
    assert draft.spec.voice is not None
    assert draft.spec.voice.languages == ["es", "en"]
    assert not draft.spec.voice.languages_limited
