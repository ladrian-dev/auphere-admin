"""Unit tests for the owner inbound command parser.

The parser is pure (no IO) — exhaustive table-driven cases live here.
Phase 1 routes ``free_text`` / ``yes`` / ``no`` only; slash commands
degrade to ``unknown_command``.
"""

from __future__ import annotations

import pytest

from nexus_api.services.owner_command_parser import (
    ParsedOwnerMessage,
    parse_owner_message,
)


@pytest.mark.parametrize(
    "text,kind",
    [
        ("sí", "yes"),
        ("Sí", "yes"),
        ("SI", "yes"),
        ("ok", "yes"),
        ("Okay", "yes"),
        ("dale", "yes"),
        ("listo", "yes"),
        ("hecho", "yes"),
        ("perfecto", "yes"),
        ("confirmo", "yes"),
        ("Confirmado.", "yes"),
        ("ya", "yes"),
        ("yep", "yes"),
    ],
)
def test_yes_variants(text: str, kind: str) -> None:
    parsed = parse_owner_message(text)
    assert parsed.kind == kind
    assert parsed.free_text  # original preserved for audit


@pytest.mark.parametrize(
    "text",
    ["no", "No", "Nope", "negativo", "imposible", "ahora no", "no por ahora", "No."],
)
def test_no_variants(text: str) -> None:
    parsed = parse_owner_message(text)
    assert parsed.kind == "no"
    assert parsed.free_text == text.strip()


@pytest.mark.parametrize(
    "text",
    [
        "Cobrá $25.000 por ese corte",
        "Decile que pase mañana a las 4pm",
        "Hmm puede ser",
        "Tal vez",
        "Depende del horario",
        "1234",
    ],
)
def test_free_text_fallback(text: str) -> None:
    parsed = parse_owner_message(text)
    assert parsed.kind == "free_text"
    assert parsed.free_text == text.strip()


def test_empty_and_whitespace() -> None:
    assert parse_owner_message("").kind == "empty"
    assert parse_owner_message("   ").kind == "empty"
    assert parse_owner_message("\n\t  \n").kind == "empty"


def test_none_is_empty() -> None:
    assert parse_owner_message(None).kind == "empty"  # type: ignore[arg-type]


def test_slash_command_unsupported_in_phase_1() -> None:
    parsed = parse_owner_message("/handoff")
    assert parsed.kind == "unknown_command"
    assert parsed.slash_verb == "handoff"
    assert parsed.slash_arg == ""


def test_slash_command_with_argument() -> None:
    parsed = parse_owner_message("/responde Decile que llegue 10 minutos antes")
    assert parsed.kind == "unknown_command"
    assert parsed.slash_verb == "responde"
    assert parsed.slash_arg == "Decile que llegue 10 minutos antes"


def test_parsed_dataclass_is_immutable() -> None:
    parsed = parse_owner_message("sí")
    assert isinstance(parsed, ParsedOwnerMessage)
    with pytest.raises(Exception):  # frozen dataclass
        parsed.kind = "no"  # type: ignore[misc]
