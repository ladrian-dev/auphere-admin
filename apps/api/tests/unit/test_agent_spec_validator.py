"""Spec 047, T073 — el validador sin modelo del AgentSpec (requisitos 15.4, 16.1 y 16.6).

Rechaza, cada cosa con su código y su puntero:
- claves de plataforma;
- herramientas fuera de catálogo o no permitidas al partner (sin conectar, desde la
  enmienda del 2026-10-29, queda pendiente: requisito 62.4);
- un cliente final como argumento (garantía 8);
- datos de otro cliente;
- un aviso de IA que llega decidido del constructor.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from nexus_api.services.agent_spec.validator import (
    Context,
    ToolInfo,
    problems_out,
    validate_spec,
)
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
        "ops.sync_internal": ToolInfo("ops.sync_internal", status="internal"),
        # Spec 048: retired, as the catalog marks them after 0205.
        "booking.create_appointment": ToolInfo("booking.create_appointment", status="deprecated"),
        "booking.check_availability": ToolInfo("booking.check_availability", status="deprecated"),
        "old.tool": ToolInfo("old.tool", status="deprecated"),
        "hubspot.create_contact": ToolInfo(
            "hubspot.create_contact", integration="hubspot", connected=False
        ),
        # Spec 047, enmienda del 2026-10-30 (65.3): la petición de conexión de
        # STRUCTURED (``google_calendar``) es la de un conector ofrecido.
        "google_calendar.list_events": ToolInfo(
            "google_calendar.list_events", integration="google_calendar", connected=False
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
        ("ops.sync_internal", "tool_not_allowed"),
        ("old.tool", "tool_not_allowed"),
        ("shopify.list_orders", "tool_not_allowed"),
    ],
)
def test_tools_are_in_the_catalog_and_allowed(tool: str, code: str) -> None:
    # Spec 047, enmienda del 2026-10-29 (62.4): sin conectar ya no es un problema;
    # la herramienta queda pendiente de conexión (``test_pending_tools``).
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


def test_a_retired_booking_tool_is_refused_and_its_reservas_one_proposed() -> None:
    """Spec 048 (requisitos 2.2 y 2.3): ``booking.*`` writes in a table the
    business does not see. A new or edited draft that carries it is refused
    with ``tool_retired``, and the problem names the Reservas tool that
    replaces it — in ``tools`` and in a procedure alike."""
    doc = _doc(tools=["reservas.find_slots", "booking.create_appointment"])
    doc["procedures"][0]["tools"] = ["booking.check_availability"]
    _spec, problems = validate_spec(doc, CTX)
    retired = [p for p in problems if p.code == "tool_retired"]
    assert {(p.pointer, p.replacement) for p in retired} == {
        ("/tools/1", "reservas.create"),
        ("/procedures/0/tools/0", "reservas.find_slots"),
    }
    assert all("Reservas" in p.message for p in retired)
    out = problems_out(retired)
    assert {o["replacement"] for o in out} == {"reservas.create", "reservas.find_slots"}
    # A problem without a replacement keeps the three keys it always had.
    _spec, others = validate_spec(_doc(tools=["calendar.unknown"]), CTX)
    assert set(problems_out(others)[0]) == {"pointer", "code", "message"}


def test_retired_by_name_even_where_the_catalog_still_says_active() -> None:
    """The retirement is the code's decision; a catalog that has not run 0205
    yet does not let ``booking.*`` back in."""
    from dataclasses import replace

    ctx = replace(
        CTX,
        tools={**CTX.tools, "booking.create_appointment": ToolInfo("booking.create_appointment")},
    )
    _spec, problems = validate_spec(_doc(tools=["booking.create_appointment"]), ctx)
    assert [(p.pointer, p.code) for p in problems] == [("/tools/0", "tool_retired")]


def test_a_published_version_with_booking_still_runs() -> None:
    """Spec 048 (requisito 5.3): until the final removal the runtime keeps
    ``booking.*`` for the versions that already have it — registered, and
    handed to the model when the version's whitelist names it."""
    from nexus_mcp import build_default_registry

    registry = build_default_registry()
    booking = [
        "booking.check_availability",
        "booking.create_appointment",
        "booking.modify_appointment",
        "booking.cancel_appointment",
        "booking.get_appointments",
    ]
    assert all(registry.has(name) for name in booking)
    assert [d.name for d in registry.get_tool_definitions(booking)] == sorted(booking)
