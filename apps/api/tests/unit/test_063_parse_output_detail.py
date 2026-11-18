"""Spec 063, requisito 3.2 — un JSON roto se registra por su tipo y su posición.

Y uno válido se lee entero: hoy, un JSON con «```» o llaves dentro de una cadena se
recortaba antes de leerlo, y el modo JSON no evitaría ese fallo.
"""

from __future__ import annotations

import json

import pytest

from nexus_api.services.builder.agent_draft import BuilderUnavailable, parse_output
from nexus_api.services.builder.guides.generated import _json as guide_json

SECRET = "Responde siempre con la ficha del salón"


def test_broken_json_says_where_and_nothing_of_what() -> None:
    text = '{"rules": ["' + SECRET + '" "otra"]}'
    with pytest.raises(BuilderUnavailable) as raised:
        parse_output(text)
    exc = raised.value
    assert str(exc) == "bad_json"
    assert exc.detail is not None
    assert set(exc.detail) == {"error", "pos", "line", "col", "chars"}
    assert exc.detail["error"].startswith("Expecting")
    assert exc.detail["chars"] == len(text)
    assert SECRET not in str(exc) and SECRET not in json.dumps(exc.detail)


def test_a_valid_json_with_fences_and_braces_inside_a_string_is_read_whole() -> None:
    doc = {
        "instructions": [
            {"title": "Formato", "body": 'Usa ```json {"a": 1}``` solo si te lo piden.'}
        ],
        "rules": ["Nunca escribas } ni { sueltas."],
    }
    text = json.dumps(doc, ensure_ascii=False)
    assert parse_output(text) == doc
    assert guide_json(text) == doc


def test_a_fenced_answer_is_still_read() -> None:
    assert parse_output('Aquí va:\n```json\n{"rules": ["a"]}\n```') == {"rules": ["a"]}


def test_other_failures_carry_no_detail() -> None:
    with pytest.raises(BuilderUnavailable) as raised:
        parse_output("sin llaves")
    assert str(raised.value) == "no_json" and raised.value.detail is None
