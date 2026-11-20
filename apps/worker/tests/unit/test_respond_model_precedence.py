"""Spec 065, T024 (requisitos 2.2, 2.3, 3.2 y 3.3): con qué modelo responde el turno.

El turno resuelve el modelo de respuesta del agente con la única resolución
(``nexus_api.core.respond_model.resolve``): su elección; si no, la de su versión; si no, el
modelo por defecto de Auphere de este entorno, que al desplegar es Sol, como ayer. La
asignación de respuesta del cliente y ``llm_respond_model`` ya no deciden el modelo de un
agente: ``llm_respond_model`` queda para la plataforma (constructor, Playground QA antiguo).
La degradación por presupuesto sigue por encima de todo.
"""

from __future__ import annotations

import uuid

import pytest
from nexus_api.core import respond_catalog

from nexus_worker.runtime.agent_loader import AgentBundle
from nexus_worker.runtime.model_resolver import ModelBinding
from nexus_worker.runtime.pipeline import agent_respond_model, turn_respond_model

SOL = "openai/gpt-5.6-sol"
TERRA = "openai/gpt-5.6-terra"
LUNA = "openai/gpt-5.6-luna"
HAIKU = "anthropic/claude-haiku-5-5"


def bundle(**kw: object) -> AgentBundle:
    base: dict[str, object] = {
        "tenant_id": uuid.uuid4(),
        "version": 1,
        "version_id": uuid.uuid4(),
        "system_prompt": "Recepción",
        "tools": frozenset(),
    }
    base.update(kw)
    return AgentBundle(**base)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _seed() -> object:
    respond_catalog.reset()
    yield
    respond_catalog.reset()


def test_the_agents_choice_answers() -> None:
    got = agent_respond_model(bundle(respond_model=TERRA, respond_model_set_by="partner"))
    assert (got.model_id, got.source) == (TERRA, "agent")


def test_without_a_choice_the_version_then_auphere_default() -> None:
    with_version = bundle(policies={"llm": {"respond_model": LUNA}})
    assert agent_respond_model(with_version).model_id == LUNA
    assert agent_respond_model(bundle()).model_id == SOL, "al desplegar, Sol (CE-005)"


def test_the_default_is_the_platform_setting_not_llm_respond_model(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_LLM_RESPOND_MODEL", LUNA)
    respond_catalog.refresh_from_rows(
        [
            {"model_id": m, "status": "active", "offer_label": None, "respond_enabled_at": None}
            for m in respond_catalog.BOOT_HOP_MODEL_IDS
        ],
        agent_default=HAIKU,
    )
    assert agent_respond_model(bundle()).model_id == HAIKU


def test_the_clients_respond_binding_no_longer_decides() -> None:
    bound = bundle(
        model_bindings={
            "respond": ModelBinding(role="respond", model_id=LUNA, fallback_chain=(TERRA,))
        }
    )
    assert agent_respond_model(bound).model_id == SOL


def test_the_budget_downgrade_wins_over_everything() -> None:
    chosen = bundle(respond_model=TERRA, respond_model_set_by="partner")
    assert turn_respond_model(chosen, degrade_to=LUNA) == (LUNA, ())
    assert turn_respond_model(chosen, degrade_to=None) == (TERRA, ())
