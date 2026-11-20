"""Spec 065, T060 y T062 (requisitos 5.3 y 6.1): el Playground prueba el agente con su modelo.

- El turno simulado responde con el modelo efectivo del agente: el que eligió el partner en
  Agente > Avanzado, sin publicar versión (es un ajuste vivo).
- La respuesta del Playground dice con qué modelo respondió de verdad (``model``, con su
  nombre en ``model_name``) y si fue la reserva (``fell_back``); la transcripción guardada de
  la sesión, también.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from nexus_worker.runtime.llm import InMemoryProvider, LLMRouter
from nexus_worker.simulation.runner import set_simulation_router
from sqlalchemy.ext.asyncio import AsyncSession

from ..business._business_world import Biz
from .test_playground_draft import _agent, _url, biz, scripted  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

LUNA = "openai/gpt-5.6-luna"
ANSWER = "Abrimos de 10 a 20."


async def _choose(client: Any, biz: Biz, agent_id: uuid.UUID, model_id: str) -> None:  # noqa: F811
    resp = await client.put(
        f"/console/clients/{biz.ref}/agents/{agent_id}/model",
        json={"model_id": model_id},
        headers=biz.headers(),
    )
    assert resp.status_code == 200, resp.text


async def _say(client: Any, biz: Biz, agent_id: uuid.UUID, text: str) -> dict[str, Any]:  # noqa: F811
    opened = await client.post(
        _url(biz, agent_id), json={"version": "draft"}, headers=biz.headers()
    )
    assert opened.status_code == 201, opened.text
    session_id = opened.json()["session_id"]
    sent = await client.post(
        f"{_url(biz, agent_id)}/{session_id}/messages", json={"text": text}, headers=biz.headers()
    )
    assert sent.status_code == 200, sent.text
    stored = await client.get(f"{_url(biz, agent_id)}/{session_id}", headers=biz.headers())
    assert stored.status_code == 200, stored.text
    return {"turn": sent.json()["turn"], "transcript": stored.json()["transcript"]}


async def test_the_playground_answers_with_the_agents_model_and_says_so(
    client: Any,
    db_session: AsyncSession,
    biz: Biz,  # noqa: F811
    fake_redis: Any,
    scripted: InMemoryProvider,  # noqa: F811
) -> None:
    agent_id = await _agent(client, biz, fake_redis)
    await _choose(client, biz, agent_id, LUNA)
    scripted.responder = lambda call: "info" if call.role == "classify" else ANSWER

    got = await _say(client, biz, agent_id, "¿A qué hora abrís?")

    answered = [c.model for c in scripted.calls if c.role != "classify"]
    assert answered and set(answered) == {LUNA}, answered
    turn = got["turn"]
    assert turn["bubbles"] == [ANSWER]
    assert (turn["model"], turn["model_name"], turn["fell_back"]) == (LUNA, "Luna", False)
    assert got["transcript"][-1]["model"] == LUNA


async def test_when_the_reserve_answers_the_turn_says_it_fell_back(
    client: Any,
    db_session: AsyncSession,
    biz: Biz,  # noqa: F811
    fake_redis: Any,
) -> None:
    provider = InMemoryProvider()

    def responder(call: Any) -> str:
        if call.role == "classify":
            return "info"
        if call.model == LUNA:
            raise RuntimeError("luna is down")
        return ANSWER

    provider.responder = responder
    set_simulation_router(
        LLMRouter(
            provider=provider,
            classify_model="t/c",
            respond_model="t/r",
            fallback_model="t/fallback",
            retry_backoff_s=0.0,
        )
    )
    try:
        agent_id = await _agent(client, biz, fake_redis)
        await _choose(client, biz, agent_id, LUNA)
        got = await _say(client, biz, agent_id, "¿A qué hora abrís?")
    finally:
        set_simulation_router(None)

    turn = got["turn"]
    assert turn["bubbles"] == [ANSWER]
    assert turn["fell_back"] is True
    assert turn["model"] != LUNA
    assert turn["model"] in {c.model for c in provider.calls if c.role != "classify"}
    assert got["transcript"][-1]["fell_back"] is True
