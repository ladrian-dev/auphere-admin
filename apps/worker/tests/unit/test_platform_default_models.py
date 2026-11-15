"""Spec 059 (requisitos 1.1, 1.5 y 5.7; T002) — el registro de los modelos que la
plataforma usa por defecto.

La protección de «Retirar» y «No disponible» se apoya en este registro: un modelo
que aparezca aquí no se puede retirar ni marcar no disponible. Por eso el test no
enumera los usos conocidos: **barre** (constitución §I). Recorre los campos
``*_model`` de las dos configuraciones, las tareas de ``PLATFORM_MODELS`` y cada
identificador de modelo escrito a mano en el código de la API y del worker. Un
valor por defecto nuevo que no pase por el registro rompe este test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from nexus_api.config import Settings, get_settings

from nexus_worker.config import WorkerSettings, get_worker_settings
from nexus_worker.platform_models import (
    EXCLUDED_FIELDS,
    EXCLUDED_SOURCES,
    PLATFORM_MODELS,
    default_models,
)

REPO = Path(__file__).resolve().parents[4]
SOURCES = (REPO / "apps/api/src/nexus_api", REPO / "apps/worker/src/nexus_worker")
# Un identificador de modelo de LiteLLM escrito a mano: proveedor/modelo.
_MODEL_LITERAL = re.compile(
    r"""["']((?:openai|anthropic|bedrock|scaleway|gemini|mistral)/[a-z0-9][a-z0-9._:-]*)["']"""
)


def _model_fields(settings_cls: type) -> list[str]:
    return [name for name in settings_cls.model_fields if name.endswith("_model")]


def test_every_model_setting_is_registered_or_excluded() -> None:
    models = default_models()
    worker, api = get_worker_settings(), get_settings()
    for cls, instance in ((WorkerSettings, worker), (Settings, api)):
        for name in _model_fields(cls):
            if name in EXCLUDED_FIELDS:
                assert EXCLUDED_FIELDS[name].strip(), f"{name}: la exclusión necesita su motivo"
                continue
            value = getattr(instance, name)
            if value is None:
                continue
            assert value in models.values(), (
                f"{cls.__name__}.{name} = {value} no está en el registro"
            )


def test_every_platform_task_is_registered() -> None:
    models = default_models()
    for task in PLATFORM_MODELS:
        assert task in models, f"la tarea de plataforma {task} no está en el registro"


def test_every_hardcoded_model_is_registered_or_excused() -> None:
    """Un modelo escrito a mano en el código es un valor por defecto que nadie ve
    desde la configuración. O está en el registro, o su fichero está excusado con
    su motivo."""
    registered = set(default_models().values())
    loose: list[str] = []
    for root in SOURCES:
        for path in root.rglob("*.py"):
            rel = path.relative_to(root.parent).as_posix()
            if rel in EXCLUDED_SOURCES:
                assert EXCLUDED_SOURCES[rel].strip(), f"{rel}: la excusa necesita su motivo"
                continue
            for literal in _MODEL_LITERAL.findall(path.read_text(encoding="utf-8")):
                if literal not in registered:
                    loose.append(f"{rel}: {literal}")
    assert not loose, "modelos escritos a mano fuera del registro:\n" + "\n".join(loose)


def test_runtime_fallbacks_resolve_to_what_the_runtime_uses() -> None:
    """La reserva de responder y la del clasificador son el modelo de responder
    (``bootstrap.build_default_router``), el freno de reservas clasifica con el
    clasificador y el Playground usa los del runtime (5.7)."""
    models = default_models()
    worker = get_worker_settings()
    assert models["respond"] == worker.llm_respond_model
    assert models["respond_fallback"] == worker.llm_respond_model
    assert models["classify"] == worker.llm_classify_model
    assert models["classify_fallback"] == worker.llm_respond_model
    assert models["booking_brake"] == worker.llm_classify_model
    assert models["qa_classify"] == worker.llm_classify_model
    assert models["qa_respond"] == worker.llm_respond_model


def test_a_deployment_override_reaches_the_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_LLM_JUDGE_MODEL", "anthropic/claude-haiku-5-5")
    assert default_models()["judge"] == "anthropic/claude-haiku-5-5"


def test_the_registry_is_plain_data() -> None:
    """Lo que publica el latido (D2) tiene que ser JSON: uso → identificador."""
    models = default_models()
    assert models and all(
        isinstance(k, str) and isinstance(v, str) and v for k, v in models.items()
    )


def test_the_worker_uses_are_part_of_the_registry() -> None:
    """Research D2: la API compara con el latido solo estas claves."""
    from nexus_worker.platform_models import WORKER_USES

    assert set(default_models()) >= WORKER_USES
    assert {"respond", "classify", "judge"} <= WORKER_USES
    assert "companion" not in WORKER_USES, "la resuelve la API con su entorno"
