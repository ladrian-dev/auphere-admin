"""Spec 065, T060 (requisitos 6.1 y 5.3): la batería y el Playground dicen con qué modelo
respondió el agente de verdad.

- ``TurnOutcome`` lleva ``model`` (el que respondió, del estado del turno) y ``fell_back``;
- cada turno del agente en la transcripción de una prueba lleva los dos;
- el cliente simulado evita el modelo que respondió de verdad (``avoid_model``), también
  cuando fue la reserva, y el juez se compara con los que respondieron.

Que el turno simulado responde con el modelo efectivo del agente (su elección) lo fija la
prueba del Playground en la API (``tests/integration/builder/test_playground_agent_model.py``):
necesita la base y el agente de verdad.
"""

from __future__ import annotations

from typing import Any

from nexus_worker.simulation.customer import converse
from nexus_worker.simulation.runner import TurnOutcome
from nexus_worker.simulation.world import World

TERRA = "openai/gpt-5.6-terra"
SONNET = "anthropic/claude-sonnet-5-5"


def test_the_turn_outcome_carries_the_fallback() -> None:
    outcome = TurnOutcome(bubbles=["Hola"], actions=[], model=SONNET, fell_back=True)
    assert (outcome.model, outcome.fell_back) == (SONNET, True)
    assert TurnOutcome(bubbles=[], actions=[]).fell_back is False


async def test_the_transcript_and_the_customer_see_the_model_that_answered() -> None:
    served = iter([(TERRA, False), (SONNET, True)])
    avoided: list[str | None] = []

    async def agent_turn(_message: str) -> TurnOutcome:
        model, fell_back = next(served)
        return TurnOutcome(bubbles=["Vale."], actions=[], model=model, fell_back=fell_back)

    async def customer(messages: list[dict[str, str]], *, avoid_model: str | None = None) -> str:
        avoided.append(avoid_model)
        return '{"message": "¿Y el sábado?", "status": "continue"}'

    talk = await converse(
        first_message="Hola",
        persona="Cliente",
        plan="Pregunta dos cosas.",
        customer=customer,
        agent_turn=agent_turn,
        world=_world(),
        max_turns=2,
    )
    agent_turns: list[dict[str, Any]] = [t for t in talk.transcript if t["role"] == "agent"]
    assert [(t["model"], t["fell_back"]) for t in agent_turns] == [(TERRA, False), (SONNET, True)]
    assert talk.responding == [TERRA, SONNET]
    assert avoided == [TERRA], "el cliente evita el que respondió"


def _world() -> World:
    return World(timezone="Europe/Madrid", now="2026-11-02T07:00:00+00:00", week=[], services=[])
