"""El constructor tiene su propio plazo (staging, 2026-11-04).

El borrador de un agente es un JSON largo: a unos 60 tokens/s no cabe en los 30 s del
proveedor, y el SDK lo reintentaba dos veces más: ``provider_failed`` tras unos 91 s.
Ningún ``agent_draft`` terminó en 7 días (8 de 8 fallidos, con varias causas), y el
cliente siempre acababa en la plantilla.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from nexus_worker.jobs.handlers import agent_draft
from nexus_worker.simulation.world import Action, World

pytestmark = pytest.mark.unit


def test_a_build_call_has_time_and_no_sdk_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus_worker import config
    from nexus_worker.runtime import llm

    seen: dict[str, Any] = {}

    class Recording:
        def __init__(self, **kwargs: Any) -> None:
            seen.update(kwargs)

    monkeypatch.setattr(llm, "LiteLLMProvider", Recording)
    settings = config.get_worker_settings()
    monkeypatch.setattr(settings, "llm_use_inmemory", False)
    assert agent_draft.default_complete(uuid.uuid4()) is not None
    assert seen["timeout_s"] == agent_draft.BUILD_CALL_TIMEOUT_S > 60
    assert seen["max_retries"] == 0
    # El trabajo deja sitio a dos llamadas (la guía generada y el borrador).
    assert agent_draft.TIMEOUT_S > 2 * agent_draft.BUILD_CALL_TIMEOUT_S


def test_the_provider_passes_its_retries_only_when_told() -> None:
    from dataclasses import fields

    from nexus_worker.runtime.llm import LiteLLMProvider

    defaults = {f.name: f.default for f in fields(LiteLLMProvider)}
    assert defaults["max_retries"] is None
    assert defaults["timeout_s"] == 30.0  # un turno de chat sigue con su plazo


def _world() -> World:
    return World.__new__(World)


def test_a_connector_calendar_counts_as_a_booking() -> None:
    """Con Calendly la cita no pasa por la agenda simulada: es la acción apuntada."""
    world = _world()
    world.bookings = []
    world.escalated = False
    world.actions = [Action(tool="CALENDLY_POST_INVITEE", phrase="Crear", args={})]
    world.timezone = "UTC"
    state = world.final_state()
    assert state["booking"]["created"] is True and state["booking"]["count"] == 1


def test_google_calendar_is_not_a_booking() -> None:
    """Spec 043, R11.9: a Google solo sale lo que ya es una reserva."""
    world = _world()
    world.bookings = []
    world.escalated = False
    world.actions = [Action(tool="GOOGLECALENDAR_CREATE_EVENT", phrase="Crear", args={})]
    world.timezone = "UTC"
    assert world.final_state()["booking"]["created"] is False


def test_looking_for_slots_is_not_a_booking() -> None:
    world = _world()
    world.bookings = []
    world.escalated = False
    world.actions = [Action(tool="GOOGLECALENDAR_FIND_FREE_SLOTS", phrase="Ver", args={})]
    world.timezone = "UTC"
    assert world.final_state()["booking"]["created"] is False
