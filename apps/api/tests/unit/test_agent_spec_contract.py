"""Spec 047, T073 — el AgentSpec de Pydantic es el del contrato (requisito 16.1).

``services/agent_spec/schema.AgentSpec`` y
``specs/047-la-fabrica-de-agentes/contracts/agent-spec.schema.json`` dicen lo
mismo, campo a campo, con el mismo normalizador que la prueba del ClientSpec
(T072). Y con documentos: uno completo de cada modo vale para los dos, y cada
uno de los rotos, para ninguno.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from pydantic import ValidationError

from nexus_api.services.agent_spec.schema import AgentSpec, dump
from tests.unit.test_client_spec_contract import _diff, normalise

CONTRACT = (
    Path(__file__).resolve().parents[4]
    / "specs"
    / "047-la-fabrica-de-agentes"
    / "contracts"
    / "agent-spec.schema.json"
)


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return json.loads(CONTRACT.read_text())


def test_the_pydantic_schema_is_the_contract(contract: dict[str, Any]) -> None:
    generated = AgentSpec.model_json_schema()
    assert _diff(normalise(generated, generated), normalise(contract, contract)) == []


def test_the_normaliser_sees_a_difference(contract: dict[str, Any]) -> None:
    tampered = copy.deepcopy(contract)
    tampered["properties"]["identity"]["properties"]["name"]["maxLength"] = 41
    generated = AgentSpec.model_json_schema()
    assert _diff(normalise(generated, generated), normalise(tampered, tampered)) == [
        "/properties/identity/properties/name/maxLength: pydantic=40 contract=41"
    ]


STRUCTURED: dict[str, Any] = {
    "schema_version": "1",
    "mode": "structured",
    "identity": {
        "name": "Recepción",
        "description": "Atiende las citas de la barbería y responde dudas de horario y precios.",
        "goal": "Que cada cliente salga con su cita.",
    },
    "voice": {
        "tone": "Cercano",
        "languages": ["es-ES", "en"],
        "register": "tu",
        "greeting": "¡Hola!",
    },
    "instructions": {"sections": [{"title": "Cómo atiendes", "body": "Pregunta el servicio."}]},
    "procedures": [
        {
            "id": "reservar",
            "title": "Reservar una cita",
            "when": "Cuando piden cita",
            "steps": "Busca hueco y reserva.",
            "tools": ["reservas.find_slots", "reservas.create"],
        }
    ],
    "services": {
        "mode": "list",
        "service_ids": ["4b0c8a5e-3f0e-4d0b-9b8e-2a6f3a1c9d10"],
        "faqs": [{"q": "¿Aparcamiento?", "a": "Hay uno al lado."}],
    },
    "skills": [{"key": "booking", "enabled": True, "fallback": "Pasa al equipo."}],
    "tools": ["reservas.find_slots", "reservas.create"],
    "connection_requests": [{"integration": "google_calendar", "reason": "Para ver la agenda"}],
    "escalation": {
        "triggers": ["asks_for_human", {"custom": "Si pregunta por facturas"}],
        "failed_attempts": 2,
        "message": "Te paso con el equipo.",
    },
    "rules": ["No ofrezcas descuentos."],
    "team_access": [{"phone_e164": "+34600123456", "level": "full", "label": "Marta"}],
    "ai_disclosure": {"decided": True, "mode": "first_message", "text": "Soy un asistente."},
    "model_policy": {"kind": "profile", "profile": "auto"},
    "memory": {"scope": "shared"},
    "reception": {
        "enabled": True,
        "targets": [
            {"agent_id": "5b0c8a5e-3f0e-4d0b-9b8e-2a6f3a1c9d10", "when": "Ventas al por mayor"}
        ],
    },
    "test_suite": {"suite_id": "6b0c8a5e-3f0e-4d0b-9b8e-2a6f3a1c9d10", "revision": 1},
}

INSTRUCTIONS: dict[str, Any] = {
    "schema_version": "1",
    "mode": "instructions",
    "identity": {"name": "Asistente", "description": "Agente migrado de antes de la spec 047."},
    "instructions": {"legacy_text": "Eres el asistente de la barbería.\n\nResponde en español."},
    "ai_disclosure": {"decided": False},
    "model_policy": {"kind": "pinned", "deployment": "openai/gpt-5.6-sol"},
    "memory": {"scope": "shared"},
}


def _accepts(contract: dict[str, Any], doc: dict[str, Any]) -> bool:
    try:
        jsonschema.Draft202012Validator(contract).validate(doc)
    except jsonschema.ValidationError:
        return False
    return True


def _pydantic_accepts(doc: dict[str, Any]) -> bool:
    try:
        AgentSpec.model_validate(doc)
    except ValidationError:
        return False
    return True


@pytest.mark.parametrize("doc", [STRUCTURED, INSTRUCTIONS], ids=["structured", "instructions"])
def test_a_full_document_is_valid_for_both(doc: dict[str, Any], contract: dict[str, Any]) -> None:
    assert _accepts(contract, doc)
    spec = AgentSpec.model_validate(doc)
    # Lo que se guarda es lo que entró.
    assert dump(spec) == doc


def _set(doc: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    out = copy.deepcopy(doc)
    *parents, last = path.split("/")
    node: Any = out
    for part in parents:
        node = node[int(part)] if isinstance(node, list) else node[part]
    if value is _DROP:
        del node[last]
    elif isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value
    return out


_DROP = object()

BROKEN: dict[str, tuple[dict[str, Any], str, Any]] = {
    "a platform key": (STRUCTURED, "policies", {"admin_access": {}}),
    "a platform key inside identity": (STRUCTURED, "identity/kg_schema_id", "x"),
    "a name of 41": (STRUCTURED, "identity/name", "x" * 41),
    "a description of 19": (STRUCTURED, "identity/description", "x" * 19),
    "a tool without a dot": (STRUCTURED, "tools", ["reservas"]),
    "a repeated tool": (STRUCTURED, "tools", ["reservas.create", "reservas.create"]),
    "a register of your own": (STRUCTURED, "voice/register", "vosotros"),
    "a language in caps": (STRUCTURED, "voice/languages", ["ES"]),
    "an unknown trigger": (STRUCTURED, "escalation/triggers", ["when_angry"]),
    "six failed attempts": (STRUCTURED, "escalation/failed_attempts", 6),
    "a pinned model without deployment": (STRUCTURED, "model_policy", {"kind": "pinned"}),
    "an unknown profile": (STRUCTURED, "model_policy", {"kind": "profile", "profile": "turbo"}),
    "a phone without plus": (STRUCTURED, "team_access/0/phone_e164", "600123456"),
    "a structured spec without tools": (STRUCTURED, "tools", _DROP),
    "an instructions spec without legacy_text": (INSTRUCTIONS, "instructions", {}),
    "an older schema": (STRUCTURED, "schema_version", "0"),
    "no ai disclosure": (STRUCTURED, "ai_disclosure", _DROP),
}


@pytest.mark.parametrize("case", sorted(BROKEN))
def test_a_broken_document_is_rejected_by_both(case: str, contract: dict[str, Any]) -> None:
    base, path, value = BROKEN[case]
    doc = _set(base, path, value)
    assert not _accepts(contract, doc), f"the contract accepts {case}"
    assert not _pydantic_accepts(doc), f"pydantic accepts {case}"
