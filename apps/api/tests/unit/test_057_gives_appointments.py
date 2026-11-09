"""Spec 057, requisito 5.1: «dar citas» decide quién gana la agenda al encender Reservas.

Un agente da citas si reserva en un conector, si nombra ``booking.*`` o si su texto
promete reservar, mover o cancelar citas, con las mismas palabras que el aviso de
promesas (``compiler.promises_in``). Las frases son las de Spa Jemma (staging,
2026-11-08)."""

from __future__ import annotations

import uuid
from typing import Any

from nexus_api.db.models import AgentConfig, AgentConfigStatus
from nexus_api.services.reservations.passing import gives_appointments


def _cfg(
    *, tools: list[str] | None = None, spec: dict[str, Any] | None = None, prompt: str = ""
) -> AgentConfig:
    return AgentConfig(
        tenant_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        version=1,
        status=AgentConfigStatus.ACTIVE,
        system_prompt_rendered=prompt,
        channels=[],
        tools=tools or [],
        policies={},
        spec=spec,
        created_by="test",
    )


def _structured(description: str, *, rules: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "mode": "structured",
        "identity": {"name": "Luna", "description": description},
        "rules": rules or [],
        "tools": [],
        "ai_disclosure": {"decided": False},
        "model_policy": {"kind": "profile", "profile": "auto"},
        "memory": {"scope": "shared"},
    }


def test_a_text_that_books_gives_appointments() -> None:
    spec = _structured(
        "Agendas, consultas, cambias y cancelas citas siempre en la agenda de Auphere."
    )
    assert gives_appointments(_cfg(spec=spec))


def test_a_rule_that_cancels_appointments_counts() -> None:
    spec = _structured(
        "Atiendes el WhatsApp del salón.", rules=["Cancelas citas cuando te lo piden."]
    )
    assert gives_appointments(_cfg(spec=spec))


def test_an_instructions_agent_is_read_from_its_free_text() -> None:
    spec = {
        "schema_version": "1",
        "mode": "instructions",
        "identity": {"name": "Ana", "description": "Recepción del salón de belleza."},
        "instructions": {"legacy_text": "Da citas en la agenda del negocio."},
        "tools": [],
        "ai_disclosure": {"decided": False},
        "model_policy": {"kind": "profile", "profile": "auto"},
        "memory": {"scope": "shared"},
    }
    assert gives_appointments(_cfg(spec=spec))


def test_a_version_without_spec_is_read_from_its_prompt() -> None:
    assert gives_appointments(_cfg(prompt="Reservas citas para las clientas del salón."))


def test_booking_in_a_connector_gives_appointments() -> None:
    assert gives_appointments(_cfg(tools=["CALENDLY_POST_INVITEE"]))


def test_the_retired_agenda_gives_appointments() -> None:
    assert gives_appointments(_cfg(tools=["booking.create_appointment"]))


def test_a_billing_agent_does_not() -> None:
    spec = _structured(
        "Revisas los comprobantes de pago y pasas al equipo lo que no cuadra.",
        rules=["Si quieren reservar, pasa la conversación al equipo."],
    )
    assert not gives_appointments(_cfg(spec=spec, tools=["payments.request_review"]))


def test_nothing_is_nothing() -> None:
    assert not gives_appointments(None)


def test_the_business_facts_in_the_prompt_do_not_count() -> None:
    """El texto compilado lleva la ficha («Corte · 30 min · se reserva»): con AgentSpec,
    solo cuenta lo que escribe el partner."""
    spec = _structured("Revisas los comprobantes de pago que te mandan las clientas.")
    prompt = "Servicios que atiendes:\n- Cabello · Corte de damas · 30 min · se reserva"
    assert not gives_appointments(_cfg(spec=spec, prompt=prompt))
