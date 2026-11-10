"""Spec 057, T018 — «No tenemos herramienta para» dice lo que falta ahora (requisito 6).

Lo que el constructor anotó al escribir el agente (``policies.builder``) se
contrasta, al leer, con lo que la versión tiene: lo que ya hace una herramienta,
el módulo que ya está encendido y la integración que ya está conectada dejan de
salir. Una herramienta que no existe sigue saliendo (6.1, 6.2, 6.4).
"""

from __future__ import annotations

import copy
from typing import Any

from nexus_api.services.agent_spec import missing
from nexus_api.services.agent_spec.missing import MissingCapability, still_missing
from nexus_api.services.agent_spec.schema import AgentSpec
from nexus_api.services.agent_spec.validator import Context, ToolInfo
from nexus_api.services.reservations.passing import RESERVAS_TOOLS
from tests.unit.test_agent_spec_contract import STRUCTURED

#: Lo que guardó el constructor de «Recepción de Spa Jemma» (staging, 2026-11-08),
#: con Reservas apagado para el cliente.
SPA_JEMMA_NOTE: list[dict[str, Any]] = [
    {
        "kind": "action",
        "key": "modify_booking",
        "label": "cambiar o cancelar citas",
        "reason": "no_tool",
        "source": "text",
        "pointer": None,
    },
    {
        "kind": "action",
        "key": "book",
        "label": "reservar citas",
        "reason": "no_tool",
        "source": "text",
        "pointer": None,
    },
]


def _ctx(*, reservas_on: bool, hubspot: bool = False, catalog: bool = False) -> Context:
    tools = {
        name: ToolInfo(name, integration="reservas", connected=reservas_on, activatable=False)
        for name in RESERVAS_TOOLS
    }
    tools["hubspot.create_contact"] = ToolInfo(
        "hubspot.create_contact", integration="hubspot", connected=hubspot
    )
    tools["catalog.send"] = ToolInfo(
        "catalog.send", integration="channel_catalog", connected=catalog, activatable=False
    )
    return Context(tools=tools)


def _spec(tools: list[str]) -> AgentSpec:
    doc = copy.deepcopy(STRUCTURED)
    doc["tools"] = tools
    doc["procedures"] = []
    return AgentSpec.model_validate(doc)


def _keys(items: list[MissingCapability]) -> list[tuple[str, str]]:
    return [(m.kind, m.key) for m in items]


def test_an_action_a_tool_now_does_is_no_longer_missing() -> None:
    items = [
        missing.action("book", "reservar citas", None),
        missing.action("invoice", "emitir facturas", None),
    ]
    out = still_missing(
        items, _spec(["reservas.find_slots", "reservas.create"]), _ctx(reservas_on=True)
    )
    assert _keys(out) == [("action", "invoice")]
    # Sin la herramienta, sigue faltando.
    out = still_missing(items, _spec(["reservas.services"]), _ctx(reservas_on=True))
    assert _keys(out) == [("action", "book"), ("action", "invoice")]


def test_reservas_off_is_no_longer_missing_once_it_is_on() -> None:
    items = [missing.not_offered("reservas", module=True, source="skill", skill="agenda")]
    assert _keys(still_missing(items, _spec([]), _ctx(reservas_on=False))) == [
        ("module", "reservas")
    ]
    assert still_missing(items, _spec([]), _ctx(reservas_on=True)) == []


def test_an_integration_now_connected_is_no_longer_missing() -> None:
    items = [
        missing.integration("hubspot", source="skill", skill="crm"),
        missing.not_offered("channel_catalog", module=False, source="tool"),
    ]
    assert _keys(still_missing(items, _spec([]), _ctx(reservas_on=False))) == [
        ("integration", "hubspot"),
        ("integration", "channel_catalog"),
    ]
    assert (
        still_missing(items, _spec([]), _ctx(reservas_on=False, hubspot=True, catalog=True)) == []
    )


def test_an_unknown_tool_stays() -> None:
    items = [missing.tool("calendar.unknown")]
    out = still_missing(items, _spec(list(RESERVAS_TOOLS)), _ctx(reservas_on=True))
    assert _keys(out) == [("tool", "calendar.unknown")]


def test_the_spa_jemma_note_with_the_nine_tools_is_empty() -> None:
    items = missing.from_json(SPA_JEMMA_NOTE)
    assert len(items) == 2
    assert still_missing(items, _spec(list(RESERVAS_TOOLS)), _ctx(reservas_on=True)) == []
    # Con la nota de un constructor viejo que solo guardó la etiqueta, igual.
    by_label = [
        MissingCapability("action", "reservar", "reservar citas", "no_tool", "text"),
        MissingCapability("action", "mover", "cambiar o cancelar citas", "no_tool", "text"),
    ]
    assert still_missing(by_label, _spec(list(RESERVAS_TOOLS)), _ctx(reservas_on=True)) == []


def test_only_moving_keeps_the_promise_to_book_missing() -> None:
    items = missing.from_json(SPA_JEMMA_NOTE)
    out = still_missing(
        items, _spec(["reservas.reschedule", "reservas.cancel"]), _ctx(reservas_on=True)
    )
    assert _keys(out) == [("action", "book")]
