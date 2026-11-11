"""Los modelos de los trabajos de la plataforma — spec 047, enmienda del 2026-10-29
(requisito 64.2; research D55; T208).

Mientras la gestión de modelos no llegue al panel de operador, **el constructor, la
lectura, el sector, el cliente simulado y el juez** usan el modelo que fija la
configuración del despliegue, nunca el del agente ni uno que pida la consola (la
API rechaza ese cambio con ``409 model_policy_managed``). Una variable de entorno
por tarea y, sin ella, el modelo de su familia de ``WorkerSettings``:

| Tarea | Variable | Sin ella |
|---|---|---|
| ``build`` (borrador, constructor del cliente) | ``NEXUS_LLM_BUILD_MODEL`` | el de responder |
| ``read_source`` (la lectura de webs y fuentes) | ``NEXUS_LLM_READ_SOURCE_MODEL`` | el de extraer |
| ``sector`` (identificar el sector) | ``NEXUS_LLM_SECTOR_MODEL`` | el de extraer |
| ``customer_sim`` (el cliente simulado, T206) | ``NEXUS_LLM_CUSTOMER_SIM_MODEL`` | el de simular |
| ``judge`` (el juez de las pruebas) | ``NEXUS_LLM_JUDGE_MODEL`` | el de simular |

Una tabla y un sitio: cada manejador la lee por :func:`platform_model`, y
``tests/unit/test_platform_models.py`` comprueba que ninguno se aparta.
"""

from __future__ import annotations

import os
from typing import Final, Literal

Family = Literal["respond", "extract", "simulation"]

PLATFORM_MODELS: Final[dict[str, tuple[str, Family]]] = {
    "build": ("NEXUS_LLM_BUILD_MODEL", "respond"),
    "read_source": ("NEXUS_LLM_READ_SOURCE_MODEL", "extract"),
    "sector": ("NEXUS_LLM_SECTOR_MODEL", "extract"),
    "customer_sim": ("NEXUS_LLM_CUSTOMER_SIM_MODEL", "simulation"),
    "judge": ("NEXUS_LLM_JUDGE_MODEL", "simulation"),
}


def platform_model(task: str) -> str:
    """El modelo de ``task`` en este despliegue. ``KeyError`` si no es una tarea
    de la plataforma."""
    from nexus_worker.config import get_worker_settings

    env, family = PLATFORM_MODELS[task]
    configured = os.environ.get(env)
    if configured:
        return configured
    settings = get_worker_settings()
    if family == "respond":
        return settings.llm_respond_model
    if family == "simulation":
        return settings.llm_simulation_model
    return settings.llm_extract_model


# ── Spec 059: el registro de los modelos que la plataforma usa por defecto ──
#
# La protección de «Retirar» y «No disponible» (requisito 1.1) se apoya en este
# registro: un modelo que aparezca aquí no se puede retirar ni marcar no disponible.
# Lo leen la API, para decidir, y el latido del worker, que lo publica tal como lo
# resuelve su proceso (1.5). ``tests/unit/test_platform_default_models.py`` barre
# las configuraciones y el código: un valor por defecto que no pase por aquí lo
# rompe.

#: Campos ``*_model`` de las configuraciones que no son un valor por defecto de
#: una tarea, con su motivo. Vacío hoy: cada campo es un uso.
EXCLUDED_FIELDS: Final[dict[str, str]] = {}

#: Ficheros con identificadores de modelo escritos a mano que no eligen modelo para
#: ninguna tarea, con su motivo. Ruta relativa a ``src/``.
EXCLUDED_SOURCES: Final[dict[str, str]] = {
    "nexus_api/core/respond_catalog.py": (
        "la semilla del catálogo y la lista de identificadores conocidos: no elige "
        "modelo para ninguna tarea. Su SOL_MODEL_ID sí es un valor por defecto, y "
        "entra en el registro como console_fallback y partner_default"
    ),
    "nexus_api/core/litellm_smoke.py": (
        "la prueba de humo manual de LiteLLM (python -m): no corre en ningún servicio"
    ),
}


#: Los usos que resuelve el proceso del worker con su propio entorno. Son los que la
#: API compara con lo que publica el latido (research D2): los demás (companion,
#: visión, evaluaciones, Playground…) los resuelve la API con el suyo, y que el
#: worker los vea distintos no es un desacuerdo.
WORKER_USES: Final[frozenset[str]] = frozenset(
    {
        "classify",
        "classify_fallback",
        "respond",
        "respond_fallback",
        "booking_brake",
        "outcome_grader",
        "extract",
        "simulation",
        *PLATFORM_MODELS,
    }
)


def default_models() -> dict[str, str]:
    """``uso → modelo`` de todo lo que la plataforma resuelve por defecto en este
    proceso, con los ajustes del despliegue ya aplicados. Datos planos: el latido
    lo publica tal cual."""
    from nexus_api.config import get_settings
    from nexus_api.core.respond_catalog import SOL_MODEL_ID
    from nexus_api.services.evals.companion.driver import COMPANION_EVAL_MODEL
    from nexus_api.services.evals.judge import EVAL_JUDGE_MODEL
    from nexus_api.services.evals.pipeline_driver import (
        EVAL_CLASSIFY_MODEL,
        EVAL_FALLBACK_MODEL,
        EVAL_RESPOND_MODEL,
    )

    from nexus_worker.config import get_worker_settings
    from nexus_worker.guardrails.outcome_grader import DEFAULT_GRADER_MODEL

    worker = get_worker_settings()
    api = get_settings()
    models: dict[str, str] = {
        # El turno: ``bootstrap.build_default_router`` usa el de responder como
        # reserva de los dos, y el freno de reservas clasifica con el clasificador.
        "classify": worker.llm_classify_model,
        "classify_fallback": worker.llm_respond_model,
        "respond": worker.llm_respond_model,
        "respond_fallback": worker.llm_respond_model,
        "booking_brake": worker.llm_classify_model,
        "outcome_grader": DEFAULT_GRADER_MODEL,
        "extract": worker.llm_extract_model,
        "simulation": worker.llm_simulation_model,
        # El Playground QA responde como un turno real (5.7).
        "qa_classify": worker.llm_classify_model,
        "qa_respond": worker.llm_respond_model,
        # La API.
        "improve": api.llm_improve_model,
        "companion": api.llm_companion_model,
        "transcribe": api.llm_transcribe_model,
        "vision": api.llm_vision_model,
        "console_fallback": SOL_MODEL_ID,
        "partner_default": SOL_MODEL_ID,
        # Las evaluaciones que lanza el panel.
        "evals_classify": EVAL_CLASSIFY_MODEL,
        "evals_respond": EVAL_RESPOND_MODEL,
        "evals_fallback": EVAL_FALLBACK_MODEL,
        "evals_judge": EVAL_JUDGE_MODEL,
        "evals_companion": COMPANION_EVAL_MODEL,
    }
    if api.knowledge_embedding_model:
        models["knowledge_embedding"] = api.knowledge_embedding_model
    for task in PLATFORM_MODELS:
        models[task] = platform_model(task)
    return models


__all__ = [
    "EXCLUDED_FIELDS",
    "EXCLUDED_SOURCES",
    "PLATFORM_MODELS",
    "WORKER_USES",
    "default_models",
    "platform_model",
]
