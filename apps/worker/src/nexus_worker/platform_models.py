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
| ``read_source`` (la lectura de webs y fuentes) | ``NEXUS_LLM_READ_SOURCE_MODEL`` | el de clasificar |
| ``sector`` (identificar el sector) | ``NEXUS_LLM_SECTOR_MODEL`` | el de clasificar |
| ``customer_sim`` (el cliente simulado, T206) | ``NEXUS_LLM_CUSTOMER_SIM_MODEL`` | el de clasificar |
| ``judge`` (el juez de las pruebas) | ``NEXUS_LLM_JUDGE_MODEL`` | el de clasificar |

Una tabla y un sitio: cada manejador la lee por :func:`platform_model`, y
``tests/unit/test_platform_models.py`` comprueba que ninguno se aparta.
"""

from __future__ import annotations

import os
from typing import Final, Literal

Family = Literal["respond", "classify"]

PLATFORM_MODELS: Final[dict[str, tuple[str, Family]]] = {
    "build": ("NEXUS_LLM_BUILD_MODEL", "respond"),
    "read_source": ("NEXUS_LLM_READ_SOURCE_MODEL", "classify"),
    "sector": ("NEXUS_LLM_SECTOR_MODEL", "classify"),
    "customer_sim": ("NEXUS_LLM_CUSTOMER_SIM_MODEL", "classify"),
    "judge": ("NEXUS_LLM_JUDGE_MODEL", "classify"),
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
    return settings.llm_respond_model if family == "respond" else settings.llm_classify_model


__all__ = ["PLATFORM_MODELS", "platform_model"]
