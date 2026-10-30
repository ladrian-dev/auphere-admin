"""Spec 047, enmienda del 2026-10-29 (requisito 64.2, D55; T208) — los modelos de
los trabajos de la plataforma los fija su configuración.

El constructor, la lectura, el sector, el cliente simulado y el juez usan el modelo
que fija el despliegue (una variable de entorno por tarea, o el de su familia), no
el del agente ni uno que pida la consola. Una tabla y un sitio: cada manejador la
lee por ``platform_model``.
"""

from __future__ import annotations

import pytest

from nexus_worker.config import get_worker_settings
from nexus_worker.platform_models import PLATFORM_MODELS, platform_model

TASKS = {"build", "read_source", "sector", "customer_sim", "judge"}


def test_every_platform_task_has_its_setting() -> None:
    assert set(PLATFORM_MODELS) == TASKS
    envs = [env for env, _family in PLATFORM_MODELS.values()]
    assert len(set(envs)) == len(envs) and all(e.startswith("NEXUS_LLM_") for e in envs)


@pytest.mark.parametrize("task", sorted(TASKS))
def test_the_deployment_decides_each_model(task: str, monkeypatch: pytest.MonkeyPatch) -> None:
    env, family = PLATFORM_MODELS[task]
    monkeypatch.delenv(env, raising=False)
    settings = get_worker_settings()
    expected = settings.llm_respond_model if family == "respond" else settings.llm_classify_model
    assert platform_model(task) == expected
    monkeypatch.setenv(env, "anthropic/claude-haiku-5-5")
    assert platform_model(task) == "anthropic/claude-haiku-5-5"


def test_the_handlers_ask_the_platform_table(monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus_worker.jobs.handlers import agent_draft, agent_tests, client_read, sector_identify

    for env, _family in PLATFORM_MODELS.values():
        monkeypatch.setenv(env, f"vendor/{env.lower()}")
    assert agent_draft.build_model() == platform_model("build")
    assert client_read.read_source_model() == platform_model("read_source")
    assert sector_identify.sector_model() == platform_model("sector")
    assert agent_tests.judge_model() == platform_model("judge")


def test_an_unknown_task_is_an_error() -> None:
    with pytest.raises(KeyError):
        platform_model("respond_to_customer")
