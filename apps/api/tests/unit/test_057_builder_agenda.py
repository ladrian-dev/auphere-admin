"""Spec 057, requisitos 1.6 y 1.7 — el constructor obedece a «Gestiona citas».

Con el interruptor encendido (y Reservas ya encendido por la ruta), la v1 lleva las
nueve herramientas de la agenda que estén disponibles y procedimientos para reservar,
mover y cancelar, y no la alternativa de «pasar al equipo para que confirme». Con el
interruptor apagado, ninguna ``reservas.*``, diga lo que diga el modelo. Sin
interruptor (``None``, clientes antiguos de la API), como hasta hoy.
"""

from __future__ import annotations

from typing import Any

from nexus_api.services.agent_spec.validator import Context, ToolInfo
from nexus_api.services.builder.agent_draft import (
    DraftRequest,
    build_messages,
    offline_output,
    sanitize,
)
from nexus_api.services.business.compilation import Facts
from nexus_api.services.reservations.passing import RESERVAS_TOOLS

FACTS = Facts(name="Spa Jemma")
DESCRIPTION = "Atiende el WhatsApp del salón: informa servicios y precios y agenda citas."


def _ctx(*, reservas_on: bool = True) -> Context:
    agenda = {
        name: ToolInfo(name, integration="reservas", connected=reservas_on, activatable=False)
        for name in RESERVAS_TOOLS
    }
    return Context(
        tools={
            **agenda,
            "escalate.escalate_to_human": ToolInfo("escalate.escalate_to_human"),
            "payments.request_review": ToolInfo("payments.request_review"),
        }
    )


def _request(agenda: bool | None) -> DraftRequest:
    return DraftRequest.clean("Recepción", DESCRIPTION, agenda=agenda)


def _raw(**changes: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "instructions": [{"title": "Cómo atiendes", "body": "Responde con la ficha del salón."}],
        "tools": ["escalate.escalate_to_human"],
    }
    raw.update(changes)
    return raw


# Lo que el constructor escribió para Spa Jemma con Reservas apagado (staging, 2026-11-08).
SPA_JEMMA_ALTERNATIVE = {
    "id": "request_appointment",
    "title": "Recoger una solicitud de cita",
    "when": "La persona pide una cita o pregunta por disponibilidad.",
    "steps": (
        "1. Confirma cuál de los servicios registrados quiere. 2. Pregunta el día y la franja "
        "horaria que prefiere. 3. No ofrezcas huecos ni confirmes la reserva. 4. Indica que el "
        "equipo revisará la disponibilidad. 5. Pasa la conversación al equipo."
    ),
    "tools": ["escalate.escalate_to_human"],
}


def test_the_model_is_told_the_agent_manages_appointments() -> None:
    user = build_messages(_request(True), FACTS, _ctx())[1]["content"]
    assert "<agenda>" in user and "reservas." in user


def test_the_model_is_told_it_does_not() -> None:
    user = build_messages(_request(False), FACTS, _ctx())[1]["content"]
    assert "<agenda>" in user and "NO gestiona citas" in user


def test_without_a_switch_nothing_is_said() -> None:
    user = build_messages(_request(None), FACTS, _ctx())[1]["content"]
    assert "<agenda>" not in user


def test_with_the_agenda_the_nine_are_in_even_if_the_model_forgot_them() -> None:
    draft = sanitize(_raw(), _request(True), _ctx(), FACTS, model_policy=None)
    assert set(RESERVAS_TOOLS) <= set(draft.spec.tools or [])


def test_with_the_agenda_there_is_a_procedure_to_book_and_one_to_change() -> None:
    draft = sanitize(_raw(), _request(True), _ctx(), FACTS, model_policy=None)
    cited = {t for p in draft.spec.procedures or [] for t in p.tools or []}
    assert {"reservas.find_slots", "reservas.create"} <= cited
    assert {"reservas.reschedule", "reservas.cancel"} <= cited


def test_with_the_agenda_the_hand_it_to_the_team_alternative_is_dropped() -> None:
    raw = _raw(
        procedures=[SPA_JEMMA_ALTERNATIVE],
        rules=["Una solicitud de cita no es una reserva confirmada."],
        escalation={
            "triggers": [
                "asks_for_human",
                {
                    "custom": "cuando solicitan crear, cambiar o cancelar una cita, porque la agenda no está activa"
                },
            ]
        },
    )
    draft = sanitize(raw, _request(True), _ctx(), FACTS, model_policy=None)
    titles = {p.title for p in draft.spec.procedures or []}
    assert "Recoger una solicitud de cita" not in titles
    customs = [
        t.custom
        for t in (draft.spec.escalation.triggers if draft.spec.escalation else [])
        if hasattr(t, "custom")
    ]
    assert not any("agenda no está activa" in c for c in customs)
    assert "Una solicitud de cita no es una reserva confirmada." not in (draft.spec.rules or [])


def test_without_the_agenda_no_reservas_tool_survives() -> None:
    raw = _raw(tools=["escalate.escalate_to_human", "reservas.create", "reservas.find_slots"])
    draft = sanitize(raw, _request(False), _ctx(), FACTS, model_policy=None)
    assert not any(t.startswith("reservas.") for t in draft.spec.tools or [])
    assert not any(
        t.startswith("reservas.") for p in draft.spec.procedures or [] for t in p.tools or []
    )


def test_without_a_switch_it_is_what_the_model_said() -> None:
    raw = _raw(tools=["escalate.escalate_to_human", "reservas.find_slots"])
    draft = sanitize(raw, _request(None), _ctx(), FACTS, model_policy=None)
    assert "reservas.find_slots" in (draft.spec.tools or [])
    assert "reservas.create" not in (draft.spec.tools or [])


def test_offline_follows_the_switch() -> None:
    on = offline_output(_request(True), FACTS, _ctx())
    assert "reservas.create" in on["tools"]
    off = offline_output(_request(False), FACTS, _ctx())
    assert not any(t.startswith("reservas.") for t in off["tools"])
