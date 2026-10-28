"""Spec 047, T073 — el validador sin modelo del AgentSpec (requisitos 15.4, 16.1 y 16.6).

Rechaza, cada cosa con su código y su puntero:
- claves de plataforma;
- herramientas fuera de catálogo, no permitidas al partner o sin conectar;
- un cliente final como argumento (garantía 8);
- datos de otro cliente;
- un aviso de IA que llega decidido del constructor.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from nexus_api.services.agent_spec.validator import Context, ToolInfo, validate_spec
from tests.unit.test_agent_spec_contract import INSTRUCTIONS, STRUCTURED

SERVICE = "4b0c8a5e-3f0e-4d0b-9b8e-2a6f3a1c9d10"
SIBLING = "5b0c8a5e-3f0e-4d0b-9b8e-2a6f3a1c9d10"

CTX = Context(
    tools={
        "reservas.find_slots": ToolInfo("reservas.find_slots"),
        "reservas.create": ToolInfo(
            "reservas.create", args=frozenset({"service_id", "conversation_id"})
        ),
        "billing.find_client": ToolInfo(
            "billing.find_client", args=frozenset({"phone", "document"})
        ),
        "agendapro.book": ToolInfo("agendapro.book", status="internal"),
        "old.tool": ToolInfo("old.tool", status="deprecated"),
        "hubspot.create_contact": ToolInfo(
            "hubspot.create_contact", integration="hubspot", connected=False
        ),
        "shopify.list_orders": ToolInfo(
            "shopify.list_orders", integration="shopify", integration_offered=False
        ),
    },
    service_ids=frozenset({SERVICE}),
    agent_ids=frozenset({SIBLING}),
    foreign_names=("Flor y Encanto", "Café"),
)


def _doc(**changes: Any) -> dict[str, Any]:
    doc = copy.deepcopy(STRUCTURED)
    doc.update(changes)
    return doc


def _codes(doc: dict[str, Any], **kw: Any) -> set[tuple[str, str]]:
    _spec, problems = validate_spec(doc, CTX, **kw)
    return {(p.pointer, p.code) for p in problems}


def test_a_good_spec_has_no_problems() -> None:
    spec, problems = validate_spec(STRUCTURED, CTX)
    assert spec is not None and problems == []


def test_a_platform_key_is_refused() -> None:
    assert ("/policies", "platform_key") in _codes(_doc(policies={"admin_access": {}}))
    nested = _doc()
    nested["identity"]["runtime_skills"] = []
    assert ("/identity/runtime_skills", "platform_key") in _codes(nested)


@pytest.mark.parametrize(
    ("tool", "code"),
    [
        ("calendar.unknown", "tool_unknown"),
        ("agendapro.book", "tool_not_allowed"),
        ("old.tool", "tool_not_allowed"),
        ("shopify.list_orders", "tool_not_allowed"),
        ("hubspot.create_contact", "tool_not_connected"),
    ],
)
def test_tools_are_in_the_catalog_allowed_and_connected(tool: str, code: str) -> None:
    doc = _doc(tools=["reservas.find_slots", tool])
    assert ("/tools/1", code) in _codes(doc)


def test_a_procedure_cannot_cite_a_tool_out_of_the_catalog() -> None:
    doc = _doc()
    doc["procedures"][0]["tools"] = ["reservas.create", "calendar.unknown"]
    assert ("/procedures/0/tools/1", "tool_unknown") in _codes(doc)


def test_an_end_customer_as_argument_is_refused() -> None:
    doc = _doc(tools=["reservas.create", "billing.find_client"])
    codes = _codes(doc)
    assert ("/tools/1", "end_customer_argument") in codes
    # El que pone el servidor (``conversation_id``) no cuenta.
    assert ("/tools/0", "end_customer_argument") not in codes


def test_a_migrated_agent_keeps_its_operator_tools_unless_the_builder_proposes() -> None:
    legacy = copy.deepcopy(INSTRUCTIONS)
    legacy["tools"] = ["billing.find_client"]
    assert _codes(legacy, author="person") == set()
    assert ("/tools/0", "end_customer_argument") in _codes(legacy, author="builder")


def test_nothing_of_another_client() -> None:
    doc = _doc()
    doc["services"]["service_ids"] = [SERVICE, "9b0c8a5e-3f0e-4d0b-9b8e-2a6f3a1c9d10"]
    doc["reception"]["targets"][0]["agent_id"] = "8b0c8a5e-3f0e-4d0b-9b8e-2a6f3a1c9d10"
    doc["rules"] = ["Haz como en Flor y Encanto: ofrece el ramo del día."]
    codes = _codes(doc)
    assert ("/services/service_ids/1", "foreign_reference") in codes
    assert ("/reception/targets/0/agent_id", "foreign_reference") in codes
    assert ("/rules/0", "foreign_text") in codes


def test_a_short_name_of_another_client_is_not_a_hit() -> None:
    """«Café» es una palabra corriente: no se toma por el nombre de otro cliente."""
    doc = _doc(rules=["Ofrece café a quien espera."])
    assert not any(code == "foreign_text" for _p, code in _codes(doc))


def test_the_builder_cannot_decide_the_ai_disclosure() -> None:
    assert ("/ai_disclosure/decided", "ai_disclosure_decided_by_builder") in _codes(
        STRUCTURED, author="builder"
    )
    undecided = _doc(ai_disclosure={"decided": False})
    assert _codes(undecided, author="builder") == set()
    # Una persona sí.
    assert _codes(STRUCTURED, author="person") == set()


def test_instructions_are_at_most_8000_characters() -> None:
    doc = _doc()
    doc["instructions"]["sections"] = [{"title": f"S{i}", "body": "x" * 4000} for i in range(3)]
    assert ("/instructions/sections", "instructions_too_long") in _codes(doc)


def test_a_migrated_prompt_can_keep_its_size_but_not_grow() -> None:
    long = copy.deepcopy(INSTRUCTIONS)
    long["instructions"]["legacy_text"] = "y" * 9000
    ctx = Context(tools=CTX.tools, legacy_chars=9000)
    assert validate_spec(long, ctx)[1] == []
    long["instructions"]["legacy_text"] = "y" * 9001
    assert validate_spec(long, ctx)[1][0].code == "instructions_too_long"


def test_problems_come_in_the_same_order_every_time() -> None:
    doc = _doc(tools=["calendar.unknown", "billing.find_client"], rules=["Como Flor y Encanto"])
    first = validate_spec(doc, CTX, author="builder")[1]
    assert first == validate_spec(doc, CTX, author="builder")[1]
    assert len(first) >= 3
