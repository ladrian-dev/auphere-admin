"""La única puerta a LiteLLM — spec 065, requisito 4.12 (research.md §D13).

Sin esto, LiteLLM descarga su mapa de modelos de GitHub al importarse: qué parámetros
acepta cada modelo puede cambiar sin desplegar, y lo que se probó en CI no es lo que corre.
Con el mapa local que trae la versión fijada tampoco basta: no conoce Sol, Terra, Luna ni
los Claude 5.5, y rechaza antes de salir cualquier ``tool_choice`` hacia GPT-5.6 y el
razonamiento de Haiku 5.5 (medido el 2026-11-20).

Así que cada proceso usa el mapa local **y** registra encima las entradas de
``litellm_models.json``, copiadas del mapa publicado con su fecha. Actualizarlas es un
cambio de código con su prueba en el cable (``test_every_llm_use_on_the_wire``).

Nadie importa ``litellm`` por su cuenta: se pide aquí con :func:`litellm_module`.
``tests/unit/test_litellm_is_deterministic.py`` lo barre.
"""

from __future__ import annotations

import json
import os
import threading
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any, Final

#: Las entradas que el mapa local no trae (research.md §D13).
PINNED_MODELS_FILE: Final[Path] = Path(__file__).with_name("litellm_models.json")

_registered = False
_lock = threading.Lock()


def pin_local_map() -> None:
    """Que LiteLLM use su mapa local al importarse. Respeta un valor explícito del entorno."""
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")


@cache
def pinned_entries() -> dict[str, dict[str, Any]]:
    """``modelo → entrada del mapa`` de los modelos que registramos encima del local."""
    data = json.loads(PINNED_MODELS_FILE.read_text(encoding="utf-8"))
    models: dict[str, dict[str, Any]] = data["models"]
    return models


def litellm_module() -> ModuleType:
    """El módulo ``litellm`` con el mapa fijo y nuestras entradas registradas.

    La primera llamada de cada proceso fija el mapa (si nada lo importó antes) y registra
    las entradas; las demás devuelven el módulo sin más."""
    global _registered
    pin_local_map()
    import litellm

    # Un doble de pruebas puede sustituir el módulo sin ``register_model``: entonces no se
    # registra nada y el registro queda pendiente para cuando llegue el de verdad.
    register = getattr(litellm, "register_model", None)
    if not _registered and register is not None:
        with _lock:
            if not _registered:
                register(pinned_entries())
                _registered = True
    return litellm


__all__ = ["PINNED_MODELS_FILE", "litellm_module", "pin_local_map", "pinned_entries"]
